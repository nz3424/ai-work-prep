"""
Compare Bonsai W1.58A16 (stock) vs W1.58A8 (8-bit activations) on the SAME
loaded model, by flipping the activation-quant flag.

Scope: prove-it + qualitative.
  1. Sanity: forward runs without NaN/Inf under A8.
  2. Quality: greedy completions on fixed prompts, A16 vs A8 side by side.

Greedy decoding (do_sample=False) so any difference is attributable to the
activation quant, not sampling noise.

Run:  ../../.venv-hf/bin/python measure_a8.py            # default 8-bit
      ../../.venv-hf/bin/python measure_a8.py --bits 4   # sweep the bit-width

Lower --bits = coarser activation grid = more quantization error. Watch how
low you can go before completions degrade (word salad / repetition).
"""
import argparse
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "hf-cache"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from quant_a8 import swap_to_a8, set_activation_quant

MODEL_ID = "deepgrove/Bonsai"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

PROMPTS = [
    "The team that is going to win the",
    "The capital of Italy is",
    "Once upon a time",
    "The most popular flavor of",
]


def generate(model, tok, prompt):
    ids = tok(prompt, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=20, do_sample=False)
    return tok.decode(out[0], skip_special_tokens=True)


def nan_check(model, tok):
    ids = tok(PROMPTS[0], return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        logits = model(**ids).logits
    bad = torch.isnan(logits).any().item() or torch.isinf(logits).any().item()
    print(f"  logits: shape={tuple(logits.shape)} "
          f"finite={'NO — NaN/Inf!' if bad else 'yes'} "
          f"absmax={logits.abs().max().item():.2f}")
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, default=8,
                    help="activation bit-width (8 = the original int8 path)")
    args = ap.parse_args()

    print(f"torch {torch.__version__} | device = {DEVICE} | act bits = {args.bits}")
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, trust_remote_code=True, torch_dtype=torch.float16,
    ).to(DEVICE).eval()

    n, _ = swap_to_a8(model, enable=False, bits=args.bits)
    print(f"swapped {n} QLinear -> QLinearA8")

    print(f"\n=== NaN/Inf sanity check (A{args.bits} on) ===")
    set_activation_quant(model, True)
    ok = nan_check(model, tok)
    if not ok:
        print("  A8 forward produced non-finite logits — stop and debug before "
              "trusting generations.")

    print(f"\n=== A16 (stock) vs A{args.bits} (quantized activations) ===")
    for p in PROMPTS:
        set_activation_quant(model, False)
        a16 = generate(model, tok, p)
        set_activation_quant(model, True)
        a8 = generate(model, tok, p)
        print(f"\nPROMPT: {p!r}")
        print(f"  [A16]     {a16}")
        print(f"  [A{args.bits:<2}]     {a8}")
        print(f"  (identical: {a16 == a8})")


if __name__ == "__main__":
    main()
