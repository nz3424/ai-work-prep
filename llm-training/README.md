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

- `../../quantm-learning/` — a separate, standalone study track (theory
  only, no code) covering transformers, activations/normalization,
  quantization fundamentals, QAT+STE, and BitNet/ternary specifics in
  depth. Read through it before/alongside the Core tasks below — it's the
  "why" behind what you're about to build here.
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
- [x] Implement a `BitLinear`-equivalent layer with absmean ternary
      quantization on top of the from-scratch model (exp 007, `src/ternary_quant.py`)
- [x] Compare quantized vs. full-precision model: perplexity, memory
      footprint, and (conceptually) why the matmul is now multiplication-free
      (exp 005 PTQ sweep + exp 007 QAT)
- [ ] Write up, in your own words, why multiplication-free matmul is the
      specific property that makes ternary weights attractive for photonic
      hardware (light-based hardware handles addition/accumulation well but
      multiplication poorly)

## Status

Core and Stretch both landed (as of 2026-07-27). The from-scratch stack
(tokenizer, transformer, training loop) is built and trained, and the ternary
quantization stretch goal is complete through experiment 007. Per-experiment
missions, results, and eval harnesses live in `experiments/NNN-*/`.

Headline quantization result (all on the same 20-fixed-batch axis, 002
checkpoint): FP32 baseline **ppl 66.6**; post-training ternary (005) collapses
to **ppl 627** — you cannot PTQ your way to ternary; QAT-from-scratch with STE
(007, `BitLinear`) recovers to **ppl 52.7**, *below* the FP32 baseline. That is
BitNet's thesis in miniature — train in low precision, don't quantize after.

Architecture exploration beyond the ternary track: **exp 010** swaps the dense
FFN for a top-2-of-4 routed **Mixture of Experts** (compute-matched, FP32,
Switch/GShard load-balancing). Load balancing worked cleanly (all 4 experts
~evenly used, no collapse), but the 4× FFN params overfit the tiny corpus — val
bottomed at **ppl ~43** (step 1200, beating the 66.6 dense baseline) then rose to
a shipped **ppl 118.5**. Lesson: capacity without data overfits; **exp 011**
(bigger corpus + vocab, own dense baseline) is the room-to-specialize follow-up.

Infra: the `llm-training-fleet` Terraform plan (`terraform/`, `fleet/`) is fully
built and applied on AWS — dedicated VPC, EC2 training box (`t3.small`; the
design's `t3.medium` default is blocked by this account's Free Tier
restriction), S3 checkpoint bucket, and `fleet_start.sh`/`fleet_stop.sh`/
`fleet_ssh.sh` — verified end-to-end and stopped when idle.

## Notes

Agent operating rules for this track — the fleet dependency installer,
experiment layout, the `-m src.train` invocation gotcha, and the `*token*`
gitignore caveat — live in `CLAUDE.md`.

(Log training-run results, gotchas, and quantization-accuracy tradeoffs here
as you go.)
