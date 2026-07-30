# 009 — Bonsai activation quant + QAT study — results

Ternary-weight Bonsai (0.5B) already ships as **W1.58A16** (ternary weights,
full-precision activations). This study ports 8-bit activation quant to reach
the full **W1.58A8** BitNet recipe, then probes how Bonsai quantizes weights and
does QAT. Apple Silicon / MPS. Scripts in this dir.

## 1. Activation quantization (W1.58A16 → W1.58A8)

`quant_a8.py` swaps every `QLinear` for a `QLinearA8` subclass (via
`module.__class__` reassignment — no param copy, cache untouched) whose forward
adds per-token INT8 absmax fake-quant on the activations, flag-gated so the same
model flips A16↔A8. 112 layers swapped (7 projections × 16 blocks; `lm_head`
stays full precision).

**Result: A8 is nearly free.** Logits stay finite (absmax 18.4 vs A16's 18.9),
generations stay coherent, and only diverge from A16 on lower-confidence tokens.

## 2. Bit-width cliff (`measure_a8.py --bits N`)

| bits | logit absmax | quality |
|------|-------------|---------|
| A16  | 18.9 | reference |
| A8   | 18.4 | coherent; mild trajectory shifts |
| A5   | ~17  | **fluent but factually WRONG** ("capital of Italy" → "Sardinia") |
| A4   | 15.9 | word salad |

**Lesson:** the dangerous failure is not obvious garbage (A4) — it's confident,
grammatical wrongness (A5). Eyeballing text won't catch it; you need a metric.

**Methodology note:** compare schemes under **greedy** decoding only. A *sampled*
A5 run answered "Rome" by luck; greedy exposed the fact as actually broken.

## 3. How Bonsai quantizes weights

Inspecting a real weight tensor: values are **already exactly {-1, 0, +1}**
(mean|w| = 0.586), and all magnitude lives in a learned per-output-channel
`self.scales` (mean 0.032) applied post-matmul.

Consequences:
- The weight-quant STE in the forward is a **no-op at inference** (weights already
  on the grid).
- Swapping the weight-quant scheme (clamp-round ↔ absmean) changes **nothing** at
  inference. It only matters during training → i.e. it is a QAT question.
- **clamp-round** (Bonsai): fixed 0.5 threshold, scale-blind. **absmean**
  (canonical BitNet): normalize by mean|w| first, adaptive threshold. Bonsai's
  learned scale is why the cheaper clamp-round suffices.

## 4. Weight-QAT — the STE, and why it stalls on Bonsai

`qat_demo.py` (1-layer toy, fit a random target with ternary weights):
- **The STE learns** — loss 110 → 16 with a hard ternary `round` in the forward.
  Kept a full-precision master weight, quantized on-the-fly each step.
- With a learned scale present, clamp-round ≈ absmean. They only diverge in
  stressed regimes (no scale / wrong scale). A frozen `s=5` wrecked both
  (loss 190 vs 1234) — clamp-round fought back via sparsity; absmean couldn't.
- STE is **self-healing**: a layer that quantizes to all-zeros still gets gradient
  to its masters (identity backward) and revives.

`qat_finetune.py` (weight-QAT on real Bonsai, perplexity):
- **Stalls.** Masters start at ternary bin *centers* (0.5 from any boundary). The
  STE pins the forward output within a bin, so `lr=1e-4` → flat loss (nothing
  crosses a threshold); `lr=0.5` → mass bin-flips, perplexity explodes to 5.4e6.
- **This is why quantized models are finetuned with LoRA** — a continuous,
  full-precision adapter sidesteps the discrete staircase entirely.

## 5. Capstone — can LoRA recover activation-quant damage? (`lora_qat.py`)

Break Bonsai with A5 (fluent-but-wrong), LoRA-finetune **with the quant on** (base
ternary weights frozen; only the continuous adapter moves), and measure recovery.
A matched **A16 no-quant control** (`--no-quant`) separates instruction-tuning
from genuine quant recovery. 60 steps, batch 1 × accum 4, max_len 128, float32.

### The 2×2 (perplexity on EVAL_TEXT; generation quality)

|            | No LoRA                                   | + LoRA                                              |
|------------|-------------------------------------------|-----------------------------------------------------|
| **A16**    | 6.95 — broken (echoes the prompt)         | 7.34 — correct: "Rome", "Paris", "red/yellow/blue" ✓ |
| **A5**     | 11.22 — broken (wrong facts)              | 10.88 — right format, "red/yellow/green" ✗           |

### Decomposition

- **LoRA effect** (across a row): A16 6.95→7.34 (+0.39), A5 11.22→10.88 (−0.34).
  Generations go broken→clean in BOTH rows. → LoRA's job is **instruction-tuning
  (answer format)**; its perplexity effect is tiny (±0.4), independent of quant.
- **Quant penalty** (down a column): +4.27 without LoRA, +3.54 with LoRA. The
  ~+4 perplexity damage dominates and stays open either way.
- **Quant recovery (diff-in-diff):** LoRA narrowed the quant gap by 4.27−3.54 =
  **0.73 ppl ≈ 17% of the damage.** Modest and real, but 83% remains.

### Conclusions

1. **LoRA teaches the model how to *answer*, not how to be *right* under quant.**
   The flashy "Rome/Paris" recovery is instruction-tuning — the A16 control with
   ZERO quantization produces the same answers.
2. **Generations mislead; perplexity is honest.** A5+LoRA looks recovered but is
   still +57% perplexity over A16. Residual damage leaks into facts (A5+LoRA gets
   primary colors wrong; the A16 control gets them right).
3. **The clean half of the thesis holds:** LoRA trains fine on a quantized base —
   no discreteness stall (contrast §4). It just can't, in a short finetune,
   recover precision that 5-bit activations threw away.

## Practical notes (MPS)

- **Token-positions per step has a cliff.** batch 1 × accum 4 × max_len 128 (=512
  positions/step) runs at ~1.7 s/it. Pushing to max_len 256 × effective batch 8
  (=2048/step) did NOT scale ~4× — it went ~100× slower (~190 s/it), memory
  thrashing near the 18 GB MPS ceiling. **512 positions/step is the sweet spot.**
- **Use float32 for training**, but keep per-step token count small — fp32 + large
  batch/seq OOMs the loss (32k-vocab cross-entropy) and crawls.

## Open follow-ups

- Longer LoRA-QAT (many more steps) to see if quant recovery grows past ~17%.
- Per-layer sensitivity sweep (which layers tolerate low bits).
