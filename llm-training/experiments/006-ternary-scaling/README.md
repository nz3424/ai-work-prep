# 006 — Absmax vs Absmean in the Ternary Regime (quantm study)

> **⚠️ This is a `quantm-learning` study artifact, not an experiment template.**
>
> Experiments 004–006 exist to *measure* the already-trained `002-rope`
> checkpoint in service of the theory track at
> `~/ClaudeProjects/quantm-learning/`. They are read-only instrumentation: no
> training run, no hypothesis-vs-baseline A/B, no code change to `src/`.
>
> **Do not base structural experiments on this folder or its layout.** Work
> that changes the model or the pipeline — a RoPE swap, the BPE corpus-scan
> optimization, an architecture or hyperparameter change — should follow the
> convention established by `001-first-training-run`, `002-rope`, and
> `003-incremental-tokenizer`: a `mission.md` stating the hypothesis, baseline
> and success criteria up front, a real training/benchmark run, a
> `source_archive/`, and a `results.md` with the head-to-head numbers. This
> folder deliberately has none of those, because there is nothing to A/B.

## What this measures

Four things on the trained `checkpoints/002-rope` weights:

1. Where weights land under ternarization with `s = mean|W|` vs `s = max|W|`.
2. What a single injected outlier does to each rule.
3. The concrete memory win of ternary-packed weights, for this model and for a
   LLaMA-7B-shaped config.
4. Whether ternarizing the FFN up-projection blurs *which* detector neuron
   fires — a thread parked in Unit 1.

## Findings

### `s` is a survival threshold, not a step size

A weight becomes ±1 only if `|w| > s/2`; everything else becomes 0. So a badly
chosen `s` gives you an **empty** matrix, not a coarse one.

```
tensor / rule                       s        -1       0      +1   nonzero
W1 (ffn up-proj)   absmean     0.0521    36.7%   27.2%   36.0%    72.8%
W1 (ffn up-proj)   absmax      0.2017     4.8%   90.4%    4.8%     9.6%
```

**The primary argument for absmean is entropy, not outlier robustness.**
absmean lands near-even across three codes (~1.58 bits of content); absmax
lands 4.8/90.4/4.8 (~0.6 bits). Same storage either way — absmax spends it
transmitting a third of the content.

Also note absmax gets *worse as tensors grow*: `max|W|` rises with tensor size
(more chances at an extreme draw) while `mean|W|` is stable.

### One outlier at 20× collapses absmax entirely

```
rule        s before    s after   nonzero before   nonzero after
absmean       0.0521     0.0521           72.8%           72.7%
absmax        0.2017     4.0345            9.6%            0.0%
```

Every weight rounds to zero; the layer outputs its bias and nothing else. At 8
bits an outlier costs resolution — at ternary it costs the entire tensor.

### Memory: the ratio tracks how embedding-heavy the model is

```
toy model  (d_model=128,  vocab=1006)   body 75.3%   FP16 2.09 MB → 0.71 MB   2.93x
LLaMA-7B   (d_model=4096, vocab=32000)  body 96.1%   FP16 13476 MB → 2143 MB  6.29x
```

The toy model only reaches 2.93× because **72% of the compressed file is the
held-out embedding + head**. At 7B that drops to 24%. This is the mechanism
behind the BitNet paper's Figure 2 curve (2.93× at 1.3B → 7.16× at 70B).

**Caveat:** this is weights-only math, an *upper bound*. The paper measures
4.40× at 7B because runtime GPU memory includes the KV cache and activation
buffers, which stay FP16 and don't shrink.

### Parked Unit 1 thread: hypothesis inverted, mechanism confirmed

```
                     cos sim   kurtosis   corr(kurtosis, cos sim)
attention.q_proj      0.8977     2.65            -0.786
attention.out_proj    0.9047     2.47            -0.764
ffn.0  (W1)           0.9152     2.22            -0.789   ← best
```

- The FFN up-projection survives ternarization **better** than every attention
  projection, not worse.
- The proposed mechanism is confirmed: peaky rows suffer more,
  `corr(kurtosis, cos sim) ≈ -0.8` in every tensor.
- The assumption was wrong: `ffn.0` has the *lowest* kurtosis. It wins on
  exactly the axis the hypothesis named, from the other side of it.
- Why: **the FFN's sparsity is in its activations, not its weights.** Neurons
  are silent because GELU gates them, not because their rows are sparse.

Firing overlap on real tokens (512 FFN neurons):

```
top-8   preserved 58.7%  (chance 1.6%)
top-64  preserved 73.8%  (chance 12.5%)
```

Overlap **rises** with k, so the ternary matrix finds the right *neighbourhood*
of neurons and shuffles the ordering within it. Coarse routing survives; fine
ranking doesn't — which is exactly the damage QAT exists to repair, and which
no choice of scale rule can fix.

## Running it

```sh
PYTHONPATH=. python3 experiments/006-ternary-scaling/ternary_scaling.py
```

Output as of the committed run is in `ternary_scaling.txt`.
