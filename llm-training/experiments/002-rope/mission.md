# Experiment 002: RoPE vs. Absolute Position Embeddings

## Hypothesis

Replacing the learned absolute position embedding with Rotary Position
Embeddings (RoPE) — while holding every other hyperparameter identical to
experiment 001 (`d_model=128`, 4 layers, 4 heads, ~750-merge BPE vocab,
`context_length=256`, `lr=3e-4`, 3000 steps, `seed=0`) — will train at least
as well as the absolute-embedding baseline, and plausibly reach a slightly
lower loss and/or generalize a touch better (smaller train/val gap), because
RoPE injects relative-position information at every attention layer rather
than adding a single absolute-position vector at the input.

This is a controlled A/B: the **only** difference from experiment 001 is the
positional-encoding mechanism (code change on the `rope-positional-embeddings`
branch). Same corpus, same tokenizer settings, same optimizer, same seed.

## Baseline to beat (experiment 001, absolute embeddings)

- `train_loss` @ step 2999: **3.5306**
- `val_loss` @ step 2999: **4.2274**
- Train/val gap late in the run: ~0.6–0.7
- Untrained baseline (`ln(vocab_size)`, ~1006-token vocab): ~6.9

## Success criteria

- [ ] Run completes 3000 steps on the fleet with the RoPE model
- [ ] Final `train_loss` is at or below the 001 baseline (≤ ~3.53), or if
      higher, the difference is small and explainable
- [ ] `val_loss` and train/val gap compared head-to-head with 001 — note
      whether RoPE narrows or widens the generalization gap
- [ ] `generate.py` sampling from the RoPE checkpoint produces coherent
      English word structure comparable to (or better than) 001's samples

## Run

`run_fleet.sh` — identical hyperparameters to `001-first-training-run`, only
the checkpoint/S3 paths and experiment id differ. Must be executed with the
`rope-positional-embeddings` branch (or after it merges to `main`) checked out
on the fleet, so the RoPE code path is the one under test.

## Results

See `results.md` after the run.
