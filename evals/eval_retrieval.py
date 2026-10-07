"""
Evaluates retrieval.py's retrieval quality against the golden dataset, using
DeepEval's contextual metrics with Groq as the judge model.

We drive this as a plain sequential loop instead of using DeepEval's
evaluate() helper. evaluate() always calls each metric's async a_measure(),
which fires one judge call per retrieved chunk *concurrently* regardless of
the metric's async_mode setting -- that instantly bursts past Groq's 8000
tokens/minute free-tier cap. Calling metric.measure() ourselves, one test
case and one metric at a time, actually respects async_mode=False and keeps
every judge call strictly sequential. Slower, but reliable on a free tier --
and a failure on one test case no longer wipes out every other result.

Results are saved to results.json in this folder, keyed by question, merged
with whatever's already there -- so a partial rerun (see below) only updates
the questions it actually ran, instead of wiping out the rest of the file.

Run from anywhere (this file fixes up sys.path itself):

    python evals/eval_retrieval.py            # all questions
    python evals/eval_retrieval.py 6 8         # only GOLDEN_DATASET[6:8],
                                                # e.g. to redo ones that
                                                # failed on rate limits

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

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric, ContextualRelevancyMetric
from deepeval.test_case import LLMTestCase

from golden_dataset import GOLDEN_DATASET
from groq_judge import GroqJudge
from retrieval import retrieve_relevant_chunks

TENANT_ID = 2
RESULTS_FILE = Path(__file__).parent / "results.json"


async def build_test_cases(dataset: list[dict]) -> list[tuple[str, LLMTestCase]]:
    test_cases = []
    for item in dataset:
        retrieved_chunks = await retrieve_relevant_chunks(item["question"], tenant_id=TENANT_ID)
        test_case = LLMTestCase(
            input=item["question"],
            expected_output=item["expected_answer"],
            actual_output="",  # unused by the contextual retrieval metrics below
            retrieval_context=retrieved_chunks,
        )
        test_cases.append((item["question"], test_case))
    return test_cases


def load_existing_results() -> dict:
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(GOLDEN_DATASET)
    dataset = GOLDEN_DATASET[start:end]

    test_cases = asyncio.run(build_test_cases(dataset))

    judge = GroqJudge()
    metrics = {
        "Contextual Precision": ContextualPrecisionMetric(model=judge, async_mode=False),
        "Contextual Recall": ContextualRecallMetric(model=judge, async_mode=False),
        "Contextual Relevancy": ContextualRelevancyMetric(model=judge, async_mode=False),
    }

    all_results = load_existing_results()

    for i, (question, test_case) in enumerate(test_cases, start=1):
        print(f"\n=== [{i}/{len(test_cases)}] {question}")
        case_result = {"evaluated_at": datetime.now(timezone.utc).isoformat(), "metrics": {}}
        for name, metric in metrics.items():
            try:
                score = metric.measure(test_case)
                case_result["metrics"][name] = {"score": score, "reason": metric.reason}
                print(f"  {name}: {score:.2f}  ({metric.reason})")
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
