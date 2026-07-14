from dataclasses import dataclass

from scoring.judge_scorer import score_api_design


@dataclass
class FakeLLMResponse:
    text: str
    cost_usd: float = 0.01


class FakeLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def call(self, model, prompt, temperature, max_tokens=2048):
        self.calls.append((model, prompt, temperature))
        return FakeLLMResponse(text=self._responses.pop(0))


def test_score_api_design_parses_valid_json():
    client = FakeLLMClient(['{"score": 8, "rationale": "Good use of REST conventions"}'])
    result = score_api_design(client, "Design a REST API for a todo app", "rubric text", "response text")
    assert result.score == 8.0
    assert result.error is None
    assert result.judge_cost_usd == 0.01


def test_score_api_design_retries_on_bad_json_then_succeeds():
    client = FakeLLMClient(["not json at all", '{"score": 5, "rationale": "ok"}'])
    result = score_api_design(client, "prompt", "rubric", "response")
    assert result.score == 5.0
    assert len(client.calls) == 2
    assert result.judge_cost_usd == 0.02


def test_score_api_design_gives_up_after_second_failure():
    client = FakeLLMClient(["not json", "still not json"])
    result = score_api_design(client, "prompt", "rubric", "response")
    assert result.score is None
    assert result.error == "judge_parse_failed"
    assert result.judge_cost_usd == 0.02


def test_score_api_design_parses_json_wrapped_in_markdown_fences():
    client = FakeLLMClient(['```json\n{"score": 7, "rationale": "fenced but valid"}\n```'])
    result = score_api_design(client, "prompt", "rubric", "response")
    assert result.score == 7.0
    assert result.error is None
    assert len(client.calls) == 1


def test_score_api_design_parses_json_with_surrounding_prose():
    client = FakeLLMClient(['Sure, here is my evaluation:\n{"score": 6, "rationale": "ok"}\nHope that helps!'])
    result = score_api_design(client, "prompt", "rubric", "response")
    assert result.score == 6.0
    assert result.error is None
