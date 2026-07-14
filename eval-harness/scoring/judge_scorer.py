import json

from scoring.base import ScoreResult

JUDGE_MODEL = "claude-opus-4-8"

JUDGE_PROMPT_TEMPLATE = """You are grading an API design response against a rubric.

Original task prompt:
{task_prompt}

Rubric:
{rubric}

Candidate response to grade:
{response_text}

Respond with ONLY a JSON object, no other text, in this exact shape:
{{"score": <number 0-10>, "rationale": "<one sentence>"}}
"""


def score_api_design(llm_client, task_prompt: str, rubric: str, response_text: str) -> ScoreResult:
    prompt = JUDGE_PROMPT_TEMPLATE.format(task_prompt=task_prompt, rubric=rubric, response_text=response_text)
    judge_response = llm_client.call(model=JUDGE_MODEL, prompt=prompt, temperature=0.0)
    parsed = _parse_judge_output(judge_response.text)

    if parsed is None:
        strict_prompt = prompt + "\n\nRespond with ONLY the JSON object and nothing else."
        judge_response = llm_client.call(model=JUDGE_MODEL, prompt=strict_prompt, temperature=0.0)
        parsed = _parse_judge_output(judge_response.text)

    if parsed is None:
        return ScoreResult(score=None, pass_fail=None, raw_output=judge_response.text, error="judge_parse_failed")

    return ScoreResult(score=parsed["score"], pass_fail=None, raw_output=judge_response.text)


def _parse_judge_output(text: str):
    try:
        data = json.loads(text.strip())
        return {"score": float(data["score"]), "rationale": data.get("rationale", "")}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
