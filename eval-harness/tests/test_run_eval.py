import os
import tempfile
from unittest.mock import MagicMock

import run_eval
from configs import MODEL_CONFIGS, PROMPT_VARIANT_SUFFIXES
from tasks.codegen_tasks import CODEGEN_TASKS
from tasks.apidesign_tasks import API_DESIGN_TASKS
from storage import ResultsStore


def test_run_writes_expected_number_of_rows(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)

    fake_response = MagicMock(text="fake code", cost_usd=0.001, latency_ms=100.0)
    monkeypatch.setattr(run_eval.LLMClient, "call", lambda self, **kwargs: fake_response)

    fake_codegen_result = MagicMock(score=1.0, pass_fail="pass", error=None)
    fake_judge_result = MagicMock(score=7.0, pass_fail=None, error=None)
    monkeypatch.setattr(run_eval, "score_codegen", lambda code, test_code: fake_codegen_result)
    monkeypatch.setattr(run_eval, "score_api_design", lambda client, prompt, rubric, text: fake_judge_result)

    try:
        run_id = run_eval.run(db_path)
        store = ResultsStore(db_path)
        results = store.all_results()

        subject_configs = [c for c in MODEL_CONFIGS if not c.judge_only]
        expected_rows = len(subject_configs) * (len(CODEGEN_TASKS) + len(API_DESIGN_TASKS))
        assert len(results) == expected_rows
        assert all(r.run_id == run_id for r in results)
        assert {r.task_type for r in results} == {"codegen", "api_design"}
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_run_records_error_row_on_api_failure(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)

    def raise_error(self, **kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(run_eval.LLMClient, "call", raise_error)

    try:
        run_eval.run(db_path)
        store = ResultsStore(db_path)
        results = store.all_results()
        assert len(results) > 0
        assert all(r.error == "rate limited" for r in results)
        assert all(r.score is None for r in results)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_prompt_variant_suffix_is_applied(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)

    fake_response = MagicMock(text="fake code", cost_usd=0.001, latency_ms=100.0)
    captured_prompts = {}

    def fake_call(self, **kwargs):
        captured_prompts.setdefault(kwargs["prompt"], []).append(kwargs)
        return fake_response

    monkeypatch.setattr(run_eval.LLMClient, "call", fake_call)

    fake_codegen_result = MagicMock(score=1.0, pass_fail="pass", error=None)
    fake_judge_result = MagicMock(score=7.0, pass_fail=None, error=None)
    monkeypatch.setattr(run_eval, "score_codegen", lambda code, test_code: fake_codegen_result)
    monkeypatch.setattr(run_eval, "score_api_design", lambda client, prompt, rubric, text: fake_judge_result)

    try:
        run_eval.run(db_path)

        terse_suffix = PROMPT_VARIANT_SUFFIXES["terse"]
        default_suffix = PROMPT_VARIANT_SUFFIXES["default"]

        task = CODEGEN_TASKS[0]
        terse_prompt = task.prompt + terse_suffix
        default_prompt = task.prompt + default_suffix

        assert terse_prompt in captured_prompts
        assert terse_suffix in terse_prompt
        assert default_prompt in captured_prompts
        assert terse_suffix not in default_prompt
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_run_records_error_row_when_scorer_raises(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)

    fake_response = MagicMock(text="fake code", cost_usd=0.001, latency_ms=100.0)
    monkeypatch.setattr(run_eval.LLMClient, "call", lambda self, **kwargs: fake_response)

    def raise_codegen_error(code, test_code):
        raise RuntimeError("docker daemon unavailable")

    def raise_judge_error(client, prompt, rubric, text):
        raise RuntimeError("judge rate limited")

    monkeypatch.setattr(run_eval, "score_codegen", raise_codegen_error)
    monkeypatch.setattr(run_eval, "score_api_design", raise_judge_error)

    try:
        run_id = run_eval.run(db_path)
        store = ResultsStore(db_path)
        results = store.all_results()

        subject_configs = [c for c in MODEL_CONFIGS if not c.judge_only]
        expected_rows = len(subject_configs) * (len(CODEGEN_TASKS) + len(API_DESIGN_TASKS))
        assert len(results) == expected_rows
        assert all(r.run_id == run_id for r in results)

        codegen_rows = [r for r in results if r.task_type == "codegen"]
        api_design_rows = [r for r in results if r.task_type == "api_design"]

        assert all(r.error == "docker daemon unavailable" for r in codegen_rows)
        assert all(r.score is None and r.pass_fail is None for r in codegen_rows)
        assert all(r.cost_usd == 0.001 and r.latency_ms == 100.0 for r in codegen_rows)

        assert all(r.error == "judge rate limited" for r in api_design_rows)
        assert all(r.score is None and r.pass_fail is None for r in api_design_rows)
        assert all(r.cost_usd == 0.001 and r.latency_ms == 100.0 for r in api_design_rows)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
