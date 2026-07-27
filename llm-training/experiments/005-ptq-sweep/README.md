# 005 — Post-Training Quantization Bit-Width Sweep (quantm study)

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

Quantizes every body `nn.Linear` weight in the trained `checkpoints/002-rope`
model at a range of bit widths — fake-quant (quantize then dequantize back to
float, so the model still runs in FP32) — and measures validation loss on 20
fixed batches. Pure PTQ: no retraining, no calibration beyond reading the
weights themselves.

Note this is **weight-only, data-free PTQ** — the weakest tier of the PTQ
family. Activations run in FP32 throughout; GPTQ/AdaRound-style error
compensation would do meaningfully better at INT3–INT4.

Also enumerates every `nn.Linear` a `BitLinear` conversion would touch.

## Findings

FP32 baseline: **val loss 4.198 / ppl 66.6**. Uniform-random over the
1006-token vocab would be ppl 1006.

```
scheme             granularity    val loss       ppl    vs FP32
INT8 absmax        per-tensor       4.1988      66.6    +0.0009
INT6 absmax        per-tensor       4.2063      67.1    +0.0084
INT4 absmax        per-tensor       4.4925      89.3    +0.2945
INT3 absmax        per-tensor       5.6654     288.7    +1.4674
INT3 absmax        per-channel      4.9343     139.0    +0.7363
ternary absmax     per-tensor       7.4278    1682.1    +3.2298
ternary absmean    per-tensor       6.4407     626.8    +2.2427
```

- **The cliff is between INT6 and INT4**, not at INT8. INT8 costs 0.0009 — not
  "small", *nothing*.
- **INT2 signed and ternary absmax are byte-identical.** With `q_max=1`, INT2
  rounds to {-1,0,1} and never reaches its 4th code — a 2-bit signed format
  *is* ternary with a wasted code, hence `log2(3) = 1.58`.
- **Granularity is not a substitute for bits.** Per-channel halves the damage
  at INT4/INT3 and buys nothing at ternary (+2.24 → +2.23).
- **absmean beats absmax by a full 1.0 nats at ternary** — see 006 for why.
- **Loss is not monotone in precision**: quantizing the LM head *as well* gave
  *lower* loss (5.755 vs 6.441), because cross-entropy punishes confident
  wrongness and a ternary head compresses logits toward uniform. Watch for this
  when using loss to pick a quantization config.

**Punchline: you cannot PTQ your way to ternary.** Perplexity 627 is not a
starting point you fine-tune out of — which is the empirical reason BitNet
trains from scratch in low precision rather than converting a trained model.

Conversion-site inventory: 24 body Linears / 786,432 params (75% of the model);
`head` and `token_embedding` held out at 128,768 each. The 75% is pessimistic —
vocab 1006 vs `d_model=128` makes embeddings unusually heavy here; at
`d_model=4096` the body is >95% of params.

## Running it

```sh
PYTHONPATH=. python3 experiments/005-ptq-sweep/ptq_sweep.py
```

Output as of the committed run is in `ptq_sweep.txt`.
