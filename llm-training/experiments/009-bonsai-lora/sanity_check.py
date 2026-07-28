"""
Bonsai inference sanity check + ternary-layer inspection.

Goals:
  1. Prove the HF stack loads Bonsai and generates text on MPS.
  2. Locate Bonsai's *custom* modeling code (the trust_remote_code file).
  3. Inspect the linear layers and confirm the weights are actually ternary.

Run:  ../../.venv-hf/bin/python sanity_check.py
"""
import os
from pathlib import Path

# Keep the model download local + gitignored (see llm-training/.gitignore).
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "hf-cache"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "deepgrove/Bonsai"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"


def main():
    print(f"torch {torch.__version__} | device = {DEVICE}")

    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,   # runs Bonsai's custom ternary modeling code
        torch_dtype=torch.float16,
    ).to(DEVICE)
    model.eval()

    # ---- 1. Generate ------------------------------------------------------
    prompt = "The key idea behind ternary-weight neural networks is"
    inputs = tok(prompt, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=40, do_sample=False)
    print("\n--- generation ---")
    print(tok.decode(out[0], skip_special_tokens=True))

    # ---- 2. Where does the custom modeling code live? ---------------------
    print("\n--- custom modeling file(s) ---")
    print(f"model class: {type(model).__module__}.{type(model).__name__}")
    src = getattr(type(model), "__module__", "")
    # trust_remote_code modules cache under HF_HOME/modules/transformers_modules/...
    mod_root = Path(os.environ["HF_HOME"]) / "modules" / "transformers_modules"
    for p in mod_root.rglob("*.py"):
        print(f"  {p}")

    # ---- 3. Is the weight actually ternary? -------------------------------
    print("\n--- layer types (unique) ---")
    seen = {}
    for name, module in model.named_modules():
        cls = type(module).__name__
        if hasattr(module, "weight") and module.weight is not None:
            seen.setdefault(cls, name)
    for cls, example in seen.items():
        print(f"  {cls:30s} e.g. {example}")

    # Pick one linear-ish layer and look at its unique values.
    print("\n--- weight value distribution (first weighted layer) ---")
    for name, module in model.named_modules():
        w = getattr(module, "weight", None)
        if w is not None and w.dim() == 2:
            wf = w.detach().float().flatten()
            uniq = torch.unique(wf)
            print(f"  layer: {name}  ({type(module).__name__})")
            print(f"  shape: {tuple(w.shape)}  n_unique_values: {uniq.numel()}")
            if uniq.numel() <= 16:
                print(f"  unique values: {uniq.tolist()}")
            else:
                print(f"  (stored in fp16 — not packed; ternary structure may be "
                      f"in a scale + sign, inspect the modeling file)")
            break


if __name__ == "__main__":
    main()
