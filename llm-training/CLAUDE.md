# llm-training — agent operating rules

Project-scoped instructions for work under `llm-training/`. These are durable
operational conventions specific to this track; they sit **under** the global
`~/.claude/CLAUDE.md` rules (git hygiene, the skill size-gate, etc.), never
above them. For goals, tasks, and status see `README.md`.

## Running the trainer

Run it as a module from the `llm-training/` directory:

```
python3.11 -m src.train ...
```

Not `python3.11 src/train.py` — invoking the file directly puts `src/` itself
on `sys.path` instead of `llm-training/`, so `from src.tokenizer import ...`
fails to resolve.

## Fleet experiments

- **Every experiment's `run_fleet.sh` must install deps via
  `fleet/install_deps.sh`**, never a bare `pip install -r requirements.txt`.
  The fleet box is GPU-less; default-PyPI `torch` pulls the CUDA build plus
  huge `nvidia-*-cu*` wheels that overflow the small disk/tmpfs
  (`[Errno 28] No space left on device`). The shared script installs the
  CPU-only wheel and keeps the fix in one place so it can't drift between
  experiments (it did, between 001 and 002). When creating a new experiment,
  copy an existing `run_fleet.sh` so you inherit the shared-installer call.

## Creating a new experiment

Copy the most recent `experiments/NNN-*/` directory rather than starting from
scratch — you inherit the shared-installer call, the `-m src.train` invocation,
and the S3 upload step. Each experiment directory holds `mission.md`
(hypothesis + baselines + success criteria), `run_fleet.sh`, `results.md`, a
run-time `source_archive/` snapshot of `src/`, `training_config.txt`, and
`training.log`. The run emits `timing` lines (tokenizer build, training
seconds, steps/sec) — always keep them; the wall-clock record is part of the
reproducibility spec. Hold hyperparameters identical to whichever experiment
you're comparing against, so the result is attributable to the one variable
under test.

## Committing tokenizer-named files

`.gitignore`'s `*token*` secret rule matches anything with "token" anywhere in
its path by substring — `tokenizer.py`, `bench_tokenizer.*`, a `*-tokenizer`
experiment directory — and silently drops it with **no error**. Don't rename
around it; add a scoped `!` negation following the existing pattern near the
bottom of `.gitignore`. Trained `tokenizer.json` artifacts stay ignored via the
separate `checkpoints/` rule, and should — they're large binaries.
