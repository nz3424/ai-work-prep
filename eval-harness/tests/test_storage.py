import os
import tempfile

from storage import ResultsStore, ResultRow


def _make_row(**overrides):
    defaults = dict(
        run_id="run1",
        model="claude-sonnet-5",
        temperature=0.2,
        prompt_variant="default",
        task_id="codegen_01",
        task_type="codegen",
        score=1.0,
        pass_fail="pass",
        cost_usd=0.001,
        latency_ms=250.0,
        timestamp="2026-07-06T00:00:00",
        raw_response="def reverse(s): return s[::-1]",
        error=None,
    )
    defaults.update(overrides)
    return ResultRow(**defaults)


def test_write_and_read_result():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row())
        results = store.all_results()
        assert len(results) == 1
        assert results[0].task_id == "codegen_01"
        assert results[0].score == 1.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_multiple_writes_accumulate():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(task_id="codegen_01"))
        store.write_result(_make_row(task_id="codegen_02", score=0.0, pass_fail="fail"))
        results = store.all_results()
        assert len(results) == 2
        assert {r.task_id for r in results} == {"codegen_01", "codegen_02"}
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_judge_cost_usd_roundtrips():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(task_type="api_design", judge_cost_usd=0.015))
        results = store.all_results()
        assert results[0].judge_cost_usd == 0.015
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_nullable_fields_roundtrip_as_none():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(score=None, pass_fail=None, cost_usd=None,
                                      latency_ms=None, raw_response=None, error="boom"))
        results = store.all_results()
        assert results[0].score is None
        assert results[0].error == "boom"
    finally:
        if os.path.exists(path):
            os.remove(path)
