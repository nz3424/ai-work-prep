# Experiment 007: QAT + STE Ternary Weights (BitLinear)

## Hypothesis

Training the model **from scratch in low precision** — every body `nn.Linear`
replaced by a `BitLinear` that fake-quantizes its weights to ternary
({-1, 0, +1}, BitNet b1.58 absmean) on each forward, with a straight-through
estimator carrying the gradient to full-precision master weights — will
**dramatically beat the post-training ternary collapse** that experiment 005
measured, closing most of the gap back to the FP32 baseline.

This is the payoff experiments 004–006 set up. 005 proved you *cannot PTQ your
way to ternary* (ppl 627); 006 localized the damage to the *fine ranking* of
FFN neurons — "exactly the damage QAT exists to repair, which no choice of scale
rule can fix." 007 builds that repair and measures whether it works.

Controlled A/B: the **only** variable vs 002-rope is `nn.Linear → BitLinear`
on the 24 body projections. Same corpus, same tokenizer (002's, loaded
verbatim), same `d_model=128 / 4 layers / 4 heads`, `context_length=256`,
`batch_size=32`, `lr=3e-4`, `seed=0`, 3000 steps. `head` and `token_embedding`
stay FP32 (BitNet convention; 005 showed quantizing the head makes loss
non-monotone).

## Baselines (both measured on the 002-rope checkpoint)

- **FP32 (002-rope):** val loss **4.198 / ppl 66.6** — the ceiling.
- **PTQ ternary absmean (005):** val loss **6.441 / ppl 627** — the floor QAT
  must beat. "Not a starting point you fine-tune out of."
- Untrained (`ln(vocab)`, ~1006 tokens): ppl ~1006.

> **Measurement-axis note.** The 66.6 / 627 numbers come from 005's eval: 20
> fixed batches through the 002 checkpoint. To place 007 on the *same* axis, do
> **not** just read `train.py`'s in-loop `val_loss` (different eval set). After
> the run, evaluate the 007 checkpoint with 005's 20-fixed-batch harness — the
> BitLinear layers already fake-quantize in `forward`, so this is a plain
> forward pass, no extra PTQ step. That exp(val_loss) is the number to compare.

## Success criteria

- [ ] Run completes 3000 steps on the fleet with the quantized model; loss
      stays **finite** (no NaN/inf) and decreases — evidence the STE flows and
      the FP32 master weights are moving.
- [ ] 007 ppl (005 harness) lands **far below the 627 PTQ floor**, closing most
      of the 627 → 66.6 gap — target comfortably **under ~150**. At ~0.8M params
      we won't *match* FP the way BitNet does at 3B+, but "PTQ can't, QAT can"
      must show clearly.
- [ ] Sanity (optional, cheap): a short `--quantize-linears` run with the
      `int8_absmax` quant_fn trains to near-FP loss, confirming the STE harness
      is correct independent of ternary difficulty.
- [ ] `generate.py` sampling from the 007 checkpoint produces word-structure
      comparable to 002 — a qualitative check the ternary model learned language,
      not just a low number.

## Run

`run_fleet.sh` — hyperparameters identical to 002-rope; only the quantize flag,
the loaded tokenizer, checkpoint/S3 paths, and experiment id differ. Fetches
002's `tokenizer.json` from S3 first so the vocab is byte-identical to the
002/004/005/006 axis. Must run with the 007 `BitLinear` code (this branch, or
after it merges to `main`) checked out on the fleet.
