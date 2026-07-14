# llm-training

**Maps to:** Track 3 (added 2026-07-14) — see `../GOALS.md` for full context and
current priority order.

## Goal

Get hands-on, *in-practice* understanding of how an LLM is actually trained —
tokenization, attention, activation layers, the training loop — by building a
small transformer from scratch rather than only reading about one. Then, as a
stretch goal, quantize its weights to ternary ({-1, 0, 1}) following BitNet
b1.58 as a starting point.

**Why this track exists:** the upcoming role involves training an LLM with
ternary weight quantization. The company's broader goal is to use ternary
weights — whose matrix multiplication reduces to integer addition, with no
multiplication required — to make photonics the primary compute substrate
instead of GPUs. BitNet b1.58 is the cited inspiration, not necessarily the
exact target architecture.

## Reference material

- `docs/bitnet-b1.58-2402.17764.pdf` — Ma et al. (Microsoft Research / UCAS),
  "The Era of 1-bit LLMs: All Large Language Models are in 1.58 Bits"
  (arXiv:2402.17764). Introduces BitNet b1.58: every weight is ternary
  {-1, 0, 1} via absmean quantization (`RoundClip(W/(γ+ε), -1, 1)`, `γ` = mean
  abs weight), replacing `nn.Linear` with `BitLinear`, trained from scratch
  with 8-bit activations. Matches FP16 Transformer perplexity/end-task
  performance from ~3B params up, while cutting memory/latency/energy —
  because matmul becomes integer addition instead of floating-point
  multiply-add. That's the property that opens the door to photonic hardware.

## Tasks

**Core — train a transformer from scratch**
- [ ] Build a tokenizer (understand BPE/subword tokenization in practice, not
      just call a library)
- [ ] Implement a minimal Transformer block from scratch: embeddings,
      multi-head self-attention, feed-forward/activation layers, layer norm,
      residual connections
- [ ] Write the training loop (loss, backprop, optimizer) and train on a small
      dataset (tiny Shakespeare-scale corpus or similar) to convergence on a
      laptop/single GPU
- [ ] Be able to explain, from having built it, what each piece (tokens,
      attention, activations) is actually doing and why

**Stretch — ternary weight quantization (BitNet b1.58-style)**
- [ ] Implement a `BitLinear`-equivalent layer with absmean ternary
      quantization on top of the from-scratch model
- [ ] Compare quantized vs. full-precision model: perplexity, memory
      footprint, and (conceptually) why the matmul is now multiplication-free
- [ ] Write up, in your own words, why multiplication-free matmul is the
      specific property that makes ternary weights attractive for photonic
      hardware (light-based hardware handles addition/accumulation well but
      multiplication poorly)

## Status

Not started as of 2026-07-14 — track just added.

## Notes

(Log training-run results, gotchas, and quantization-accuracy tradeoffs here
as you go.)
