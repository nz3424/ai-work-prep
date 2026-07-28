# Experiment 008: 8-bit Activation Quantization (W1.58A8, full BitNet recipe)

## Hypothesis

Adding **8-bit per-token absmax activation quantization** on top of 007's
ternary-weight QAT — so every body `BitLinear` fake-quantizes *both* its weights
(ternary, {-1, 0, +1}) *and* its input activations (INT8) on each forward, with
straight-through estimators carrying gradient to the FP32 master weights — will
hold perplexity **close to 007** (a small, bounded penalty), completing BitNet
b1.58's actual **W1.58A8** recipe. 8 bits is near-lossless for activations that
have already been shaped by training, so the activation-quant cost should be
far smaller than the ternary *weight* cost QAT had to repair in 007.

This is the second half of BitNet. 007 built the weight side (train-in-ternary
beats PTQ-ternary, 627 → 52.7). 008 adds the activation side, landing the
complete integer-only matmul: **ternary weights × INT8 activations → integer
multiply-accumulate**, no floating-point multiply. That integer-accumulation
property is exactly what makes the matmul mappable onto photonic hardware.

Controlled A/B: the **only** variable vs 007 is **8-bit activation
quantization** inside `BitLinear`. Same corpus, same tokenizer (002's, loaded
verbatim), same `d_model=128 / 4 layers / 4 heads`, `context_length=256`,
`batch_size=32`, `lr=3e-4`, `seed=0`, 3000 steps. Weights stay ternary QAT
exactly as 007. `head` and `token_embedding` stay FP32 (BitNet convention).

## Scope note — no SubLN (deliberate single-variable discipline)

BitNet's full recipe inserts a normalization (SubLN/RMSNorm) *before* the
activation quantizer to tame outliers (the outlier problem 004 measured). We
**deliberately do not add SubLN here** — that would be a *second* variable and
break the clean "only activation quant changed vs 007" attribution. 008
quantizes the activation as-presented (per-token absmax), reusing the norms the
from-scratch model already has. If 008 shows a larger-than-expected penalty,
that localizes the cost to *missing SubLN* and sets up a natural 009. Honest
scope beats a flattering number.

## Activation quantizer (per-token absmax INT8)

Following BitNet: for input `x` of shape `(..., in_features)`, scale per token
(the last, feature dim) by its own absmax so each token uses the full INT8
range:

    gamma = x.abs().amax(dim=-1, keepdim=True)      # per-token, NOT per-tensor
    s     = gamma / 127
    x_q   = ste_round(x / (s + eps)).clamp(-127, 127) * s   # fake-quant, real-valued

Per-token (not per-tensor like the existing `int8_absmax` weight helper) is the
BitNet choice and the point of the experiment — one row-varying scale, applied
across the sequence, so a single outlier token can't crush the range for all
the others. `ste_round` is the existing straight-through round; gradient flows
as identity so the FP32 activations upstream still train.

### Design notes (secondary)

**Fidelity to BitNet b1.58.** The paper quantizes activations per-token to a
symmetric range `[−Q_b, Q_b]` (`Q_b = 2^(b−1)`) via absmax, deliberately
dropping the zero-point ("to get rid of zero-point quantization … negligible
effects"). 008 matches that intent exactly — per-token, symmetric, absmax, no
zero-point. Two deviations: **(1)** we scale by `γ/127` (reusing the repo's
existing INT8 convention) where the paper uses `γ/128` — one quantization
level, <1% of range; **(2)** BitNet inserts a normalization (SubLN/RMSNorm)
immediately before each activation quantizer; we do not (see scope note above),
so the attention out-projection and the post-GELU second FFN linear quantize an
un-renormalized input. (1) is negligible; (2) is the deliberate single-variable
choice and the most likely source of any extra penalty.

**Weight vs activation scale — static vs dynamic.** Both the ternary weight
scale and the INT8 activation scale factor cleanly out of the matmul (the
integer `W_int @ x_int` is the real work; scales apply after). The asymmetry is
*when they're known*: the weight scale is one scalar per matrix, fixed at load
time; the activation scale is a per-token vector computed live from each token's
absmax, so it can't be pre-folded. That's why `int8_activation` returns its
input already dequantized rather than a `(codes, scale)` pair — in fake-quant
training there's no integer matmul to feed, so the folded form is just the
readable one, and it composes cleanly with the weight fake-quant.

## Memory note — gradient checkpointing

Activation quant adds activation-sized (`batch × seq × d`) intermediates that
autograd retains for backward across all 24 body layers — enough extra live
memory to OOM the `t3.small` fleet box (3.7 GiB, no swap) at step ~5 on the
first attempt. Fix: `--grad-checkpoint` recomputes each block's activations in
backward instead of storing them. It is **numerically transparent** (same
forward, deterministic blocks, no dropout → bit-identical loss curve and
gradients — locked by `test_grad_checkpoint_run_matches_plain_run`), so the
008-vs-007 **ppl** comparison is unaffected. The **only** cost is ~30% more
compute, so 008's `timing` line (steps/sec, wall-clock) is **not** directly
comparable to 007's — note this in `results.md`; the ppl axis is what matters.

## Baselines (all on 005's 20-fixed-batch harness, 002 checkpoint axis)

- **007 (W1.58, A16-fp):** val loss **3.9649 / ppl 52.7** — the ceiling 008
  should stay near. Activation quant is the only thing added.
- **002-rope (FP32):** val loss **4.198 / ppl 66.6** — full-precision reference.
- **005 PTQ ternary:** val loss **6.441 / ppl 627** — the floor; 008 must stay
  far below it.

> **Measurement-axis note.** As in 007, do **not** read `train.py`'s in-loop
> `val_loss` (different eval set). After the run, evaluate the 008 checkpoint
> with 005's 20-fixed-batch harness. The checkpoint's `model_config` carries
> both `quantize_linears=True` and `quantize_activations=True`, so
> reconstruction rebuilds `BitLinear` layers that fake-quantize weights *and*
> activations in `forward` — eval is a plain forward pass, no post-hoc step.

## Success criteria

- [ ] Run completes 3000 steps with both weight- and activation-quant active;
      loss stays **finite** (no NaN/inf) and decreases — STE flows through both
      quantizers and the FP32 master weights move.
- [ ] 008 ppl (005 harness) stays **far below the 627 PTQ floor** and
      **close to 007's 52.7** — target comfortably **under ~100**, ideally
      within a small factor of 52.7. The claim to demonstrate: *8-bit
      activations cost little on top of ternary weights.*
- [ ] `generate.py` from the 008 checkpoint still produces 002/007-comparable
      word-structure — the fully-integer-matmul model still learned language.

## Run

`run_fleet.sh` — hyperparameters identical to 007; only `--quantize-activations`
is added and the experiment/checkpoint/S3 ids differ. Fetches 002's
`tokenizer.json` from S3 first so the vocab is byte-identical to the
002/004/005/006/007 axis. Must run with the 008 activation-quant code
(this branch, or after merge to `main`) checked out on the fleet.
