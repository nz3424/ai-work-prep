# Experiment 001: First Training Run — Results

## Outcome

**Hypothesis held.** All three success criteria from `mission.md` were met.

## Final loss

- `train_loss` at step 2999: **3.5306**
- `val_loss` at step 2999: **4.2274**
- Untrained baseline (`ln(vocab_size)` for the ~1006-token vocab): ~6.9

Both well below baseline — the model clearly learned structure from the
corpus rather than staying near a uniform-distribution guess.

## Loss curve (val vs. train)

From step 1400 to 2999, `train_loss` fell steadily (4.02 → 3.53) while
`val_loss` stayed roughly flat/noisy in the 4.1-4.5 range, bottoming out
around step 2750-2900 (~4.11-4.14) before ticking back up slightly to 4.23
by the end. The train/val gap widened gently over the run (~0.4 early,
~0.6-0.7 late) — a mild generalization gap, not a sharp divergence. No
runaway overfitting at this step count/scale.

## Sample generation

Prompt: `"ROMEO:"`, `max_new_tokens=200`, default sampling (temperature=1.0,
no top_k):

```
ROMEO: gyehead?

BRUT:
Why, smak you, need,
So it not noteddoubled bon ever,
To have will mine eyes him, my love
Letestable gire, markind your growsand valt, with the gate,
To lood and years he bold enganishment:
He is my lord, --deed as I spto his night.

Lord Anger,
Your to usurpoor Heof!

FRIAR LAURENCE:
I pray father, they banish, grief, whilst thou pargar amome to have made bell.
Even have we gay retten med,
Is my to the weve out of our,
To seciring and born.
I will abity cle me p
```

Real, correctly-spelled English words dominate, word boundaries and
capitalization are solid throughout, and the model reproduced the corpus's
play-script formatting (`CHARACTER:` on its own line followed by dialogue —
see `BRUT:`, `FRIAR LAURENCE:`, `Lord Anger,`) along with archaic flavor
(`thou`, `whilst`). Mixed in with genuine invented/garbled tokens
(`gyehead`, `noteddoubled bon`, `pargar amome`) — not fully coherent, as
expected for a ~1M-parameter model, but unmistakably real linguistic
structure rather than character noise.

## Learnings / surprises

- The model picked up document-level structure (speaker-label formatting)
  purely from a byte-level BPE vocabulary with no built-in notion of
  grammar or dialogue — that structure had to be learned entirely from
  the attention/FFN layers picking up on the repeated `NAME:\n` pattern
  in the corpus.
- The from-scratch BPE tokenizer's naive merge-learning loop (full corpus
  rescan per merge, no incremental pair-count bookkeeping) was the
  slowest part of the run by a wide margin — noticeably slower than the
  3000 training steps that followed it.
- A plain `pip install torch` on the fleet instance pulled the CUDA-enabled
  build and its `nvidia-*-cu12` dependency wheels, which overflowed the
  box's small RAM-backed `/tmp` (`tmpfs`) even though the root volume had
  plenty of free space. Installing the CPU-only wheel
  (`--index-url https://download.pytorch.org/whl/cpu`) fixed it and is
  the right choice anyway for a GPU-less instance.
