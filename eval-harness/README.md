# eval-harness

**Maps to:** Itinerary Days 4-5 (agent-capstone slot) — see `../GOALS.md`.

## What this is

An LLM evaluation harness that compares Claude Opus/Sonnet/Haiku (plus prompt-variant
and Sonnet effort-level variants) on two task types:

- **Code generation** (5 tasks) — scored by running real pytest unit tests inside a
  sandboxed, network-disabled Docker container.
- **API design** (5 tasks) — scored by Claude Opus acting as an LLM judge against a
  hand-written rubric. Opus is excluded from being scored as a subject, to avoid
  self-evaluation bias.

Results are stored in SQLite (`eval_results.db`) and rendered into a static,
self-contained HTML report (`report.html`) plus a CSV export (`report.csv`).

## Setup

```bash
cd eval-harness
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_EVAL_HARNESS_API_KEY=sk-ant-...
```

Docker Desktop must be running (code-gen tasks execute inside containers).

## Running

```bash
python run_eval.py
```

This runs every subject model config against every task, prints progress as it goes,
writes results to `eval_results.db`, and regenerates `report.html` / `report.csv` at
the end. Re-running appends a new run rather than overwriting — all runs stay in the
same database, tagged by `run_id`.

The report defaults to showing only the run that just completed, so results from
different runs are never silently blended together. Under the hood,
`report.generate_report(db_path, html_path, csv_path, run_id=...)` accepts `"latest"`
(the default — the most recently completed run), a specific `run_id` string to look at
one run in isolation, or `"all"` to include every run ever recorded. When `"all"` (or
any query spanning multiple runs) is used, each run's numbers are kept in their own
rows rather than averaged together — a `Run ID` column identifies which run each row
came from, in both the HTML table and the CSV export.

## Running the harness's own tests

```bash
pytest -v
```

No API key needed for most tests (LLM calls are mocked). `tests/test_test_scorer.py`
requires Docker Desktop running (it exercises real container execution against golden
good/bad solutions).

## Architecture

See `../docs/superpowers/specs/2026-07-06-eval-harness-design.md` for the full design
rationale, and `../docs/superpowers/plans/2026-07-06-eval-harness.md` for the
implementation plan.

## Status

Clean run (`run_id=dd65b66d`) completed with the `output_config.effort` axis in place:
6 subject configs (`sonnet-default`, `sonnet-terse`, `sonnet-effort-low`,
`sonnet-effort-high`, `sonnet-effort-xhigh`, `haiku-default`) × 10 tasks each, no
errored rows. `temperature` is recorded as `null` for every Sonnet config (the API
silently drops it) and populated only for Haiku, which still accepts it.

## Findings

- **Codegen pass rate is saturated at 100% across every config** — as expected, the
  interesting signal is in judge score, cost, and latency, not pass/fail.
- **`xhigh` effort scored surprisingly poorly on API-design (4.6/10 avg)** — well below
  `sonnet-effort-low` and `sonnet-effort-high` (9.8/10 each) despite costing about the
  same and taking longer (11.1s vs 9.2-10.2s avg latency). Two of five xhigh API-design
  tasks scored 3.0 and one scored 0.0. This one run isn't enough to conclude `xhigh`
  is worse in general for this task type — it's worth a second run to see if it
  replicates before drawing a conclusion.
- **`sonnet-default` and `sonnet-effort-high` send byte-identical requests** (both
  `effort="high"`) and landed close but not identical on judge score (9.4 vs 9.8) —
  a reminder that the LLM judge itself has some run-to-run variance, separate from
  the effort axis being tested.
- **`sonnet-effort-low` matched `sonnet-effort-high` on judge score (9.8 vs 9.8)** while
  costing slightly less ($0.346 vs $0.377 total) — on this task set, low effort was not
  a meaningful quality tradeoff.
- **`sonnet-terse` was the cheapest non-Haiku option** ($0.180 total, 4.6s avg latency)
  with only a modest judge-score dip (8.4 vs 9.4-9.8 for the `default` prompt variant).
- **Haiku is cheapest overall** ($0.299 total) but scored lowest on judge quality
  (6.2/10) among non-anomalous configs.
