from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelConfig:
    label: str
    model: str
    temperature: float
    prompt_variant: str
    judge_only: bool = False
    # Only claude-sonnet-5 configs set this; effort errors on Haiku 4.5, and
    # leaving it unset for opus-judge keeps that config out of scope for this change.
    effort: Optional[str] = None


MODEL_CONFIGS = [
    ModelConfig(label="opus-judge", model="claude-opus-4-8", temperature=0.0,
                prompt_variant="default", judge_only=True),
    ModelConfig(label="sonnet-default", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="default", effort="high"),
    ModelConfig(label="sonnet-terse", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="terse", effort="high"),
    ModelConfig(label="sonnet-effort-low", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="default", effort="low"),
    ModelConfig(label="sonnet-effort-high", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="default", effort="high"),
    ModelConfig(label="sonnet-effort-xhigh", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="default", effort="xhigh"),
    ModelConfig(label="haiku-default", model="claude-haiku-4-5-20251001", temperature=0.2,
                prompt_variant="default"),
]

PROMPT_VARIANT_SUFFIXES = {
    "default": "",
    "terse": "\n\nBe as concise as possible in your response.",
}
