from dataclasses import dataclass


@dataclass
class ModelConfig:
    label: str
    model: str
    temperature: float
    prompt_variant: str
    judge_only: bool = False


MODEL_CONFIGS = [
    ModelConfig(label="opus-judge", model="claude-opus-4-8", temperature=0.0,
                prompt_variant="default", judge_only=True),
    ModelConfig(label="sonnet-default", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="default"),
    ModelConfig(label="sonnet-terse", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="terse"),
    ModelConfig(label="sonnet-hot", model="claude-sonnet-5", temperature=0.8,
                prompt_variant="default"),
    ModelConfig(label="haiku-default", model="claude-haiku-4-5-20251001", temperature=0.2,
                prompt_variant="default"),
]

PROMPT_VARIANT_SUFFIXES = {
    "default": "",
    "terse": "\n\nBe as concise as possible in your response.",
}
