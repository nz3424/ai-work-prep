"""Unit 3 / Module 5: absmax vs absmean in the ternary regime, plus the memory math.

Three questions:
  1. Why does BitNet scale by mean|W| instead of max|W|? (measure what fraction of
     weights survive as +/-1 under each, with and without an injected outlier)
  2. What is the concrete memory win of ternary-packed weights?
  3. Parked Unit 1 thread: does ternarizing the FFN up-projection blur *which*
     pattern each detector neuron fires on, and does it hurt sparse detector rows
     more than diffuse attention projections?

Run from the llm-training repo root with PYTHONPATH=.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path

from src.tokenizer import BPETokenizer
from src.transformer import ModelConfig, TinyTransformer

CKPT = Path("checkpoints/002-rope")
DATA = Path("data/tinyshakespeare.txt")


def ternarize(w, rule, per_channel=False):
    if rule == "absmean":
        s = w.abs().mean(dim=1, keepdim=True) if per_channel else w.abs().mean()
    else:
        s = w.abs().amax(dim=1, keepdim=True) if per_channel else w.abs().max()
    s = s.clamp(min=1e-12)
    codes = (w / s).round().clamp(-1, 1)
    return codes, codes * s


ckpt = torch.load(CKPT / "model.pt", map_location="cpu", weights_only=False)
config = ckpt["model_config"]
if isinstance(config, dict):
    config = ModelConfig(**config)
model = TinyTransformer(config)
model.load_state_dict(ckpt["model_state_dict"])
model.eval()

W1 = model.blocks[0].ffn[0].weight.data.clone()      # (512, 128) FFN up-proj
QP = model.blocks[0].attention.q_proj.weight.data.clone()  # (128, 128)

# ---- 1. why absmean -------------------------------------------------------
print("=" * 74)
print("1. WHERE THE WEIGHTS LAND: fraction assigned to each ternary code")
print("=" * 74)
print(f"{'tensor / rule':<34} {'s':>9} {'-1':>7} {'0':>7} {'+1':>7} {'nonzero':>9}")
print("-" * 74)


def code_report(label, w, rule, per_channel=False):
    codes, w_hat = ternarize(w, rule, per_channel)
    s = (w.abs().mean() if rule == "absmean" else w.abs().max()).item()
    n = codes.numel()
    neg = (codes == -1).sum().item() / n
    zer = (codes == 0).sum().item() / n
    pos = (codes == 1).sum().item() / n
    print(f"{label:<34} {s:9.4f} {neg:6.1%} {zer:6.1%} {pos:6.1%} {1 - zer:8.1%}")
    return w_hat


code_report("W1 (ffn up-proj)   absmean", W1, "absmean")
code_report("W1 (ffn up-proj)   absmax", W1, "absmax")
code_report("q_proj             absmean", QP, "absmean")
code_report("q_proj             absmax", QP, "absmax")

# theory for a Gaussian
print("\n  theory, Gaussian weights with std = sigma:")
print("    absmean:  s = sigma*sqrt(2/pi) = 0.798 sigma, threshold s/2 = 0.399 sigma")
print(f"              -> P(|w| > 0.399 sigma) = {2 * (1 - 0.5 * (1 + math.erf(0.399 / math.sqrt(2)))):.1%} nonzero")
print(f"    absmax:   s = max|W| ~ 4.2 sigma for n=65536, threshold s/2 = 2.1 sigma")
print(f"              -> P(|w| > 2.1 sigma)   = {2 * (1 - 0.5 * (1 + math.erf(2.1 / math.sqrt(2)))):.1%} nonzero")

# ---- 2. outlier robustness ------------------------------------------------
print("\n" + "=" * 74)
print("2. OUTLIER ROBUSTNESS: inject one weight at 20x the current max")
print("=" * 74)
W1_out = W1.clone()
W1_out[0, 0] = W1.abs().max() * 20

hdr = f"{'rule':<12} {'s before':>10} {'s after':>10} {'nonzero before':>15} {'nonzero after':>14}"
print(hdr)
print("-" * len(hdr))
for rule in ["absmean", "absmax"]:
    c0, _ = ternarize(W1, rule)
    c1, _ = ternarize(W1_out, rule)
    s0 = (W1.abs().mean() if rule == "absmean" else W1.abs().max()).item()
    s1 = (W1_out.abs().mean() if rule == "absmean" else W1_out.abs().max()).item()
    nz0 = 1 - (c0 == 0).float().mean().item()
    nz1 = 1 - (c1 == 0).float().mean().item()
    print(f"{rule:<12} {s0:10.4f} {s1:10.4f} {nz0:14.1%} {nz1:13.1%}")

# ---- 3. memory math -------------------------------------------------------
print("\n" + "=" * 74)
print("3. MEMORY MATH")
print("=" * 74)


def memory_math(name, body, embed, head):
    total = body + embed + head
    fp16 = total * 2
    held = (embed + head) * 2
    ideal = body * 1.58 / 8 + held
    packed = body * 2 / 8 + held
    print(f"\n{name}   total {total:,} params   body {body / total:.1%} of params")
    print(f"  FP16 everything            {fp16 / 1e6:10.2f} MB    1.00x")
    print(f"  ternary 2-bit packed body  {packed / 1e6:10.2f} MB   {fp16 / packed:5.2f}x")
    print(f"  ternary ideal 1.58-bit     {ideal / 1e6:10.2f} MB   {fp16 / ideal:5.2f}x")
    print(f"  (embedding + head held in FP16: {held / 1e6:.2f} MB, "
          f"{held / packed:.0%} of the packed model)")


body = sum(m.weight.numel() for n, m in model.named_modules()
           if isinstance(m, nn.Linear) and n != "head")
emb = model.token_embedding.weight.numel()
head = model.head.weight.numel()
memory_math("toy model (d_model=128, vocab=1006)", body, emb, head)

# LLaMA-7B shape, for contrast
d, L, dff, V = 4096, 32, 11008, 32000
body7 = L * (4 * d * d + 3 * d * dff)
memory_math("LLaMA-7B shape (d_model=4096, vocab=32000)", body7, V * d, V * d)

# ---- 4. parked Unit 1 thread ----------------------------------------------
print("\n" + "=" * 74)
print("4. PARKED UNIT 1 THREAD: do sparse FFN detector rows suffer more?")
print("=" * 74)


def row_fidelity(w, label):
    """Per-row cosine similarity after ternarization, and per-row kurtosis
    (how 'peaky' / detector-like the row is)."""
    _, w_hat = ternarize(w, "absmean")
    cos = F.cosine_similarity(w, w_hat, dim=1)
    z = (w - w.mean(dim=1, keepdim=True)) / w.std(dim=1, keepdim=True)
    kurt = (z ** 4).mean(dim=1)          # 3.0 for a Gaussian row
    corr = torch.corrcoef(torch.stack([kurt, cos]))[0, 1].item()
    print(f"  {label:<22} cos sim {cos.mean():.4f} +/- {cos.std():.4f}   "
          f"kurtosis {kurt.mean():5.2f}   corr(kurt, cos) {corr:+.3f}")
    return cos, kurt


print("\nper-row cosine similarity between original and ternarized rows:")
for name, mod in model.named_modules():
    if isinstance(mod, nn.Linear) and name.startswith("blocks.0"):
        row_fidelity(mod.weight.data, name.replace("blocks.0.", ""))

# Does ternarizing W1 change WHICH neurons fire?
print("\ndoes ternarizing the FFN up-proj change which neurons fire?")
tok = BPETokenizer.load(str(CKPT / "tokenizer.json"))
ids = torch.tensor(tok.encode(DATA.read_text()[:100_000]), dtype=torch.long)
g = torch.Generator().manual_seed(0)
T = config.context_length
starts = torch.randint(0, ids.size(0) - T - 1, (8,), generator=g)
batch = torch.stack([ids[s:s + T] for s in starts])

captured = {}
model.blocks[0].ln2.register_forward_hook(
    lambda m, i, o: captured.__setitem__("x", o.detach()))
with torch.no_grad():
    model(batch)
x = captured["x"].reshape(-1, config.d_model)

lin = model.blocks[0].ffn[0]
with torch.no_grad():
    act_fp = F.gelu(F.linear(x, W1, lin.bias))
    _, W1_tern = ternarize(W1, "absmean")
    act_tern = F.gelu(F.linear(x, W1_tern, lin.bias))

for k in [8, 16, 32, 64]:
    top_fp = act_fp.topk(k, dim=1).indices
    top_tn = act_tern.topk(k, dim=1).indices
    overlap = torch.stack([
        torch.isin(top_fp[i], top_tn[i]).float().mean() for i in range(top_fp.size(0))
    ]).mean().item()
    print(f"  top-{k:<3} firing neurons preserved: {overlap:6.1%}   "
          f"(chance = {k / config.d_ff:.1%})")

corr_act = torch.corrcoef(torch.stack([act_fp.flatten(), act_tern.flatten()]))[0, 1]
print(f"\n  correlation of all post-GELU activations, FP32 vs ternary W1: {corr_act:.4f}")
