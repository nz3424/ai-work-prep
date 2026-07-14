# Eval Harness: Scope Reports to a Single Run by Default

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix GitHub issue #13 — `report.generate_report` currently blends every row ever written to `eval_results.db` (across all past `run_id`s) into one aggregate per `(model, temperature, prompt_variant)`, so re-running the harness after a prompt/rubric tweak silently averages two different questions' results together with no indication this happened.

**Chosen design (confirmed with the repo owner):** `generate_report` defaults to showing only the latest `run_id`. Callers can opt into a specific `run_id` or `"all"` (every run) for cross-run comparison — but even in `"all"` mode, results from different runs are never blended into the same aggregate row: `run_id` becomes part of the aggregation key unconditionally, so blending across runs is structurally impossible rather than policy-dependent. `run_eval.py`'s own end-of-run report call is fixed to pass its own `completed_run_id` explicitly instead of discarding it.

**Architecture:** `ResultsStore` (storage.py) gains two new read methods — `latest_run_id()` and `results_for_run(run_id)` — alongside the existing unchanged `all_results()`. `report.generate_report` gains a `run_id` parameter (default `"latest"`) that it resolves before querying, and `_aggregate_by_config` always groups by `(run_id, model, temperature, prompt_variant)` so the "all runs" opt-in path can never silently re-blend runs. `run_eval.py`'s `__main__` block passes its own `completed_run_id` into `generate_report` instead of ignoring the return value of `run()`.

## Global Constraints

- No change to the `results` table schema (`storage.py`'s `SCHEMA` constant) — `run_id` is already a column.
- `all_results()` in `storage.py` stays exactly as-is (signature and behavior unchanged) — it is still used internally and by existing tests.
- `_aggregate_by_config`'s existing behavior (codegen pass-rate / judge-score exclusion rules, subject vs. judge cost separation) is unchanged — the only change to it is adding `run_id` to the group-by key and to each summary dict.
- Use the `id` column (`INTEGER PRIMARY KEY AUTOINCREMENT`) — not `timestamp` — to determine "latest" (`ORDER BY id DESC LIMIT 1`). This avoids any edge case with tied or non-monotonic timestamp strings.
- `generate_report`'s new `run_id` parameter accepts three kinds of values: the literal string `"latest"` (default — resolves to the most recent `run_id` in the DB), the literal string `"all"` (every run, each kept distinct in the aggregation), or any other string (treated as a literal `run_id` to filter to).
- Existing tests in `tests/test_report.py` and `tests/test_storage.py` all use a single fixed `run_id="run1"` for every row they write — do not change those existing tests' row data; your new grouping-by-run_id logic must keep them passing unmodified (single run_id in the data means the grouping change is a no-op for them).
- Every module must remain testable without spending real API money or requiring Docker (no change to that constraint — these tasks don't touch LLM-calling code).

---

### Task 1: Storage — run-scoped reads

**Files:**
- Modify: `eval-harness/storage.py`
- Modify: `eval-harness/tests/test_storage.py`

**Step 1: Write failing tests first (TDD).**

Add to `eval-harness/tests/test_storage.py` (reuse the existing `_make_row` helper already in that file):

```python
def test_latest_run_id_returns_none_for_empty_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        assert store.latest_run_id() is None
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_latest_run_id_returns_most_recently_written_run():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(run_id="run1", task_id="codegen_01"))
        store.write_result(_make_row(run_id="run1", task_id="codegen_02"))
        store.write_result(_make_row(run_id="run2", task_id="codegen_01"))
        assert store.latest_run_id() == "run2"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_results_for_run_filters_to_matching_run_id():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(run_id="run1", task_id="codegen_01"))
        store.write_result(_make_row(run_id="run2", task_id="codegen_02"))
        results = store.results_for_run("run1")
        assert len(results) == 1
        assert results[0].task_id == "codegen_01"
        assert results[0].run_id == "run1"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_results_for_run_returns_empty_list_for_unknown_run_id():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(run_id="run1"))
        assert store.results_for_run("nonexistent") == []
    finally:
        if os.path.exists(path):
            os.remove(path)
```

Run `pytest tests/test_storage.py -v` from `eval-harness/` and confirm these four new tests fail (methods don't exist yet) while all pre-existing tests in the file still pass.

**Step 2: Implement.**

In `eval-harness/storage.py`, add two methods to `ResultsStore` (after `write_result`, before `all_results` — or after `all_results`, either position is fine, but do not modify `all_results` itself):

```python
    def latest_run_id(self) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT run_id FROM results ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def results_for_run(self, run_id: str) -> list[ResultRow]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM results WHERE run_id = ?", (run_id,))
        rows = [
            ResultRow(
                run_id=r["run_id"], model=r["model"], temperature=r["temperature"],
                prompt_variant=r["prompt_variant"], task_id=r["task_id"],
                task_type=r["task_type"], score=r["score"], pass_fail=r["pass_fail"],
                cost_usd=r["cost_usd"], judge_cost_usd=r["judge_cost_usd"], latency_ms=r["latency_ms"],
                timestamp=r["timestamp"], raw_response=r["raw_response"], error=r["error"],
            )
            for r in cursor.fetchall()
        ]
        conn.close()
        return rows
```

Note `results_for_run` duplicates `all_results`'s row-mapping block with a `WHERE` clause added — this mirrors the existing code's style (no shared row-mapping helper exists yet in this file; do not introduce one as part of this task, that's out of scope).

**Step 3: Run the full storage test file and confirm all tests (old and new) pass.**

```bash
cd eval-harness && pytest tests/test_storage.py -v
```

**Report contract:** commit with a message describing the storage changes. In your final report, state the exact `pytest tests/test_storage.py -v` command you ran and its pass/fail summary line.

---

### Task 2: Report — scope aggregation to a run (or explicit "all")

**Files:**
- Modify: `eval-harness/report.py`
- Modify: `eval-harness/tests/test_report.py`

**Depends on Task 1** — `ResultsStore.latest_run_id()` and `ResultsStore.results_for_run(run_id)` must already exist (they will, since Task 1 is committed before this task is dispatched).

**Step 1: Write failing tests first (TDD).**

Add to `eval-harness/tests/test_report.py`:

```python
def test_generate_report_defaults_to_latest_run_only():
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
            cost_usd=0.001, latency_ms=100.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run2", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
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
            run_id="run1", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
            cost_usd=0.001, latency_ms=100.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run2", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
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
        run_id="run1", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
        task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
        cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
        raw_response="code", error=None,
    )
    run2_row = ResultRow(
        run_id="run2", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
        task_id="codegen_01", task_type="codegen", score=0.0, pass_fail="fail",
        cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:01",
        raw_response="code", error=None,
    )

    summary = _aggregate_by_config([run1_row, run2_row])

    assert len(summary) == 2
    pass_rates = {s["run_id"]: s["codegen_pass_rate"] for s in summary}
    assert pass_rates == {"run1": 1.0, "run2": 0.0}
```

Run `pytest tests/test_report.py -v` from `eval-harness/` and confirm these three new tests fail while all pre-existing tests in the file still pass (the pre-existing tests all use a single `run_id="run1"`, so `_aggregate_by_config`'s grouping change must not affect them once implemented — but right now `run_id` isn't in the summary dict at all, so `test_aggregate_by_config_keeps_different_run_ids_in_separate_groups` fails on the `s["run_id"]` lookup, and the two `generate_report` tests fail because both runs currently always end up blended into the CSV).

**Step 2: Implement.**

In `eval-harness/report.py`:

1. Change `generate_report`'s signature and body:

```python
def generate_report(db_path: str, html_path: str, csv_path: str, run_id: str = "latest") -> None:
    store = ResultsStore(db_path)
    if run_id == "all":
        results = store.all_results()
    else:
        resolved = store.latest_run_id() if run_id == "latest" else run_id
        results = store.results_for_run(resolved) if resolved else []

    _write_csv(results, csv_path)
    _write_html(results, html_path)
```

2. In `_aggregate_by_config`, add `r.run_id` as the first element of the group-by tuple, and add `"run_id"` to each summary dict:

```python
def _aggregate_by_config(results):
    groups = defaultdict(list)
    for r in results:
        groups[(r.run_id, r.model, r.temperature, r.prompt_variant)].append(r)

    summary = []
    for (run_id, model, temperature, variant), rows in groups.items():
        # exclude rows that errored before scoring, matching the judge metric's policy
        codegen_rows = [r for r in rows if r.task_type == "codegen" and r.pass_fail is not None]
        judged_rows = [r for r in rows if r.task_type == "api_design" and r.score is not None]
        pass_count = sum(1 for r in codegen_rows if r.pass_fail == "pass")
        avg_judge_score = (sum(r.score for r in judged_rows) / len(judged_rows)) if judged_rows else None
        subject_cost = sum(r.cost_usd for r in rows if r.cost_usd is not None)
        judge_cost = sum(r.judge_cost_usd for r in rows if r.judge_cost_usd is not None)
        latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else None
        summary.append({
            "run_id": run_id, "model": model, "temperature": temperature, "prompt_variant": variant,
            "codegen_pass_rate": (pass_count / len(codegen_rows)) if codegen_rows else None,
            "avg_judge_score": avg_judge_score,
            "subject_cost_usd": subject_cost,
            "judge_cost_usd": judge_cost,
            "total_cost_usd": subject_cost + judge_cost,
            "avg_latency_ms": avg_latency,
        })
    return summary
```

3. In `_write_html`, add a "Run ID" column: add `<th>Run ID</th>` right after `<th>Model</th>` in the `<thead>` row, and add `f"<td>{html.escape(s['run_id'])}</td>"` right after the model `<td>` in the per-row loop (immediately before the existing `f"<td>{s['temperature']}</td>"` line). Leave every other column, the chart JS, and the rest of the HTML template untouched.

**Step 3: Run the full report test file and confirm all tests (old and new) pass.**

```bash
cd eval-harness && pytest tests/test_report.py -v
```

**Report contract:** commit with a message describing the report changes. In your final report, state the exact `pytest tests/test_report.py -v` command you ran and its pass/fail summary line, and confirm the pre-existing tests (`test_generate_report_creates_html_and_csv`, `test_aggregate_reports_subject_and_judge_cost_separately`, `test_aggregate_excludes_errored_codegen_rows_from_pass_rate`) still pass unmodified.

---

### Task 3: Wire run_eval.py to the new default, update README

**Files:**
- Modify: `eval-harness/run_eval.py`
- Modify: `eval-harness/tests/test_run_eval.py` (only if it currently asserts on the `generate_report` call — read it first to check; add a test only if none already covers this)
- Modify: `eval-harness/README.md`

**Depends on Task 2** — `generate_report`'s new `run_id` parameter must already exist.

**Step 1: Check existing coverage, then implement.**

Read `eval-harness/tests/test_run_eval.py` first. If it already has a test asserting how `generate_report` is called (e.g. via monkeypatching/mocking `report.generate_report` and checking call args) from the `__main__` block, update or extend that test to assert `run_id=completed_run_id` is passed. If no such test exists, add one that imports `run_eval`, monkeypatches `run_eval.generate_report` (or the equivalent import point used in that file) to capture its call arguments, invokes the script's entry-point logic, and asserts the captured `run_id` equals the return value of `run_eval.run(...)`. Follow the existing test file's established patterns for mocking/monkeypatching rather than introducing a new mocking style — read a couple of its existing tests first to match conventions.

Then in `eval-harness/run_eval.py`, change the `__main__` block:

```python
if __name__ == "__main__":
    completed_run_id = run(DB_PATH)
    print(f"\nRun {completed_run_id} complete. Generating report...")
    from report import generate_report
    generate_report(DB_PATH, "report.html", "report.csv", run_id=completed_run_id)
    print("Report written to report.html and report.csv")
```

(This is the only functional change to this file — the `run()` function itself, `_run_codegen`, and `_run_api_design` are unchanged.)

**Step 2: Update `eval-harness/README.md`.**

Find the paragraph in the "Running" section that currently reads:

> This runs every subject model config against every task, prints progress as it goes, writes results to `eval_results.db`, and regenerates `report.html` / `report.csv` at the end. Re-running appends a new run rather than overwriting — all runs stay in the same database, tagged by `run_id`.

Replace it with wording that additionally explains: the report defaults to showing only the most recently completed run; `report.generate_report(db_path, html_path, csv_path, run_id=...)` accepts `"latest"` (default), a specific `run_id` string, or `"all"` to see every run; and when `"all"` (or a query spanning multiple runs) is used, each run's numbers are kept in separate rows (never averaged together) via a `Run ID` column in both the HTML table and CSV export.

**Step 3: Run the full test suite (excluding the Docker-dependent test file, per this repo's own documented convention) and confirm everything passes.**

```bash
cd eval-harness && pytest -v --ignore=tests/test_test_scorer.py
```

**Report contract:** commit with a message describing the run_eval + README changes. In your final report, state the exact pytest command you ran and its pass/fail summary line, and paste the exact README paragraph diff.

---

## Plan Self-Review Notes

- Task boundaries were chosen so each task lands in 1-2 files with a complete, verbatim-code spec (mechanical implementation, no design judgment left to the implementer) — the design decision itself was already made in conversation with the repo owner before this plan was written.
- Task 3's test step is intentionally conditional ("check existing coverage first") rather than prescribing exact new test code, because `tests/test_run_eval.py`'s current mocking approach for the `__main__` block is unknown to this plan's author at time of writing — the task brief instructs the implementer to match existing conventions rather than inventing a new pattern blind.
- No task touches `scoring/`, `tasks/`, `llm_client.py`, `configs.py`, or the Docker-dependent test file — those are out of scope for this bug fix and untouched by this plan.
