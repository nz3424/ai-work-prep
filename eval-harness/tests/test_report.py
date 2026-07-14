import os
import tempfile

from storage import ResultsStore, ResultRow
from report import generate_report


def test_generate_report_creates_html_and_csv():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    html_path = db_path + ".html"
    csv_path = db_path + ".csv"

    try:
        store = ResultsStore(db_path)
        store.write_result(ResultRow(
            run_id="run1", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
            cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run1", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
            task_id="apidesign_01", task_type="api_design", score=8.0, pass_fail=None,
            cost_usd=0.003, latency_ms=500.0, timestamp="2026-07-06T00:00:01",
            raw_response="design", error=None,
        ))

        generate_report(db_path, html_path, csv_path)

        assert os.path.exists(html_path)
        assert os.path.exists(csv_path)
        with open(html_path) as f:
            content = f.read()
        assert "claude-sonnet-5" in content
        assert "<canvas" in content

        with open(csv_path) as f:
            csv_content = f.read()
        assert "codegen_01" in csv_content
        assert "apidesign_01" in csv_content
    finally:
        for p in (db_path, html_path, csv_path):
            if os.path.exists(p):
                os.remove(p)
