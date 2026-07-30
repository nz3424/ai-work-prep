"""Evaluate the 010 MoE checkpoint on 005's 20-fixed-batch harness.

Places 010 on the exact same measurement axis as the 66.6 (FP32 002-rope)
number: same val split (last 10% of tinyshakespeare through 002's tokenizer),
same fixed batches (seed 1234, 20 batches, batch_size 16).

The 010 checkpoint's model_config has use_moe=True, so reconstructing the model
rebuilds the MoEFeedForward layers. This is a plain forward pass: NO apply_ptq
step. The MoE forward is deterministic (top-2 routing, no dropout), so the 20
fixed batches are identical every call.

Run from the llm-training repo root with PYTHONPATH=.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path

from src.tokenizer import BPETokenizer
from src.transformer import ModelConfig, TinyTransformer
from src.moe import MoEFeedForward

CKPT = Path("checkpoints/010-moe")  # pull from S3 to here to reproduce
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

# sanity: confirm the blocks are actually MoE, and report per-expert balance.
n_moe = sum(1 for m in model.modules() if isinstance(m, MoEFeedForward))
print(f"MoEFeedForward blocks: {n_moe}   use_moe flag: {config.use_moe}")
print(f"n_experts: {config.n_experts}   top_k: {config.top_k}")

loss = val_loss(model)

# report the routing balance from the last eval forward (should be ~even).
moe_blocks = [m for m in model.modules() if isinstance(m, MoEFeedForward)]
if moe_blocks:
    fracs = torch.stack([(b.last_gate_weights > 0).float().mean(0) for b in moe_blocks]).mean(0)
    print(f"mean expert_frac (last batch): {[round(v, 2) for v in fracs.tolist()]}")

print(f"\n010 MoE (005 harness): val loss {loss:.4f}   ppl {math.exp(loss):.1f}")
print("\nfor reference on the same axis:")
print(f"  002-rope FP32 (dense FFN)  val loss 4.198   ppl  66.6")
