# Design — Experiment 007: QAT + STE Ternary Weights (`BitLinear`)

**Date:** 2026-07-27
**Track:** llm-training (Track 3) — stretch goal: BitNet b1.58-style ternary quantization
**Status:** design approved, pending spec review → implementation plan

## Motivation

Experiments 004–006 established the empirical case for this experiment:

- **005** proved you *cannot PTQ your way to ternary*: post-training ternary
  quantization of the trained `002-rope` weights gives **ppl 627** (absmean,
  per-tensor) vs the **ppl 66.6** FP32 baseline — "not a starting point you
  fine-tune out of."
- **006** localized the damage: ternarization finds the right *neighbourhood*
  of FFN neurons but shuffles the fine ranking within it — "exactly the damage
  QAT exists to repair, which no choice of scale rule can fix."

007 builds the quantization-aware training (QAT) machinery that repairs that
damage: a `BitLinear` layer whose weights are fake-quantized to ternary during
training, with a Straight-Through Estimator (STE) so gradients flow to the
full-precision master weights. It answers one question: **does training from
scratch in low precision rescue the ternary collapse that PTQ could not?**

## Scope

**In scope (007):**
- Weights-only ternary quantization (BitNet b1.58 absmean, eqs (1)–(3)).
- STE on the weights.
- `BitLinear` swapped in for the 24 body `nn.Linear`s; embeddings + head held
  out in FP32.
- A single-variable A/B against the existing `002-rope` FP baseline.

**Out of scope (deferred):**
- **008** — 8-bit per-token activation quantization + SubLN (a second STE on
  the activation path; the output-side scale seam is built now so this is an
  extension, not a refactor).
- **009 (parked, requested)** — swap our architecture toward BitNet's
  LLaMA-alike components: **RMSNorm** (vs our LayerNorm), **SwiGLU** (vs GELU),
  and **no biases**. Orthogonal to the weight-quantization lesson; deferred so
  007 isolates one variable, but explicitly wanted as a follow-up.

## The core mechanism (the learning centerpiece)

**Fake quantization.** Weights stay FP32 in memory and the matmul stays FP32,
but the *value* used in the forward pass is snapped to the ternary grid. The
model feels quantization error during training while still running in plain
float on the GPU-less box.

**Straight-Through Estimator (STE).** `round()` has zero gradient almost
everywhere, which would kill learning. STE forwards the quantized value but
passes the gradient straight through the rounding as if it were the identity:

```python
def ste_round(x):
    # forward: round(x);  backward: d/dx = 1
    return x + (x.round() - x).detach()
```

The `(x.round() - x)` cancels on the forward pass (value = `round(x)`); it is
`.detach()`-ed to zero gradient on the backward pass, so the gradient flows
through the bare `x`. The FP32 master weights accumulate real gradients and
drift toward values that survive ternarization.

## The quantizer — exactly BitNet b1.58 eqs (1)–(3)

```
W̃ = RoundClip( W / (γ + ε), -1, 1 )
RoundClip(x, a, b) = max(a, min(b, round(x)))
γ = (1/nm) Σ_ij |W_ij|         # per-tensor mean absolute value
```

Verified line-for-line against `docs/bitnet-b1.58-2402.17764.pdf`:

| Paper | Code | Match |
|---|---|---|
| `γ = (1/nm) Σ|W_ij|` (per-tensor mean-abs) | `w.abs().mean()` | exact |
| `W / (γ + ε)` | `w / (gamma + eps)`, ε inside denominator | exact |
| `RoundClip(·,-1,1) = max(-1, min(1, round(·)))` | `.round().clamp(-1, 1)` (round then clip) | exact |

Design choices, each backed by our own 004–006 findings:
- **absmean, not absmax** — 006: absmax spends storage on ~0.6 bits of content
  vs absmean's ~1.58, and one 20× outlier collapses the whole tensor to zero.
- **per-tensor scale** — matches the paper; 006 showed per-channel buys nothing
  at ternary (+2.24 → +2.23).
- **pluggable `quant_fn`** — ternary is the default; an `int8_absmax` variant
  exists purely as the STE-correctness sanity path (see success criteria).

### Representation choice (ii): keep W̃ and γ separate

Equation (1) defines `W̃ ∈ {-1,0,+1}` as the *bare ternary matrix*; the scale γ
reappears at the **matmul output**, not folded into the weight. Because γ is a
per-tensor scalar, `W̃·γ` (folded) and `γ·(W̃x)` (output-side) are
mathematically identical for a linear layer — but we implement the **separate**
form:

```
y = γ · (W̃ @ x)          # scale applied at the output
```

Rationale: this is the paper's / deployment's actual data path, and the
output-side multiply is the exact seam where the **activation scale** joins in
008: `y = (γ_w · γ_x) · (W̃ @ x̃)`. Keeping them separate now makes 008 an
extension rather than a refactor.

STE placement: the STE wraps the **RoundClip** (the non-differentiable step);
the scale γ is a separate scalar applied at the output. Whether the gradient is
allowed to flow through γ (which itself depends on `W` via `mean|W|`) vs
detaching it is an implementation detail to settle during coding — the
`int8_absmax` sanity test will catch a wrong choice.

## The `BitLinear` layer

`class BitLinear(nn.Linear)` — a subclass so it is swap-compatible everywhere an
`nn.Linear` lives. Only `forward` changes:

1. Compute `W̃` via `ste`-wrapped `RoundClip` and `γ = mean|W|` (per-tensor).
2. `y = γ * F.linear(x, W̃, bias=None)`; add bias afterward if present.

The constructor takes a `quant_fn` (default ternary absmean) so bit-width is one
argument, not a fork in the code.

## What gets quantized (hold-out)

Quantize the **24 body Linears** (attention q/k/v/out_proj + both FFN
projections) — the inventory 005 enumerated (786,432 params, 75% of the model).
**Hold `token_embedding` and `head` in FP32**, matching BitNet and backed by
005's warning that quantizing the head made loss *non-monotone* (a ternary head
compresses logits toward uniform and cross-entropy rewards it for the wrong
reason). One config flag; the two held-out modules stay plain `nn.Linear` /
`nn.Embedding`.

## Integration

- Add a `quantize_linears: bool = False` field to `ModelConfig` (FP path is
  byte-identical when off — the baseline is unaffected).
- `TransformerBlock` and `CausalSelfAttention` construct `BitLinear` instead of
  `nn.Linear` for body projections when the flag is set (a small `make_linear`
  helper keyed off config keeps the swap in one place). `head` and
  `token_embedding` never consult the flag.
- `train.py` gains a `--tokenizer-path` **load** option: 007 must *reuse
  002's `tokenizer.json`* rather than rebuild, because 003 showed the
  incremental BPE loop's tie-break drift changes the learned vocab. Reusing
  002's tokenizer keeps 007 on the exact measurement axis as 004–006.

## Experiment 007 as an A/B

Anchored to **002**: same tokenizer, corpus, config, seed, and **3000 steps** —
the only variable is `nn.Linear → BitLinear`.

| Run | What | ppl |
|---|---|---|
| FP32 baseline | 002-rope (existing) | 66.6 |
| PTQ-ternary floor | 005 (existing) | 627 |
| **QAT-ternary** | **007 (this run)** | **?** |

Follows the `mission.md` convention (001–003): hypothesis + baselines + success
criteria stated up front, a real training run, a `source_archive/` snapshot,
and a `results.md` with the head-to-head numbers.

## Success criteria

1. **Primary** — QAT-ternary ppl lands *dramatically* below the 627 PTQ floor,
   closing most of the 627 → 66.6 gap (target: comfortably under ~150). At
   ~0.8M params we will not *match* FP the way BitNet does at 3B+, but
   "PTQ can't, QAT can" must show clearly.
2. **Stability** — loss decreases, no NaNs, and the FP32 master weights visibly
   move (evidence STE is actually flowing gradient).
3. **Sanity** — the `int8_absmax` `quant_fn` variant trains to near-FP loss,
   proving the STE harness is correct independent of ternary's difficulty.

## Deliverables

- `src/quant.py` — `ste`, `ternary_absmean`, `int8_absmax`, and `BitLinear`.
- `ModelConfig.quantize_linears` flag + `make_linear` wiring in
  `transformer.py` / `attention.py`.
- `train.py --tokenizer-path` load option.
- Unit tests: STE gradient is identity; ternary quantizer matches eqs (1)–(3)
  on hand-checked inputs; `BitLinear` forward equals `γ·(W̃x)`; FP path
  unchanged when flag off.
- `experiments/007-qat-ternary/`: `mission.md`, `run_fleet.sh` (copied from the
  most recent structural experiment so it inherits the shared installer +
  `-m src.train` invocation + S3 upload), `source_archive/`, `results.md`.

## What this translates to at the job

Built, not read: fake-quant, the STE `.detach()` idiom, absmean/RoundClip, the
`BitLinear` swap pattern — and a *measured* PTQ-vs-QAT gap that justifies why
BitNet trains from scratch. The layer is structured so 008 (activation quant)
and 009 (LLaMA-alike architecture) are clean extensions.
