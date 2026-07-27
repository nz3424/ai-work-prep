# 004 — Activation Outliers & the Residual Stream (quantm study)

> **⚠️ This is a `quantm-learning` study artifact, not an experiment template.**
>
> Experiments 004–006 exist to *measure* the already-trained `002-rope`
> checkpoint in service of the theory track at
> `~/ClaudeProjects/quantm-learning/`. They are read-only instrumentation: no
> training run, no hypothesis-vs-baseline A/B, no code change to `src/`.
>
> **Do not base structural experiments on this folder or its layout.** Work
> that changes the model or the pipeline — a RoPE swap, the BPE corpus-scan
> optimization, an architecture or hyperparameter change — should follow the
> convention established by `001-first-training-run`, `002-rope`, and
> `003-incremental-tokenizer`: a `mission.md` stating the hypothesis, baseline
> and success criteria up front, a real training/benchmark run, a
> `source_archive/`, and a `results.md` with the head-to-head numbers. This
> folder deliberately has none of those, because there is nothing to A/B.

## What this measures

Registers forward hooks on every attention output and every `TransformerBlock`
residual output, runs one 16×256 tinyshakespeare batch through the trained
`checkpoints/002-rope` model, and records per-dimension activation statistics.

Two questions, both from Unit 3 Module 3 (outlier activations / LLM.int8()):

1. Does this model have **systematic outlier feature dimensions** — the
   phenomenon that makes naive INT8 destroy transformer accuracy?
2. Does the residual stream's dynamic range **grow with depth**, as a parked
   note from Unit 1 claimed?

## Findings

**No outlier dimensions, at any layer.** The largest dimension is ~1.4× the
median dimension, and the top-3 hottest dims reshuffle almost completely from
layer to layer (21/98/114 → 124/126/103 → 65/43/118 → 74/19/88). That
reshuffling is the diagnostic: real outlier features are *systematic*, the same
dim indices everywhere. At ~0.8M params this model is four orders of magnitude
below the ~6.7B threshold where Dettmers et al. observe the phase transition.

**Residual range is flat with depth**: absmax 4.43 → 3.66 → 3.73 → 3.80 → 3.58.
A single static scale calibrated on the embedding gives 81–86% range
utilization at every later layer, with zero clipping — so the parked Unit 1
claim was wrong. Pre-LN caps each sublayer's contribution (every sublayer reads
`LayerNorm(x)`, not `x`, so nothing compounds), contributions add in quadrature
rather than linearly, and four layers is too shallow to show even sqrt growth.

Revised conclusion: **the residual-stream quantization problem is per-dimension,
not per-depth.**

## Running it

```sh
PYTHONPATH=. python3 experiments/004-activation-outliers/activation_stats.py
```

Output as of the committed run is in `activation_stats.txt`.
