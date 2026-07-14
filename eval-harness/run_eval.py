import uuid
from datetime import datetime, timezone

from configs import MODEL_CONFIGS, PROMPT_VARIANT_SUFFIXES
from llm_client import LLMClient
from storage import ResultsStore, ResultRow
from scoring.test_scorer import score_codegen
from scoring.judge_scorer import score_api_design
from tasks.codegen_tasks import CODEGEN_TASKS
from tasks.apidesign_tasks import API_DESIGN_TASKS

DB_PATH = "eval_results.db"


def run(db_path: str = DB_PATH) -> str:
    run_id = str(uuid.uuid4())[:8]
    store = ResultsStore(db_path)
    client = LLMClient()
    subject_configs = [c for c in MODEL_CONFIGS if not c.judge_only]

    for config in subject_configs:
        for task in CODEGEN_TASKS:
            _run_codegen(client, store, run_id, config, task)
        for task in API_DESIGN_TASKS:
            _run_api_design(client, store, run_id, config, task)

    return run_id


def _run_codegen(client, store, run_id, config, task):
    print(f"[{config.label}] {task.task_id} ... ", end="", flush=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt = task.prompt + PROMPT_VARIANT_SUFFIXES[config.prompt_variant]
    try:
        response = client.call(model=config.model, prompt=prompt, temperature=config.temperature)
    except Exception as exc:
        store.write_result(ResultRow(
            run_id=run_id, model=config.model, temperature=config.temperature,
            prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="codegen",
            score=None, pass_fail=None, cost_usd=None, latency_ms=None,
            timestamp=timestamp, raw_response=None, error=str(exc),
        ))
        print(f"ERROR ({exc})")
        return

    try:
        result = score_codegen(response.text, task.test_code)
    except Exception as exc:
        store.write_result(ResultRow(
            run_id=run_id, model=config.model, temperature=config.temperature,
            prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="codegen",
            score=None, pass_fail=None, cost_usd=response.cost_usd, latency_ms=response.latency_ms,
            timestamp=timestamp, raw_response=response.text, error=str(exc),
        ))
        print(f"ERROR ({exc})")
        return

    store.write_result(ResultRow(
        run_id=run_id, model=config.model, temperature=config.temperature,
        prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="codegen",
        score=result.score, pass_fail=result.pass_fail, cost_usd=response.cost_usd,
        latency_ms=response.latency_ms, timestamp=timestamp,
        raw_response=response.text, error=result.error,
    ))
    status = result.pass_fail.upper() if result.pass_fail else "ERROR"
    print(f"{status} ({response.latency_ms:.0f}ms, ${response.cost_usd:.4f})")


def _run_api_design(client, store, run_id, config, task):
    print(f"[{config.label}] {task.task_id} ... ", end="", flush=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt = task.prompt + PROMPT_VARIANT_SUFFIXES[config.prompt_variant]
    try:
        response = client.call(model=config.model, prompt=prompt, temperature=config.temperature)
    except Exception as exc:
        store.write_result(ResultRow(
            run_id=run_id, model=config.model, temperature=config.temperature,
            prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="api_design",
            score=None, pass_fail=None, cost_usd=None, latency_ms=None,
            timestamp=timestamp, raw_response=None, error=str(exc),
        ))
        print(f"ERROR ({exc})")
        return

    try:
        result = score_api_design(client, task.prompt, task.rubric, response.text)
    except Exception as exc:
        store.write_result(ResultRow(
            run_id=run_id, model=config.model, temperature=config.temperature,
            prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="api_design",
            score=None, pass_fail=None, cost_usd=response.cost_usd, latency_ms=response.latency_ms,
            timestamp=timestamp, raw_response=response.text, error=str(exc),
        ))
        print(f"ERROR ({exc})")
        return

    store.write_result(ResultRow(
        run_id=run_id, model=config.model, temperature=config.temperature,
        prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="api_design",
        score=result.score, pass_fail=result.pass_fail, cost_usd=response.cost_usd,
        latency_ms=response.latency_ms, timestamp=timestamp,
        raw_response=response.text, error=result.error,
    ))
    print(f"score={result.score} ({response.latency_ms:.0f}ms, ${response.cost_usd:.4f})")


if __name__ == "__main__":
    completed_run_id = run(DB_PATH)
    print(f"\nRun {completed_run_id} complete. Generating report...")
    from report import generate_report
    generate_report(DB_PATH, "report.html", "report.csv")
    print("Report written to report.html and report.csv")
