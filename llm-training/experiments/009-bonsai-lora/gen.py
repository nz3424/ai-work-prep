"""
Just generate text with Bonsai (plain completion, no fine-tuning).

Usage:
    ../../.venv-hf/bin/python gen.py "The moon landing was"
    ../../.venv-hf/bin/python gen.py "Once upon a time"
"""
import os, sys
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "hf-cache"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
prompt = sys.argv[1] if len(sys.argv) > 1 else "The key idea behind ternary weights is"

tok = AutoTokenizer.from_pretrained("deepgrove/Bonsai")
model = AutoModelForCausalLM.from_pretrained(
    "deepgrove/Bonsai", trust_remote_code=True, torch_dtype=torch.float16
).to(DEVICE).eval()

ids = tok(prompt, return_tensors="pt").to(DEVICE)
with torch.no_grad():
    out = model.generate(
        **ids,
        max_new_tokens=80,
        do_sample=True,      # True = varied/creative; set False for repeatable
        temperature=0.8,     # higher = more random
        top_p=0.9,
    )
print(tok.decode(out[0], skip_special_tokens=True))
