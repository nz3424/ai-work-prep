# Experiment 003: Incremental BPE Tokenizer — Results

## Outcome

**The optimization works — and it corrected our understanding of the run.**
The incremental pair-count bookkeeping made the tokenizer build **25.9×
faster** (162.96s → 6.29s at `num_merges=750` on the 1.12M-char corpus), and
model quality held within noise of experiment 002 despite the learned vocab
drifting (best `val_loss` 3.79 in both, at the same step 1750).

The surprise: once measured, the tokenizer build was **never the run's
bottleneck**. Even the naive version was ~4% of wall-clock; training dominates
at ~96%. Experiment 001's claim that the tokenizer was "the slowest part of the
run, slower than the 3000 training steps" was made before timing
instrumentation existed and does not survive measurement (see below). The
change is a real iteration-speed and scaling win — just not the
training-throughput unlock 001 implied.

## Speed: before vs after

_From `bench_tokenizer.txt` (naive vs incremental on the same box) and the
`timing` lines in `training.log`._

| Metric | Value |
|---|---|
| Corpus | tinyshakespeare.txt (1,115,394 chars) |
| `num_merges` | 750 |
| Naive tokenizer build | **162.96s** |
| Incremental tokenizer build | **6.29s** (bench) / 5.74s (in-run) |
| **Speedup** | **25.9×** |
| `timing training_seconds` (3000 steps) | 3986.54 |
| `timing steps_per_second` | 0.75 |
| `timing total_seconds` | 4160.18 |

### Where the time actually goes

| Phase | Seconds | % of run |
|---|---|---|
| Tokenizer build (incremental) | 5.74 | 0.14% |
| Training (3000 steps) | 3986.54 | ~96% |
| Total | 4160.18 | 100% |

Swapping the **naive** tokenizer back in would put it at ~163s of a ~4317s run
— ~3.8%, still nowhere near the training cost. Training dwarfs tokenization by
~24×.

## The training bottleneck is CPU, not tokenization (and not a missing KV-cache)

Training runs at **0.75 steps/s** because each step is a full forward+backward
over a batch=32 × context=256 block through the ~1M-param model on the
`t3.small`'s 2 burstable vCPUs — dense CPU matmuls, nothing more. `train()`
does one parallel `model(x)` forward per step (`src/train.py:100`) with
attention computing all 256 positions at once behind a causal mask
(`src/attention.py:70`); there is no autoregressive per-token loop in training,
so a KV-cache would not help here — that is a `generate.py` (autoregressive
sampling) optimization, orthogonal to training throughput. The levers for
faster training are hardware (GPU), batch/model/context size, or step count.

## Quality: held against 002?

_Model (RoPE), corpus, `num_merges`, optimizer, and seed identical to 002 — the
only change is the tokenizer algorithm._

| Metric | 002 (naive tokenizer) | 003 (incremental) | Δ |
|---|---|---|---|
| Step-0 `val_loss` (untrained) | 7.0456 | 7.0467 | ~same |
| Best `val_loss` | 3.7795 (step 1750) | **3.7864 (step 1750)** | +0.007 |
| Final `val_loss` (step 2999) | 4.3126 | 4.2940 | −0.019 |
| Final `train_loss` (step 2999) | 2.6205 | 2.6467 | +0.026 |

Best val lands at the **exact same step (1750)** and all deltas sit well inside
single-batch validation noise. Quality is unchanged.

## Vocab drift check

`bench_tokenizer.txt` → `merges_identical: **False**`, both learning exactly
**750** merges. So the intentional tie-break drift genuinely produced a
*different* vocabulary — and the model still reached the same loss trajectory.
This is the clean confirmation that the "accept drift" decision was safe:
different learned merges, indistinguishable model quality. (Corollary: a
retrained `tokenizer.json` is not byte-identical to 002's, as flagged in
`src/merge_state.py`.)

## Success criteria (from mission.md)

- [x] Incremental materially faster than naive — 25.9× (163s → 6s)
- [x] `tokenizer_build_seconds` a small fraction of `training_seconds` — 5.74s
      vs 3986s (0.14% of the run)
- [x] Final `train_loss` within noise of 002 (2.62) — 2.65
- [x] Best `val_loss` comparable to 002 (3.78) — 3.79, same step
- [ ] Generation sample not drawn this pass — model arch is byte-identical to
      002 and the loss matches, so output is expected equivalent; can be
      sampled from the saved checkpoint if a qualitative check is wanted

## Learnings / surprises

- **The premise was wrong, and only instrumentation showed it.** 001 flagged
  the naive tokenizer as the run's slowest part; measured, it was ~4% of
  wall-clock. The likely source of the mis-estimate is *perceptual*: the naive
  build hangs silently for ~163s before any `step` line prints, so it feels
  far longer than the visibly-progressing training that follows. Lesson:
  instrument before optimizing — the felt bottleneck and the measured
  bottleneck were different things. (001's results.md has been annotated with
  this correction.)
- **The optimization is still worth keeping.** It removes a ~157s fixed cost
  per run (faster iteration) and, more importantly, replaces an O(merges ×
  corpus) loop with O(occurrences per merge) — the naive cost would balloon on
  a larger corpus or higher `num_merges`, where it *could* become a real
  bottleneck. This run just isn't at that scale.
- **Tie-break drift is quality-neutral in practice.** A fully different learned
  vocab (750 merges, `merges_identical: False`) produced the same best/final
  loss at the same steps. Worth remembering the next time exact vocab
  reproducibility is weighed against a tokenizer refactor.
- **Real next lever is training throughput, not tokenization.** At 0.75
  steps/s on the `t3.small`, a run is ~70 min of training. That — CPU-bound
  dense matmuls — is where wall-clock actually lives.
