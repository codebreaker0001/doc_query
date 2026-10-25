"""
Evaluates the full RAG pipeline (retrieval + generation) against the golden
dataset, using RAGAS's classic metrics with Groq as the judge:

  - Faithfulness: does the generated answer only say things the retrieved
    context actually supports? (catches hallucination)
  - Answer Relevancy: does the answer actually address the question asked?
  - Context Precision: are the retrieved chunks ranked with the relevant
    ones first?
  - Context Recall: does the retrieved context cover everything the
    reference answer needs?

This complements eval_retrieval.py (DeepEval), which only grades retrieval.
RAGAS here also grades the generated answer, so it catches a case
eval_retrieval.py can't: good retrieval + a bad/hallucinated answer from the
LLM.

Like eval_retrieval.py, this drives metrics one at a time with
single_turn_score() (sync) instead of ragas.evaluate(), to keep every judge
call strictly sequential -- ragas.evaluate() fires metrics concurrently,
which bursts past Groq's free-tier tokens/minute cap. answer_relevancy also
needs strictness=1 (default 3): RAGAS samples `strictness` candidate
questions per answer for self-consistency, each as a separate completion
with n=strictness -- Groq's API rejects n>1 outright.

Results are saved to results_ragas.json in this folder, keyed by question,
merged with whatever's already there.

Run from anywhere (this file fixes up sys.path itself):

    python evals/eval_ragas.py            # all questions
    python evals/eval_ragas.py 6 8        # only GOLDEN_DATASET[6:8]

Requires the eval tenant's documents to already be ingested — see
ingest_eval_pdf.py.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "True")

from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from ragas import SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._answer_relevance import ResponseRelevancy
from ragas.metrics._context_precision import LLMContextPrecisionWithReference
from ragas.metrics._context_recall import LLMContextRecall
from ragas.metrics._faithfulness import Faithfulness

from golden_dataset import GOLDEN_DATASET
from llm import generate_answer
from retrieval import retrieve_relevant_chunks

TENANT_ID = 2
JUDGE_MODEL = "openai/gpt-oss-120b"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # same model embed.py uses in production
RESULTS_FILE = Path(__file__).parent / "results_ragas.json"


async def build_samples(dataset: list[dict]) -> list[tuple[str, SingleTurnSample]]:
    samples = []
    for item in dataset:
        chunks = await retrieve_relevant_chunks(item["question"], tenant_id=TENANT_ID)
        answer = generate_answer(item["question"], chunks)
        sample = SingleTurnSample(
            user_input=item["question"],
            retrieved_contexts=chunks,
            response=answer,
            reference=item["expected_answer"],
        )
        samples.append((item["question"], sample))
    return samples


def load_existing_results() -> dict:
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(GOLDEN_DATASET)
    dataset = GOLDEN_DATASET[start:end]

    samples = asyncio.run(build_samples(dataset))

    judge_llm = LangchainLLMWrapper(ChatGroq(model=JUDGE_MODEL, api_key=os.environ["GROQ_API_KEY"]))
    embeddings = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL))

    metrics = {
        "Faithfulness": Faithfulness(llm=judge_llm),
        "Answer Relevancy": ResponseRelevancy(llm=judge_llm, embeddings=embeddings, strictness=1),
        "Context Precision": LLMContextPrecisionWithReference(llm=judge_llm),
        "Context Recall": LLMContextRecall(llm=judge_llm),
    }

    all_results = load_existing_results()

    for i, (question, sample) in enumerate(samples, start=1):
        print(f"\n=== [{i}/{len(samples)}] {question}")
        case_result = {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "answer": sample.response,
            "metrics": {},
        }
        for name, metric in metrics.items():
            try:
                score = metric.single_turn_score(sample)
                case_result["metrics"][name] = {"score": score}
                print(f"  {name}: {score:.2f}")
            except Exception as e:
                case_result["metrics"][name] = {"score": None, "error": str(e)}
                print(f"  {name}: FAILED - {e}")
        all_results[question] = case_result

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved results to {RESULTS_FILE}")

    print("\n=== Summary (average across all saved results) ===")
    for name in metrics:
        values = [
            case["metrics"][name]["score"]
            for case in all_results.values()
            if case["metrics"].get(name, {}).get("score") is not None
        ]
        if values:
            print(f"  {name}: {sum(values) / len(values):.2f}  ({len(values)}/{len(all_results)} completed)")
        else:
            print(f"  {name}: no successful evaluations")


if __name__ == "__main__":
    main()
