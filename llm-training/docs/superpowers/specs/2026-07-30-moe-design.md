# Exp 010 — Mixture of Experts (dense-FFN → routed MoE-FFN)

**Date:** 2026-07-30
**Status:** Design approved, pre-implementation
**Track:** llm-training (Track 3) — see `../../../README.md`
**Chains off:** 002-rope FP32 baseline (val loss 4.198 / ppl 66.6)

## Goal

Get hands-on with the mechanics of Mixture of Experts by replacing the dense
feed-forward network in each `TransformerBlock` with a **router + pool of expert
FFNs**, then measuring — as a controlled A/B — whether routed specialists beat a
single generalist FFN at this scale.

The learning target is the *mechanism*: watch the router produce gate logits,
see top-2 expert selection, see the softmax-weighted combination of expert
outputs, and watch the load-balancing auxiliary loss keep experts from
collapsing onto a single winner. The trained-checkpoint + perplexity result is
the destination; tracing the mechanics is a checkpoint along the way.

## Workflow

Guide-and-review pairing (this track's default, see memory
`hands-on-coding-preference`): Claude outlines the steps and writes the tests;
Nick writes the load-bearing implementation (`src/moe.py` and the wiring),
asking for guidance along the way. TDD: tests first (red), Nick implements to
green.

## Design decisions (all resolved during brainstorming)

| Fork | Decision | Why |
|---|---|---|
| Routing | **Top-2 of 4 experts** (GShard/Mixtral style) | Shows the softmax-weighted combine that top-1 hides; 4 experts keeps a training signal per expert at tiny scale |
| A/B framing | **Compute-matched** | Each expert = one dense FFN (`d_ff=512`); top-2 ⇒ ~2× dense FFN FLOPs/token, ~4× FFN params. The standard MoE motivation ("scale params, not per-token compute"). Params deliberately **not** matched — stated in mission.md |
| Load balancing | **Switch/GShard aux loss**, coefficient `α=0.01` | The mechanic that makes MoE trainable; `α=0` witnesses collapse for free |
| Dispatch | **Compute-all-then-mask** (no capacity/dropping) | Trivially correct, fully vectorized, every intermediate printable. True sparse dispatch + capacity deferred to a later efficiency experiment |
| Quantization | Experts built via `make_linear`, but **`quantize_linears=False`** this run | Composes with the ternary track (future one-flag "ternary MoE") at zero cost today; keeps training time down. Router always FP32 |

## Architecture

### Config additions (`ModelConfig`)

```python
use_moe: bool = False        # exp 010 sets True; False keeps the 002-rope dense path byte-for-byte
n_experts: int = 4
top_k: int = 2
moe_aux_loss_coef: float = 0.01   # α; set 0.0 to witness router collapse
```

When `use_moe=False`, `TransformerBlock` builds the existing dense FFN exactly
as today. Nothing about experiments 001–009 changes.

### Components (each a small, independently testable unit)

- **Router** — `nn.Linear(d_model, n_experts, bias=False)`, always **FP32**
  (routers are tiny and precision-sensitive; kept full-precision even in future
  ternary follow-ups). Output: gate logits `(T, n_experts)`.
- **Experts** — `nn.ModuleList` of `n_experts` FFNs, each identical in shape to
  the dense FFN: `make_linear(d_model→d_ff) → GELU → make_linear(d_ff→d_model)`.
  Built via `make_linear` so a future flag makes them ternary;
  `quantize_linears=False` for this run.

### Data flow — compute-all-then-mask

```
x: (B, S, d_model)  ──flatten──▶  (T, d_model)              T = B*S
gate_logits = router(x)                        # (T, n_experts)
gate_probs  = softmax(gate_logits, dim=-1)     # (T, n_experts)
topv, topi  = gate_probs.topk(k=top_k, dim=-1) # (T, top_k) each
topv        = topv / topv.sum(-1, keepdim=True)     # renormalize the kept top_k
weights     = zeros(T, n_experts).scatter_(1, topi, topv)   # (T, n_experts), sparse
out = Σ_e  weights[:, e:e+1] * expert_e(x)     # run all experts, weight-combine
reshape out ──▶ (B, S, d_model)
```

The `weights` matrix `(T, n_experts)` is the entire routing story in one printable tensor.

### Load-balancing auxiliary loss (Switch/GShard)

Computed inside the MoE layer from the same forward pass:

- `f_i` = fraction of tokens that selected expert *i* in their top-k
- `P_i` = mean full-softmax probability mass on expert *i*
- `aux = n_experts · Σ_i f_i · P_i`

Each MoE layer stashes its `aux` on itself. `TinyTransformer` gains a
`collect_moe_aux_loss()` helper that sums-and-clears across all layers and
returns `0.0` when `use_moe=False`.

**`forward()` still returns only logits** — so `generate.py` and the 005
20-fixed-batch eval harness are untouched, keeping the A/B eval axis identical.
Only `train.py` calls `collect_moe_aux_loss()` after the forward and adds
`α · aux` to the loss.

## Instrumentation (the mechanics checkpoint)

- **Trace script** `experiments/010-moe/trace_routing.py`: feed one toy batch,
  print gate logits, top-2 picks, the `weights` matrix, and per-expert token
  counts. Run this *before* trusting a 3000-step run.
- **During training**: log per-expert routing fractions `f_i` and the aux loss
  separately at each eval interval, to watch experts equalize (or collapse at
  α=0).

## The controlled A/B

- **Only variable:** dense FFN → MoE FFN. Same corpus, same 002 tokenizer loaded
  verbatim, same `d_model=128 / 4 layers / 4 heads`, `context_length=256`,
  `batch_size=32`, `lr=3e-4`, `seed=0`, 3000 steps, FP32.
- **Eval on the same axis:** after the run, score the checkpoint with 005's
  20-fixed-batch harness → `exp(val_loss)` is the comparable number.
- **Baseline:** 002-rope FP32 — val loss **4.198 / ppl 66.6**.
- `mission.md` states explicitly that params are **not** matched (compute-matched) and why.

### Success criteria

- [ ] Run completes 3000 steps with the MoE model; loss decreases monotonically.
- [ ] No dead expert — all `f_i > 0`, roughly balanced by end of training.
- [ ] Aux loss logged and observably keeping balance (vs α=0 collapse).
- [ ] MoE ppl measured on the 005 axis and reported honestly vs 66.6.

> **Interpretation note.** At this tiny scale (~1000-token vocab, small corpus),
> MoE may **not** beat the dense baseline — 4 experts are dividing a very small
> pie. The point of exp 010 is the *mechanism built correctly + measured on the
> same axis*, not a guaranteed win. Exp 011 scales the corpus to give experts
> room to specialize.

## Follow-ups (noted, not built now)

- **Exp 011:** fresh dense baseline + MoE on a **bigger corpus + vocab**, where
  specialization can actually emerge (can't chain off 002-rope — needs its own
  retrained dense baseline on the same larger corpus).
- Later: true sparse dispatch + capacity factor / token dropping (the
  production efficiency path).
- Later: ternary experts (`quantize_linears=True`) — routed integer-add matmul,
  directly on-mission for the photonic-substrate goal.

## Testing (TDD — written first)

`tests/test_moe.py`:

- Shape preservation `(B,S,d) → (B,S,d)`.
- Exactly `top_k` experts have nonzero weight per token.
- Kept gate weights sum to 1 per token.
- Unselected experts contribute 0 to the output.
- Aux loss is a non-negative scalar.
- `use_moe=False` still builds and runs the dense path unchanged.

## Files

- **New:** `src/moe.py`, `experiments/010-moe/{mission.md, trace_routing.py, results.md}`, `tests/test_moe.py`
- **Modified:** `src/transformer.py` (config fields, block FFN selection, `collect_moe_aux_loss`), `src/train.py` (aux loss + per-expert logging)
