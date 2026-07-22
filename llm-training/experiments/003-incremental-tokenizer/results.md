# Experiment 003: Incremental BPE Tokenizer — Results

> SKELETON — fill in after the fleet run. Sources for each field are noted in
> _italics_. Delete this blockquote once complete.

## Outcome

_One paragraph: did the tokenizer build get materially faster, and did model
quality hold within noise of 002? State the headline speedup and whether
final loss regressed. TBD._

## Speed: before vs after

_From `bench_tokenizer.txt` (naive vs incremental on the same box) and the
`timing` lines in `training.log`._

| Metric | Value |
|---|---|
| Corpus | tinyshakespeare.txt (~1.12M chars) |
| `num_merges` | 750 |
| Naive tokenizer build (s) | TBD |
| Incremental tokenizer build (s) | TBD |
| **Speedup** | **TBD×** |
| `timing training_seconds` (3000 steps) | TBD |
| Tokenizer build as % of total run — before | TBD% |
| Tokenizer build as % of total run — after | TBD% |

_001 flagged the naive build as slower than the 3000 training steps. Confirm
whether the incremental build is now a negligible fraction instead._

## Quality: held against 002?

_From `training.log` (final/best loss) vs experiment 002's `results.md`._

| Metric | 002 (naive tokenizer) | 003 (incremental) | Δ |
|---|---|---|---|
| Final `train_loss` (step 2999) | 2.6205 | TBD | TBD |
| Best `val_loss` | 3.7795 (step ~1750) | TBD | TBD |
| Final `val_loss` (step 2999) | 4.3126 | TBD | TBD |

_Model (RoPE), corpus, num_merges, optimizer, and seed are identical to 002 —
the only change is the tokenizer algorithm. Differences should be within
run-to-run noise; anything larger needs explaining below._

## Vocab drift check

_The intentional caveat: tie-break order differs, so the learned vocab may
differ from 002's `tokenizer.json`._

- `bench_tokenizer.txt` → `merges_identical`: TBD (True / False)
- Merge count: naive TBD vs incremental TBD (should match)
- If the vocab differs: does the loss difference track the vocab difference, or
  is loss unchanged despite a different vocab? _Note which._

## Sample generation

_Prompt `"ROMEO:"`, `max_new_tokens=200`, `temperature=1.0`, no top_k,
`seed=0`, from the final (step-2999) checkpoint. Paste sample + one-paragraph
qualitative read vs 002. TBD._

```
TBD
```

## Success criteria (from mission.md)

- [ ] `bench_tokenizer.py` shows incremental materially faster than naive
- [ ] `tokenizer_build_seconds` a small fraction of `training_seconds`
- [ ] Final `train_loss` within noise of 002 (2.62), or gap explained by drift
- [ ] Best `val_loss` comparable to 002 (3.78)
- [ ] Generation quality comparable to 002

## Learnings / surprises

- _TBD — e.g. actual speedup vs the O(occurrences) expectation, whether the
  tie-break drift changed the vocab at all, and whether that moved the loss._
