import os
import tempfile
from unittest.mock import MagicMock

import run_eval
from configs import MODEL_CONFIGS
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
