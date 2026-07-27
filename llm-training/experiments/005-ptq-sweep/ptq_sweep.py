"""Unit 3 / Module 4: post-training quantization sweep on the trained toy model.

Quantize every nn.Linear weight (fake-quant: quantize then dequantize back to
float, so the model still runs in FP32) at a range of bit widths, and measure
what it does to validation loss. This is PTQ in its purest form: no retraining,
no calibration beyond reading the weights themselves.

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
VAL_FRACTION = 0.1
EVAL_BATCHES = 20
BATCH_SIZE = 16


# ---- the quantizers --------------------------------------------------------
def fake_quant_absmax(w: torch.Tensor, bits: int, per_channel: bool) -> torch.Tensor:
    """Symmetric uniform quantize -> dequantize. Returns a float tensor that can
    only take on the representable grid values."""
    q_max = 2 ** (bits - 1) - 1
    if per_channel:
        s = w.abs().amax(dim=1, keepdim=True) / q_max
    else:
        s = w.abs().max() / q_max
    s = s.clamp(min=1e-12)
    return (w / s).round().clamp(-q_max - 1, q_max) * s


def fake_quant_ternary_absmean(w: torch.Tensor, per_channel: bool) -> torch.Tensor:
    """BitNet b1.58's scheme: scale by mean|W|, round to {-1, 0, 1}, scale back."""
    if per_channel:
        s = w.abs().mean(dim=1, keepdim=True)
    else:
        s = w.abs().mean()
    s = s.clamp(min=1e-12)
    return (w / s).round().clamp(-1, 1) * s


def fake_quant_ternary_absmax(w: torch.Tensor, per_channel: bool) -> torch.Tensor:
    """Same ternary grid, but the scale comes from max|W| instead of mean|W|."""
    if per_channel:
        s = w.abs().amax(dim=1, keepdim=True)
    else:
        s = w.abs().max()
    s = s.clamp(min=1e-12)
    return (w / s).round().clamp(-1, 1) * s


# ---- setup -----------------------------------------------------------------
ckpt = torch.load(CKPT / "model.pt", map_location="cpu", weights_only=False)
config = ckpt["model_config"]
if isinstance(config, dict):
    config = ModelConfig(**config)

tok = BPETokenizer.load(str(CKPT / "tokenizer.json"))
ids = torch.tensor(tok.encode(DATA.read_text()), dtype=torch.long)
val_size = int(len(ids) * VAL_FRACTION)
val_data = ids[-val_size:]


def val_loss(model: nn.Module) -> float:
    """Fixed set of validation batches, same every call, so runs are comparable."""
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


def fresh_model() -> nn.Module:
    m = TinyTransformer(config)
    m.load_state_dict(ckpt["model_state_dict"])
    return m


def linear_sites(model: nn.Module) -> list[tuple[str, nn.Linear]]:
    """Every nn.Linear a BitLinear conversion would touch. The embedding and the
    LM head are listed separately because BitNet leaves them in high precision."""
    return [(n, m) for n, m in model.named_modules() if isinstance(m, nn.Linear)]


def apply_ptq(model: nn.Module, fn, skip_head: bool = True) -> int:
    n_quantized = 0
    with torch.no_grad():
        for name, mod in linear_sites(model):
            if skip_head and name == "head":
                continue
            mod.weight.copy_(fn(mod.weight.data))
            n_quantized += mod.weight.numel()
    return n_quantized


# ---- baseline --------------------------------------------------------------
base = fresh_model()
base_loss = val_loss(base)

sites = linear_sites(base)
print("nn.Linear conversion sites (what BitLinear would replace):")
total_params = 0
for name, mod in sites:
    n = mod.weight.numel()
    total_params += n
    tag = "  <- BitNet keeps this in high precision" if name == "head" else ""
    print(f"  {name:<28} {tuple(mod.weight.shape)!s:>14}  {n:>9,} params{tag}")
emb = base.token_embedding.weight.numel()
print(f"  {'token_embedding':<28} {tuple(base.token_embedding.weight.shape)!s:>14}  {emb:>9,} params"
      f"  <- BitNet keeps this in high precision")
head_n = dict(sites)["head"].weight.numel()
body = total_params - head_n
print(f"\n  quantizable body: {body:,} params   held out (head+embed): {head_n + emb:,}")
print(f"\nFP32 baseline val loss: {base_loss:.4f}  (perplexity {math.exp(base_loss):.1f})\n")

# ---- the sweep -------------------------------------------------------------
rows = []
for bits in [8, 6, 4, 3, 2]:
    for pc in [False, True]:
        m = fresh_model()
        apply_ptq(m, lambda w, b=bits, p=pc: fake_quant_absmax(w, b, p))
        rows.append((f"INT{bits} absmax", "per-channel" if pc else "per-tensor", val_loss(m)))

for pc in [False, True]:
    m = fresh_model()
    apply_ptq(m, lambda w, p=pc: fake_quant_ternary_absmax(w, p))
    rows.append(("ternary absmax", "per-channel" if pc else "per-tensor", val_loss(m)))

for pc in [False, True]:
    m = fresh_model()
    apply_ptq(m, lambda w, p=pc: fake_quant_ternary_absmean(w, p))
    rows.append(("ternary absmean", "per-channel" if pc else "per-tensor", val_loss(m)))

hdr = f"{'scheme':<18} {'granularity':<13} {'val loss':>9} {'ppl':>9} {'vs FP32':>10}"
print(hdr)
print("-" * len(hdr))
print(f"{'FP32 (none)':<18} {'-':<13} {base_loss:9.4f} {math.exp(base_loss):9.1f} {'--':>10}")
for scheme, gran, loss in rows:
    delta = loss - base_loss
    print(f"{scheme:<18} {gran:<13} {loss:9.4f} {math.exp(loss):9.1f} {delta:+10.4f}")

# ---- how much of the damage is the head? ----------------------------------
print("\nternary absmean per-tensor, WITH the lm_head also quantized:")
m = fresh_model()
apply_ptq(m, lambda w: fake_quant_ternary_absmean(w, False), skip_head=False)
l = val_loss(m)
print(f"  val loss {l:.4f}  (ppl {math.exp(l):.1f}, {l - base_loss:+.4f} vs FP32)")

# ---- random-guess floor for reference --------------------------------------
print(f"\nreference: uniform-random over {config.vocab_size} tokens would be "
      f"loss {math.log(config.vocab_size):.4f} (ppl {config.vocab_size})")
