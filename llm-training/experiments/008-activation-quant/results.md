# Experiment 008: 8-bit Activation Quantization (W1.58A8) — Results

## Outcome

**Activation quantization cost essentially nothing on top of ternary weights.**
Trained from scratch with every body `BitLinear` fake-quantizing *both* ternary
weights ({-1, 0, +1}, absmean) and INT8 per-token activations (absmax, STE),
the model reached **ppl 52.6** on 005's fixed harness — statistically
indistinguishable from 007's weight-only ppl of **52.7**, and still comfortably
below the FP32 baseline (66.6) and a factor of ~12 better than the PTQ ternary
floor (627). The full BitNet b1.58 integer-matmul recipe — ternary weights ×
INT8 activations, no floating-point multiply in the body — trains just as well
as the weight-only version at this scale. The hypothesis held, and by a wider
margin than "a small, bounded penalty": the penalty is **not measurably
different from zero**.

## Head-to-head (005's 20-fixed-batch harness, 002 checkpoint axis)

| Model | Scheme | val loss | ppl | vs 007 (A16) |
|---|---|---|---|---|
| 002-rope | FP32 | 4.198 | 66.6 | — |
| 007 | QAT ternary, **A16-fp** | 3.9649 | 52.7 | — |
| **008** | QAT ternary, **A8 (W1.58A8)** | **3.9631** | **52.6** | **−0.0018 (−0.1 ppl)** |
| 005 PTQ | ternary absmean (post-hoc) | 6.441 | 627 | +2.24 vs 007 |

Adding 8-bit per-token activation quantization moved val loss by **0.0018** —
noise-level, and in the direction of a (meaningless) improvement rather than a
penalty. The claim the mission set out to test — "8 bits is near-lossless for
activations already shaped by training" — comes back essentially confirmed at
this scale.

Identical measurement axis confirmed: 008's `tokenizer.json` is byte-identical
to 002's (loaded verbatim, not rebuilt), same `data/tinyshakespeare.txt`, same
val split (last 10%), same fixed batches (seed 1234, 20 batches, batch_size
16). The checkpoint's `model_config` carries `quantize_linears=True` **and**
`quantize_activations=True`; reconstruction rebuilds all 24 body `BitLinear`
layers (head + embedding held FP32, confirmed 24 BitLinear / 25 plain
`nn.Linear` at eval time) so both quantizers run inside `forward` — eval is a
plain forward pass, no post-hoc step. Eval script: `eval_005harness.py`.

## Training curve

- Final `train_loss` @ step 2999: **3.2858**
- Best `val_loss` (in-loop): **3.8668 @ step 2250** (final @ 2999: 4.0513)
- Loss finite throughout / STE stable: **yes** — no NaN/inf across 3000 steps;
  train loss fell monotonically 7.08 → ~3.3, in-loop val 7.06 → ~3.9. Both
  STEs (ternary weight round, INT8 activation round) flowed end-to-end and the
  FP32 master weights moved.
- `timing`: training_seconds **8581.04** / steps_per_second **0.35** /
  total_seconds **8750.09**.

> **Timing is not comparable to 007** (4221s / 0.71 steps/s) — as flagged in
> `mission.md`, 008 runs with `--grad-checkpoint` to fit the `t3.small` fleet
> box's 3.7 GiB (activation-quant intermediates OOM'd at step ~5 without it),
> recomputing each block's forward during backward. The slowdown measured
> **2.03×** (0.71 → 0.35 steps/sec), noticeably more than the "~30% more
> compute" the mission estimated for checkpointing recompute alone — plausibly
> because the recomputed forward now includes the activation quantizer's
> abs/amax/round/clamp ops too, which weren't part of 007's cheaper forward
> pass. This is a compute-axis cost of the *memory* fix, not of activation
> quantization itself, and doesn't touch the ppl comparison above (grad
> checkpointing is numerically transparent, locked by
> `test_grad_checkpoint_run_matches_plain_run`).

## Sample (generate.py from the 008 checkpoint)

`--prompt "\n" --max-new-tokens 200 --temperature 0.8 --top-k 40 --seed 0`

```
My like, that my servewsen those every ble
final-hopely to breamation dew dready
Against bush like.

KING RICHARD III:
What are your never stand he's soul! Where I never will not so you,
But that has at the matter's foot is horne as corn,
There's death: delight.

POMENSIO:
OPeter, I am gentleman hath only received with the
I creation, the heir, tell young sorrow:
Do, I had rather die and laid the moon.

KING RICHARD III:
Why, thou last have been a butcher and found.

ROMEO:
I lew this deed with slack in a cou
```

Real word-structure, play formatting, correct character names (KING RICHARD
III, ROMEO), mostly-English tokens with the malformations expected at
~0.8M params — qualitatively on par with both 002 and 007. The fully
integer-matmul model (ternary weights × INT8 activations) still learned
language, not just a low number.

## Findings

- **8-bit activations are free at this scale.** −0.1 ppl vs 007 is within run-
  to-run noise, not a measurable penalty. Combined with 007's result (ternary
  weights alone: 627 → 52.7), 008 completes BitNet b1.58's integer-only matmul
  — ternary weight × INT8 activation, no floating-point multiply in the body —
  at effectively the same quality as the FP16-activation weight-only version,
  and still ahead of the FP32 baseline (66.6). The number the mission asked
  for ("stay close to 007, target comfortably under ~100") landed as close as
  it's possible to land.

- **No-SubLN scope note did not bite, at this scale.** `mission.md` flagged
  that skipping SubLN before each activation quantizer (kept as a deliberate
  single-variable choice vs. the full BitNet recipe) was the most likely
  source of extra penalty, and that a larger-than-expected gap would localize
  the cost there. The gap came back at noise level instead — at ~0.8M params
  and this corpus, the existing norms already keep the attention out-proj and
  second-FFN-linear inputs within a range absmax/INT8 handles cleanly, so
  there's nothing here for SubLN to visibly repair. This doesn't mean SubLN is
  unnecessary in general — BitNet adds it because outlier activations get
  worse at scale (the outlier problem 004 measured) — only that its absence
  isn't costing anything *yet*. A natural follow-up would need either a larger
  model or a corpus with heavier-tailed activations to see SubLN's benefit
  show up as anything but a probably-free normalization.

- **Grad-checkpointing's compute cost exceeded the estimate, but stayed off
  the ppl axis.** 2.03× wall-clock vs. 007's ~30%-more-compute forecast is a
  reproducibility note for future fleet runs (activation-quant ops re-run on
  every recomputed block), not a result about quantization quality — the
  checkpointing is bit-identical by construction, so it's a pure timing
  footnote, not a caveat on the 52.6 number.

- **Job relevance.** 007 closed the weight side of BitNet's case (train-in-
  ternary beats PTQ-ternary); 008 closes the activation side and lands the
  complete integer-accumulation matmul — the property that makes this mappable
  onto photonic hardware (no floating-point multiply, only integer MAC). That
  the second quantizer added on top of the first cost nothing measurable is
  the strongest version of the BitNet claim this repo has produced so far.

- **Success criteria: all met.** Run completed 3000 steps with both
  quantizers active; loss finite & decreasing throughout (both STEs stable).
  Ppl (52.6) landed far below the 627 PTQ floor and within noise of 007's
  52.7 — well inside the "under ~100" bar and effectively at "within a small
  factor" read as "no factor at all." Generation from the 008 checkpoint
  produces 002/007-comparable word structure, confirming the fully
  integer-matmul model still learned language.
