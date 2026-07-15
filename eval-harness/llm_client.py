import os
import time
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

API_KEY_ENV_VAR = "ANTHROPIC_EVAL_HARNESS_API_KEY"

PRICING_PER_MTOK = {
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}

# claude-opus-4-8 and claude-sonnet-5 reject the `temperature` param outright (400
# invalid_request_error); only older-tier models like claude-haiku-4-5 still accept it.
MODELS_WITHOUT_TEMPERATURE = frozenset({
    "claude-opus-4-8",
    "claude-sonnet-5",
})


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
        self.client = client or Anthropic(api_key=os.environ.get(API_KEY_ENV_VAR), max_retries=2)

    def call(self, model: str, prompt: str, temperature: float, effort: Optional[str] = None,
              max_tokens: int = 2048) -> LLMResponse:
        start = time.monotonic()
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if model not in MODELS_WITHOUT_TEMPERATURE:
            kwargs["temperature"] = temperature
        if effort is not None:
            kwargs["output_config"] = {"effort": effort}
        response = self.client.messages.create(**kwargs)
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
