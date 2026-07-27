# Experiment 007: QAT + STE Ternary Weights — Results

> Skeleton — fill in after the fleet run completes.

## Outcome

_(one-paragraph verdict: did QAT rescue the ternary collapse?)_

## Head-to-head (005's 20-fixed-batch harness, 002 checkpoint axis)

| Model | Scheme | val loss | ppl | vs FP32 |
|---|---|---|---|---|
| 002-rope | FP32 | 4.198 | 66.6 | — |
| 007 | **QAT ternary (STE)** | _TBD_ | _TBD_ | _TBD_ |
| 005 PTQ | ternary absmean (post-hoc) | 6.441 | 627 | +2.24 |

Gap closed: _(627 → ? out of 627 → 66.6)_

## Training curve

- Final `train_loss` @ step 2999: _TBD_
- Best `val_loss` (in-loop): _TBD_
- Loss finite throughout / STE stable: _TBD_
- `timing`: tokenizer_encode _TBD_ / training_seconds _TBD_ / steps_per_second _TBD_

## Sample (generate.py from the 007 checkpoint)

```
_TBD_
```

## Findings

_(what the number means; connect back to 006's "fine ranking" damage — did QAT
repair the neuron ordering PTQ shuffled? and to the job: this is the from-scratch
low-precision training that BitNet does because PTQ can't reach ternary.)_
