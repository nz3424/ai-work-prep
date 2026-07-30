# Experiment 010: Mixture of Experts (dense FFN → routed MoE FFN)

## Hypothesis

Replacing each block's **single dense FFN** with a **pool of 4 expert FFNs and a
top-2 router** — every token softmax-routed to its 2 best experts, their outputs
combined by the (renormalized) gate weights, and a Switch/GShard load-balancing
auxiliary loss keeping the experts from collapsing onto one winner — lets the
model allocate different FFN "specialists" to different tokens instead of forcing
one generalist to cover everything.

Whether that *helps at this scale* is the open question, and the honest expectation
is **it may not**. With a ~1000-token vocab and a small corpus, 4 experts are
dividing a very small pie; each expert sees fewer tokens per step than the dense
FFN did, so specialization has little room to emerge. The purpose of 010 is the
**mechanism built correctly and measured on the same axis** — routing, top-2
combine, and load balancing that provably works — not a guaranteed perplexity win.
Exp 011 (bigger corpus + vocab) is where specialization can actually pay off, and
needs its own retrained dense baseline.

Controlled A/B: the **only** variable vs 002-rope is the block FFN — dense
`nn.Sequential` → `MoEFeedForward`. Same corpus, same tokenizer (002's, loaded
verbatim), same `d_model=128 / 4 layers / 4 heads`, `context_length=256`,
`batch_size=32`, `lr=3e-4`, `seed=0`, 3000 steps, FP32. Router is FP32
`nn.Linear`; experts are built via `make_linear` but run FP32 this experiment
(`quantize_linears=False`).

## Compute-matched, not param-matched

Each expert is **identical in shape to the dense FFN** (`d_ff=512`). This is a
deliberate *compute-matched* comparison:

- **Per-token FFN compute:** top-2 means each token passes through 2 experts, so it
  does ~**2×** the dense FFN's FLOPs. (The compute-all-then-mask implementation
  runs all 4 experts per token and masks, so wall-clock is ~4× the dense FFN — an
  implementation cost, not the conceptual compute; true sparse dispatch is a
  deferred efficiency follow-up.)
- **Parameters:** the FFN sub-layers hold **~4×** the parameters of the dense model
  (4 experts + a tiny router); attention, embeddings, and head are unchanged.

So params are **not** matched — this asks "for roughly comparable per-token FFN
work, does a pool of specialists beat one generalist?", the standard MoE framing.
Any ppl change is therefore attributable to routing *and* the extra capacity
together; that caveat is the point of stating it here.

## Baseline

- **FP32 (002-rope):** val loss **4.198 / ppl 66.6** — measured on 005's
  20-fixed-batch harness. The reference this A/B is read against.
- Untrained reference (`ln(vocab)`): ppl ≈ vocab size.

> **Measurement-axis note.** The 66.6 number comes from 005's eval: 20 fixed
> batches through the 002 checkpoint. To place 010 on the *same* axis, do **not**
> just read `train.py`'s in-loop `val_loss` (different eval set). After the run,
> evaluate the 010 checkpoint with 005's 20-fixed-batch harness — the MoE layer is
> a plain forward pass, no extra step. That `exp(val_loss)` is the number to
> compare. The in-loop `expert_frac` / `aux` logs are for watching balance during
> training, not for the headline ppl.

## Success criteria

- [ ] Run completes 3000 steps with the MoE model; loss stays **finite** and
      decreases monotonically — evidence the router + experts train together.
- [ ] **No dead expert.** The logged `expert_frac` shows every expert with a
      nonzero token share, roughly balanced (ideal ≈ 0.5 each for top-2-of-4), and
      `aux` stays low/stable rather than climbing.
- [ ] 010 ppl measured on the **005 harness** and reported honestly vs 66.6 — a
      loss (higher ppl) at this scale is an expected, documented outcome, not a
      failure of the implementation.
- [ ] **Collapse demo (cheap, high-value):** a second short run with
      `--moe-aux-loss-coef 0` should show `expert_frac` splitting toward
      `[~1, ~1, ~0, ~0]` and `aux` rising — the direct evidence that the aux loss
      is what prevents collapse.
- [ ] `generate.py` sampling from the 010 checkpoint produces word-structure
      comparable to 002 — a qualitative check the routed model learned language.

## Run

`run_fleet.sh` — hyperparameters identical to 002-rope; only `--use-moe`
(+ `--n-experts 4 --top-k 2 --moe-aux-loss-coef 0.01`), the loaded tokenizer,
checkpoint/S3 paths, and experiment id differ. Fetches 002's `tokenizer.json`
from S3 first so the vocab is byte-identical to the 002 axis. Must run with the
010 MoE code (this branch, or after it merges to `main`) checked out on the fleet.
Copy the run scaffolding from the most recent `experiments/NNN-*/` so the
`fleet/install_deps.sh` (CPU-only torch) call and `-m src.train` invocation are
inherited.
