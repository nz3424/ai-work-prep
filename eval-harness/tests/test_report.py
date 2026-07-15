import os
import tempfile

from storage import ResultsStore, ResultRow
from report import generate_report, _aggregate_by_config


def test_generate_report_creates_html_and_csv():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    html_path = db_path + ".html"
    csv_path = db_path + ".csv"

    try:
        store = ResultsStore(db_path)
        store.write_result(ResultRow(
            run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
            effort="high", prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
            cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
            effort="high", prompt_variant="default",
            task_id="apidesign_01", task_type="api_design", score=8.0, pass_fail=None,
            cost_usd=0.003, judge_cost_usd=0.02, latency_ms=500.0, timestamp="2026-07-06T00:00:01",
            raw_response="design", error=None,
        ))

        generate_report(db_path, html_path, csv_path)

        assert os.path.exists(html_path)
        assert os.path.exists(csv_path)
        with open(html_path) as f:
            content = f.read()
        assert "claude-sonnet-5" in content
        assert "sonnet-default" in content
        assert "<canvas" in content

        with open(csv_path) as f:
            csv_content = f.read()
        assert "codegen_01" in csv_content
        assert "apidesign_01" in csv_content
        assert "judge_cost_usd" in csv_content
        assert "0.02" in csv_content
    finally:
        for p in (db_path, html_path, csv_path):
            if os.path.exists(p):
                os.remove(p)


def test_aggregate_reports_subject_and_judge_cost_separately():
    codegen_row = ResultRow(
        run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
        effort="high", prompt_variant="default",
        task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
        cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
        raw_response="code", error=None,
    )
    api_design_row = ResultRow(
        run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
        effort="high", prompt_variant="default",
        task_id="apidesign_01", task_type="api_design", score=8.0, pass_fail=None,
        cost_usd=0.003, judge_cost_usd=0.02, latency_ms=500.0, timestamp="2026-07-06T00:00:01",
        raw_response="design", error=None,
    )

    summary = _aggregate_by_config([codegen_row, api_design_row])

    assert len(summary) == 1
    assert summary[0]["subject_cost_usd"] == 0.005
    assert summary[0]["judge_cost_usd"] == 0.02
    assert summary[0]["total_cost_usd"] == 0.025


def test_aggregate_excludes_errored_codegen_rows_from_pass_rate():
    passing_row = ResultRow(
        run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
        effort="high", prompt_variant="default",
        task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
        cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
        raw_response="code", error=None,
    )
    errored_row = ResultRow(
        run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
        effort="high", prompt_variant="default",
        task_id="codegen_02", task_type="codegen", score=None, pass_fail=None,
        cost_usd=None, latency_ms=None, timestamp="2026-07-06T00:00:01",
        raw_response=None, error="rate limited",
    )

    summary = _aggregate_by_config([passing_row, errored_row])

    assert len(summary) == 1
    assert summary[0]["codegen_pass_rate"] == 1.0


def test_generate_report_defaults_to_latest_run_only():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    html_path = db_path + ".html"
    csv_path = db_path + ".csv"

    try:
        store = ResultsStore(db_path)
        store.write_result(ResultRow(
            run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
            effort="high", prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
            cost_usd=0.001, latency_ms=100.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run2", label="sonnet-default", model="claude-sonnet-5", temperature=None,
            effort="high", prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=0.0, pass_fail="fail",
            cost_usd=0.001, latency_ms=100.0, timestamp="2026-07-06T00:00:01",
            raw_response="code", error=None,
        ))

        generate_report(db_path, html_path, csv_path)

        with open(csv_path) as f:
            csv_content = f.read()
        assert "run1" not in csv_content
        assert "run2" in csv_content
    finally:
        for p in (db_path, html_path, csv_path):
            if os.path.exists(p):
                os.remove(p)


def test_generate_report_run_id_all_keeps_runs_separate_not_blended():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    html_path = db_path + ".html"
    csv_path = db_path + ".csv"

    try:
        store = ResultsStore(db_path)
        store.write_result(ResultRow(
            run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
            effort="high", prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
            cost_usd=0.001, latency_ms=100.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run2", label="sonnet-default", model="claude-sonnet-5", temperature=None,
            effort="high", prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=0.0, pass_fail="fail",
            cost_usd=0.001, latency_ms=100.0, timestamp="2026-07-06T00:00:01",
            raw_response="code", error=None,
        ))

        generate_report(db_path, html_path, csv_path, run_id="all")

        with open(csv_path) as f:
            csv_content = f.read()
        assert "run1" in csv_content
        assert "run2" in csv_content
    finally:
        for p in (db_path, html_path, csv_path):
            if os.path.exists(p):
                os.remove(p)


def test_aggregate_by_config_keeps_different_run_ids_in_separate_groups():
    run1_row = ResultRow(
        run_id="run1", label="sonnet-default", model="claude-sonnet-5", temperature=None,
        effort="high", prompt_variant="default",
        task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
        cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
        raw_response="code", error=None,
    )
    run2_row = ResultRow(
        run_id="run2", label="sonnet-default", model="claude-sonnet-5", temperature=None,
        effort="high", prompt_variant="default",
        task_id="codegen_01", task_type="codegen", score=0.0, pass_fail="fail",
        cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:01",
        raw_response="code", error=None,
    )

    summary = _aggregate_by_config([run1_row, run2_row])

    assert len(summary) == 2
    pass_rates = {s["run_id"]: s["codegen_pass_rate"] for s in summary}
    assert pass_rates == {"run1": 1.0, "run2": 0.0}
