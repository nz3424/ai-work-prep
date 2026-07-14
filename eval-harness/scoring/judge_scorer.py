import json
import re

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
    judge_cost_usd = judge_response.cost_usd
    parsed = _parse_judge_output(judge_response.text)

    if parsed is None:
        strict_prompt = prompt + "\n\nRespond with ONLY the JSON object and nothing else."
        judge_response = llm_client.call(model=JUDGE_MODEL, prompt=strict_prompt, temperature=0.0)
        judge_cost_usd += judge_response.cost_usd
        parsed = _parse_judge_output(judge_response.text)

    if parsed is None:
        return ScoreResult(score=None, pass_fail=None, raw_output=judge_response.text,
                            error="judge_parse_failed", judge_cost_usd=judge_cost_usd)

    return ScoreResult(score=parsed["score"], pass_fail=None, raw_output=judge_response.text,
                        judge_cost_usd=judge_cost_usd)


def _parse_judge_output(text: str):
    candidates = [text.strip()]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            return {"score": float(data["score"]), "rationale": data.get("rationale", "")}
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return None
