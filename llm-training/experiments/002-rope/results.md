# Experiment 002: RoPE vs. Absolute Position Embeddings — Results

## Outcome

**Hypothesis held, with a wrinkle.** Swapping absolute position embeddings
for RoPE (every other hyperparameter and the seed held identical to 001) both
trained substantially better *and* reached a better best-validation loss —
and got there roughly 1000 steps sooner. The wrinkle: RoPE's stronger fitting
capacity means it also *overfits sooner*, so by the end of the full 3000 steps
its train/val gap is much wider than the absolute-embedding baseline's.

## Head-to-head numbers

| Metric | 001 (absolute) | 002 (RoPE) | Δ |
|---|---|---|---|
| Step-0 val (untrained) | 7.0682 | 7.0456 | ~same |
| **Final train_loss** (step 2999) | 3.5306 | **2.6205** | **−0.91** |
| **Best val_loss** | 4.1101 (step 2750) | **3.7795 (step 1750)** | **−0.33** |
| Final val_loss (step 2999) | 4.2274 | 4.3126 | +0.09 |
| Final train/val gap | ~0.70 | ~1.69 | wider |

(Both runs: `d_model=128`, 4 layers, 4 heads, ~1006-token BPE vocab,
`context_length=256`, `lr=3e-4`, 3000 steps, `seed=0`, tinyshakespeare.)

## Reading the curves

- **RoPE fits the training data far better** — final train loss 2.62 vs 3.53.
  Injecting relative-position information at *every* attention layer (rather
  than adding a single absolute-position vector once at the input) gives the
  model more usable capacity to model position-dependent structure.
- **RoPE also generalizes better at its best point** — min val 3.78 vs 4.11,
  and it reaches that minimum at **step ~1750 vs ~2750**: more sample-efficient.
- **But RoPE overfits past its sweet spot.** After ~step 1750–1800 its val
  loss drifts back up (3.78 → 4.31 by step 2999) while train keeps falling.
  The absolute-embedding model, fitting more weakly, never pulled as far ahead
  on train and so showed a gentler ~0.70 end-gap vs RoPE's ~1.69.
- **Takeaway for this scale:** the generalization win is real but lives in the
  first ~1750 steps. At this tiny model/corpus size, early stopping (or fewer
  steps / light regularization) captures RoPE's advantage; running the full
  3000 steps overshoots into memorization. The final-step val point (4.31) is
  *not* the number to quote for RoPE — its best (3.78) is, and it beats 001's
  best (4.11) clearly.

## Sample generation

Prompt `"ROMEO:"`, `max_new_tokens=200`, `temperature=1.0`, no top_k,
`seed=0`, sampled from the final (step-2999) checkpoint:

```
ROMEO: the pot of form,
Norfolk of my honest last;
And now I can what famixle
Is father that roar'd off. We are old sons a met: here's fortainten
Upon the sin, and ream for ever brought upon
More welcomed child. But, might executioner,
York and DackA:
And I thank thee so mild, be country!

ESCALUS:
Nigh domilly to my good deed, my captain!
It shept levines, nineward; where is the fippearest death;
Not dagger, that a banish'd in pewWoes is done:
Fared of greets b being strea
```

Qualitatively a step up from 001's sample at the same settings: it reproduces
*real* Shakespeare character names (`Norfolk`, `York`, `ESCALUS`), keeps the
`CHARACTER:`-on-its-own-line play formatting cleanly, and carries archaic
flavor (`roar'd`, `banish'd`, `thee`). Garbled invented tokens remain
(`famixle`, `fortainten`, `domilly`) — expected at ~1M params — but the
linguistic structure is visibly tighter than the absolute-embedding run.
(Sampled from the step-2999 checkpoint, which is past the val minimum, so
it slightly under-sells what an early-stopped RoPE checkpoint would produce.)

## Success criteria (from mission.md)

- [x] Run completed 3000 steps on the fleet with the RoPE model
- [x] Final train_loss at/below the 001 baseline — 2.62 vs 3.53, clearly below
- [x] val_loss + gap compared head-to-head — best val better (3.78 vs 4.11),
      but end-of-run gap wider (RoPE overfits sooner)
- [x] Generation coherent and comparable-or-better than 001 — better

## Learnings / surprises

- The single *final* val point was misleading: RoPE's step-2999 val (4.31) is
  slightly *worse* than 001's (4.23), which at a glance reads as "RoPE didn't
  help." Looking at the whole trajectory flips that — RoPE's *best* val (3.78)
  is a clear win. Lesson: for a noisy single-batch val estimate, compare the
  minima / trajectory, not the last step.
- RoPE's better fit is a double-edged sword at this scale: more capacity to
  learn structure also means more capacity to memorize, so the model that
  generalizes best also overfits fastest. The right follow-up is an
  early-stopping / step-count sweep rather than more steps.
- This run predates the timing instrumentation (added right after launch), so
  its `training.log` has no `timing` lines — wall-clock for 002 isn't captured.
  Every experiment from 003 on (and any re-run of 002) records it automatically.
