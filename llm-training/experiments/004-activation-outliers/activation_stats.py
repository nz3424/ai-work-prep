"""Unit 3 / Module 3: dump per-dimension activation statistics from the trained
toy transformer, to find outlier feature dimensions and check whether the
residual stream's dynamic range grows with depth.

Run from the llm-training repo root.
"""
import torch
from pathlib import Path

from src.tokenizer import BPETokenizer
from src.transformer import ModelConfig, TinyTransformer

CKPT = Path("checkpoints/002-rope")
DATA = Path("data/tinyshakespeare.txt")

ckpt = torch.load(CKPT / "model.pt", map_location="cpu", weights_only=False)
config = ckpt["model_config"]
if isinstance(config, dict):
    config = ModelConfig(**config)
model = TinyTransformer(config)
model.load_state_dict(ckpt["model_state_dict"])
model.eval()

tok = BPETokenizer.load(str(CKPT / "tokenizer.json"))
text = DATA.read_text()[:200_000]
ids = torch.tensor(tok.encode(text), dtype=torch.long)

# One batch of 16 sequences at full context length.
B, T = 16, config.context_length
g = torch.Generator().manual_seed(0)
starts = torch.randint(0, ids.size(0) - T - 1, (B,), generator=g)
batch = torch.stack([ids[s:s + T] for s in starts])

# ---- hooks -----------------------------------------------------------------
# Record |x| stats over (batch, seq) for every feature dimension.
records = {}

def make_hook(name):
    def hook(_mod, _inp, out):
        x = out.detach().float().reshape(-1, out.shape[-1])   # (B*T, d_model)
        records[name] = {
            "absmax_per_dim": x.abs().amax(dim=0),   # (d_model,)
            "std_per_dim": x.std(dim=0),
            "absmax_overall": x.abs().max().item(),
            "absmean_overall": x.abs().mean().item(),
        }
    return hook

handles = []
handles.append(model.token_embedding.register_forward_hook(make_hook("embed (residual in)")))
for i, block in enumerate(model.blocks):
    handles.append(block.attention.register_forward_hook(make_hook(f"L{i} attn out")))
    handles.append(block.register_forward_hook(make_hook(f"L{i} residual out")))

with torch.no_grad():
    model(batch)
for h in handles:
    h.remove()

# ---- report ----------------------------------------------------------------
print(f"model: d_model={config.d_model} n_layers={config.n_layers} "
      f"batch={B}x{T} tokens={B*T}\n")

hdr = f"{'tensor':<20} {'absmax':>9} {'absmean':>9} {'ratio':>7}  {'top-3 outlier dims (dim:absmax)'}"
print(hdr)
print("-" * len(hdr))
for name, r in records.items():
    per_dim = r["absmax_per_dim"]
    top = torch.topk(per_dim, 3)
    tops = "  ".join(f"{d.item():>3}:{v.item():7.2f}" for v, d in zip(top.values, top.indices))
    ratio = r["absmax_overall"] / max(r["absmean_overall"], 1e-9)
    print(f"{name:<20} {r['absmax_overall']:9.2f} {r['absmean_overall']:9.3f} "
          f"{ratio:7.1f}x  {tops}")

# Which dims are outliers, and are they the SAME dims across layers?
print("\nper-dimension absmax / median-dim absmax, residual stream only:")
for name, r in records.items():
    if "residual" not in name and "embed" not in name:
        continue
    per_dim = r["absmax_per_dim"]
    med = per_dim.median()
    hot = (per_dim > 5 * med).nonzero().flatten().tolist()
    print(f"  {name:<20} median-dim absmax={med.item():6.2f}  "
          f"dims >5x median: {hot if hot else 'none'}")

# Emulate a single static per-tensor INT8 scale calibrated on layer 0, applied
# everywhere: how much does it clip by the last layer?
res_names = [n for n in records if "residual" in n or "embed" in n]
s0 = records[res_names[0]]["absmax_overall"]
print(f"\nstatic INT8 scale calibrated on '{res_names[0]}' (absmax={s0:.2f}):")
for n in res_names:
    m = records[n]["absmax_overall"]
    print(f"  {n:<20} absmax={m:7.2f}  ->  {'CLIPS ' + f'{m / s0:.1f}x over range' if m > s0 else f'uses only {100 * m / s0:.0f}% of range'}")
