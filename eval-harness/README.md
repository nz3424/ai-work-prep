# eval-harness

**Maps to:** Itinerary Days 4-5 (agent-capstone slot) — see `../GOALS.md`.

## What this is

An LLM evaluation harness that compares Claude Opus/Sonnet/Haiku (plus prompt and
temperature variants) on two task types:

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
export ANTHROPIC_API_KEY=sk-ant-...
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

(Update as you go: what ran, what you found, what's fragile.)

## Findings

(Fill in after the first full run — e.g. which model won on cost/quality, any
surprising failures.)
