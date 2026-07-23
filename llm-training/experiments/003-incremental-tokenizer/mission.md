# Experiment 003: Incremental BPE Tokenizer — Speed With Quality Held

## Hypothesis

Replacing `train()`'s full-corpus rescan on every merge with incremental
pair-count bookkeeping (PR #29 / branch `llm-training/incremental-bpe-merges`)
will **dramatically cut tokenizer-build wall-clock** — per-merge cost drops
from O(corpus length) to O(occurrences of the merged pair) — **with no
meaningful effect on model quality**.

Experiment 001's `results.md` flagged the naive merge loop as the slowest part
of the entire run, slower than the 3000 training steps that followed it. This
experiment quantifies the fix and confirms it is quality-neutral.

The **only** change from experiment 002 is the tokenizer's internal algorithm.
The model (RoPE, now on `main`), corpus, `num_merges`, optimizer, and seed are
all held identical, so any change in final loss is attributable to the
tokenizer and nothing else.

## What "quality-neutral" means here (the drift caveat)

The incremental loop breaks ties among equal-frequency pairs differently from
the old `max`-over-a-freshly-rebuilt-dict (documented in
`src/merge_state.py`). So the learned vocab *may* differ from 002's
`tokenizer.json` — not because either is wrong (BPE roundtripping is invariant
to which equal-frequency pair is chosen) but because the tie-break order
changed. The success bar is therefore **final loss within noise of 002**, with
any small difference explainable by vocab drift rather than a regression.

## Baselines

**Speed** — no recorded baseline exists (002 predates the timing
instrumentation). `bench_tokenizer.py` establishes it by timing the vendored
naive loop and the current incremental loop on the *same* corpus, same
`num_merges`, same box — an apples-to-apples before/after pair. The main run
also emits `timing tokenizer_build_seconds` for the incremental build.

**Quality** — experiment 002 (RoPE, the current `main` model):
- `train_loss` @ step 2999: **2.6205**
- best `val_loss`: **3.7795** (step ~1750)
- Untrained baseline (`ln(vocab_size)`, ~1006-token vocab): ~6.9

## Success criteria

- [ ] `bench_tokenizer.py` shows the incremental build is materially faster
      than the naive loop at `num_merges=750` on the real corpus (target: at
      least several× faster; the naive loop's cost is what 001 flagged)
- [ ] `timing tokenizer_build_seconds` in `training.log` is a small fraction
      of `timing training_seconds` — the tokenizer is no longer the bottleneck
- [ ] Final `train_loss` within noise of 002's 2.62 (or any gap explainable by
      vocab drift, not a regression)
- [ ] best `val_loss` comparable to 002's 3.78
- [ ] `generate.py` sample quality comparable to 002 (no qualitative drop)

## Run

`run_fleet.sh` — identical hyperparameters to `002-rope`; only the experiment
id and checkpoint/S3 paths differ. Must be executed with the
`llm-training/incremental-bpe-merges` branch checked out (or after it merges to
`main`) so the incremental tokenizer is the code path under test. The script
runs `bench_tokenizer.py` first (captures the naive-vs-incremental baseline),
then the full training run.

## Results

See `results.md` after the run.
