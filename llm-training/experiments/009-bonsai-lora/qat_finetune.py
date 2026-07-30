"""
Option 1: weight-QAT on REAL Bonsai. Graduate the STE line from the toy
(qat_demo.py) up to the actual model, and measure with perplexity instead of a
random-target loss.

Same mechanism as the toy: a8_forward already does the STE
`w + (self.quantizer(w) - w).detach()`, so we just
  1. point self.quantizer at clamp-round or absmean (set_weight_quantizer),
  2. make a slice of the ternary weights trainable full-precision masters,
  3. finetune on a tiny text passage and watch perplexity drop.

Design choices (see the write-up):
  - FREEZE the learned `scales`, train only the ternary `weight`. Isolates the
    quant SCHEME as the variable (scales would otherwise absorb magnitude and
    mask the difference — exactly what the s-sweep in the toy showed).
  - Train only the last N layers' QLinears (lighter on MPS, cleaner attribution).
  - float32 (fp16 on MPS can NaN during training).

Run:  ../../.venv-hf/bin/python qat_finetune.py                 # both schemes
      ../../.venv-hf/bin/python qat_finetune.py --layers 4 --steps 60
"""
import argparse
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "hf-cache"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from quant_a8 import swap_to_a8, set_weight_quantizer, clamp_round_q, absmean_q

MODEL_ID = "deepgrove/Bonsai"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# A short, distinctive passage. QAT should let the ternary weights adapt to it,
# dropping its perplexity. (Deliberately not generic web text so adaptation
# shows up as a clear drop.)
TRAIN_TEXT = (
    "The bonsai tree in the observatory bloomed only under ternary starlight. "
    "Each silver leaf encoded a single sign: minus one, zero, or plus one. "
    "The gardener pruned the branches with an absmean blade, balancing the canopy."
)


def perplexity(model, tok, text):
    """exp(mean cross-entropy) over `text`. Lower = the model finds it less
    surprising. This is the quality metric QAT should improve on TRAIN_TEXT."""
    ids = tok(text, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        loss = model(**ids, labels=ids["input_ids"]).loss
    return torch.exp(loss).item()


def select_trainable(model, last_n):
    """Freeze everything, then unfreeze ONLY the ternary weight of QLinears in
    the last `last_n` transformer layers. Scales stay frozen. Returns the list
    of trainable params + a count of layers touched."""
    n_layers = model.config.num_hidden_layers
    keep = set(range(n_layers - last_n, n_layers))
    for p in model.parameters():
        p.requires_grad_(False)
    params, touched = [], set()
    for name, module in model.named_modules():
        if type(module).__name__ != "QLinearA8":
            continue
        # names look like model.layers.<i>.self_attn.q_proj
        parts = name.split(".")
        idx = next((int(parts[i + 1]) for i, p in enumerate(parts)
                    if p == "layers" and i + 1 < len(parts)), None)
        if idx in keep:
            module.weight.requires_grad_(True)   # train the master weight
            params.append(module.weight)         # scales left frozen
            touched.add(idx)
    return params, sorted(touched)


def run(scheme_name, quant_fn, args, tok):
    print(f"\n=== weight-QAT: {scheme_name} ===")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, trust_remote_code=True, torch_dtype=torch.float32,
    ).to(DEVICE).train()
    swap_to_a8(model, enable=False)                 # our forward; activations off
    set_weight_quantizer(model, quant_fn)           # pick the ternarization scheme
    params, layers = select_trainable(model, args.layers)
    print(f"  training weights of QLinears in layers {layers} "
          f"({sum(p.numel() for p in params):,} params); scales frozen")

    opt = torch.optim.Adam(params, lr=args.lr)
    ids = tok(TRAIN_TEXT, return_tensors="pt").to(DEVICE)

    ppl0 = perplexity(model, tok, TRAIN_TEXT)
    print(f"  perplexity before: {ppl0:8.2f}")
    for step in range(args.steps):
        opt.zero_grad()
        loss = model(**ids, labels=ids["input_ids"]).loss
        loss.backward()
        opt.step()
        if step % max(1, args.steps // 5) == 0 or step == args.steps - 1:
            print(f"    step {step:3d}  train loss {loss.item():.4f}")
    ppl1 = perplexity(model, tok, TRAIN_TEXT)
    print(f"  perplexity after:  {ppl1:8.2f}   (delta {ppl1 - ppl0:+.2f})")
    return ppl0, ppl1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", choices=["clamp", "absmean", "both"], default="both")
    ap.add_argument("--layers", type=int, default=4, help="finetune last N layers")
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--lr", type=float, default=1e-4)
    args = ap.parse_args()

    print(f"torch {torch.__version__} | device = {DEVICE} | "
          f"last {args.layers} layers | {args.steps} steps")
    tok = AutoTokenizer.from_pretrained(MODEL_ID)

    results = {}
    if args.scheme in ("clamp", "both"):
        results["clamp-round"] = run("clamp-round", clamp_round_q, args, tok)
    if args.scheme in ("absmean", "both"):
        results["absmean"] = run("absmean", absmean_q, args, tok)

    if len(results) == 2:
        print("\n--- summary (perplexity on TRAIN_TEXT) ---")
        for k, (a, b) in results.items():
            print(f"  {k:12s} {a:8.2f} -> {b:8.2f}  ({b - a:+.2f})")


if __name__ == "__main__":
    main()
