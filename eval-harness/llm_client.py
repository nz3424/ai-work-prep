import time
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

PRICING_PER_MTOK = {
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICING_PER_MTOK[model]
    return (input_tokens / 1_000_000) * prices["input"] + (output_tokens / 1_000_000) * prices["output"]


class LLMClient:
    def __init__(self, client: Optional[Anthropic] = None):
        # max_retries=2 gives up to 3 total attempts on transient failures.
        self.client = client or Anthropic(max_retries=2)

    def call(self, model: str, prompt: str, temperature: float, max_tokens: int = 2048) -> LLMResponse:
        start = time.monotonic()
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000
        text = "".join(block.text for block in response.content if block.type == "text")
        cost = compute_cost(model, response.usage.input_tokens, response.usage.output_tokens)
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
        )
