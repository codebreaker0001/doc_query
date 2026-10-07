"""
Wraps Groq as a DeepEval judge model, so metrics don't need an OpenAI key.

DeepEval's built-in metrics grade things by asking an LLM judge to return
structured verdicts, then parsing them. DeepEval only knows how to talk to
OpenAI out of the box; DeepEvalBaseLLM is its documented extension point for
plugging in any other model as that judge.
"""

import os
import time

from deepeval.models import DeepEvalBaseLLM
from groq import Groq, RateLimitError


class GroqJudge(DeepEvalBaseLLM):
    def __init__(self, model_name: str = "openai/gpt-oss-120b", max_retries: int = 15, max_wait_seconds: int = 60):
        self.model_name = model_name
        self.max_retries = max_retries
        self.max_wait_seconds = max_wait_seconds
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def load_model(self):
        return self.client

    def generate(self, prompt: str) -> str:
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content
            except RateLimitError:
                # Free-tier Groq has a per-minute token budget; back off and
                # let it refill instead of failing the whole eval run. Capped
                # so a stubborn rate limit doesn't turn one call into an
                # hours-long wait -- 15 retries capped at 60s is worst-case
                # ~13 minutes for one call, which is still far cheaper than
                # babysitting manual reruns.
                wait_seconds = min(10 * (attempt + 1), self.max_wait_seconds)
                time.sleep(wait_seconds)
        raise RuntimeError(f"Groq judge still rate-limited after {self.max_retries} retries")

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self) -> str:
        return f"Groq {self.model_name}"
