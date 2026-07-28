"""Evaluate the 008 W1.58A8 checkpoint on 005's 20-fixed-batch harness.

Places 008 on the exact same measurement axis as the 66.6 (FP32) / 627 (PTQ
ternary) / 52.7 (007 QAT ternary, A16) numbers: same val split (last 10% of
tinyshakespeare through 002's tokenizer), same fixed batches (seed 1234, 20
batches, batch_size 16).

The 008 checkpoint's model_config has quantize_linears=True AND
quantize_activations=True, so reconstructing the model rebuilds BitLinear
layers that fake-quantize both ternary weights and per-token INT8 activations
inside forward(). This is a plain forward pass: NO apply_ptq step (unlike 005,
which PTQs the FP32 002 checkpoint post-hoc).

Run from the llm-training repo root with PYTHONPATH=.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path

from src.tokenizer import BPETokenizer
from src.transformer import ModelConfig, TinyTransformer

CKPT = Path("checkpoints/008-activation-quant")  # pull from S3 to here to reproduce
DATA = Path("data/tinyshakespeare.txt")
VAL_FRACTION = 0.1
EVAL_BATCHES = 20
BATCH_SIZE = 16  # 005's eval batch size -- identical batches only if this matches

ckpt = torch.load(CKPT / "model.pt", map_location="cpu", weights_only=False)
config = ckpt["model_config"]
if isinstance(config, dict):
    config = ModelConfig(**config)

tok = BPETokenizer.load(str(CKPT / "tokenizer.json"))
ids = torch.tensor(tok.encode(DATA.read_text()), dtype=torch.long)
val_size = int(len(ids) * VAL_FRACTION)
val_data = ids[-val_size:]


def val_loss(model: nn.Module) -> float:
    """005's harness verbatim: fixed 20 batches, same every call."""
    g = torch.Generator().manual_seed(1234)
    T = config.context_length
    total = 0.0
    model.eval()
    with torch.no_grad():
        for _ in range(EVAL_BATCHES):
            starts = torch.randint(0, val_data.size(0) - T - 1, (BATCH_SIZE,), generator=g)
            offs = torch.arange(T)
            idx = starts.unsqueeze(1) + offs.unsqueeze(0)
            x, y = val_data[idx], val_data[idx + 1]
            logits = model(x)
            total += F.cross_entropy(
                logits.view(-1, config.vocab_size), y.view(-1)
            ).item()
    return total / EVAL_BATCHES


model = TinyTransformer(config)
model.load_state_dict(ckpt["model_state_dict"])

# sanity: confirm the body Linears are actually BitLinear (quantized in forward)
from src.ternary_quant import BitLinear
n_bit = sum(1 for m in model.modules() if isinstance(m, BitLinear))
n_plain = sum(1 for m in model.modules() if isinstance(m, nn.Linear))
print(f"BitLinear layers: {n_bit}   plain nn.Linear layers: {n_plain}")
print(f"quantize_linears flag: {config.quantize_linears}")
print(f"quantize_activations flag: {config.quantize_activations}")

loss = val_loss(model)
print(f"\n008 W1.58A8 (005 harness): val loss {loss:.4f}   ppl {math.exp(loss):.1f}")
print("\nfor reference on the same axis:")
print(f"  002-rope FP32           val loss 4.198   ppl  66.6")
print(f"  005 PTQ ternary absmean val loss 6.441   ppl 627")
print(f"  007 QAT ternary (A16)   val loss 3.9649  ppl  52.7")
