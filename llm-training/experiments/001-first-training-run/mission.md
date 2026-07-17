# Experiment 001: First Training Run

## Hypothesis

Training the from-scratch TinyTransformer (`d_model=128`, 4 layers, 4 heads,
~750-merge BPE vocab, `context_length=256`) on the full tinyshakespeare
corpus for 3000 steps will bring training loss from the untrained baseline
(~`ln(vocab_size)` ≈ 6.6 for a ~750-token vocab) down to a noticeably lower
value, and `generate.py` sampling from the resulting checkpoint will produce
text with real word boundaries and some archaic/Shakespearean vocabulary or
phrasing, even if not fully coherent at this model size.

## Success criteria

- [ ] Final training loss is well below the ~6.6 untrained baseline
- [ ] Validation loss tracks training loss without diverging sharply (no
      severe overfitting at this scale/step count)
- [ ] `generate.py` sampling from the final checkpoint produces text with
      recognizable English word structure, not random character noise

## Run

See `run_fleet.sh` for the exact command and hyperparameters (also captured
verbatim in `training_config.txt` after the run). Executed per the workflow
in `docs/superpowers/specs/2026-07-14-llm-training-fleet-design.md`.
