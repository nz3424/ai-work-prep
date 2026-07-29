"""
Add 8-bit activation quantization to Bonsai's ternary layer (W1.58A16 -> W1.58A8).

Bonsai ships its linear layer (`QLinear`) as a trust_remote_code file that HF
downloads into a cache dir and executes. Editing that cached file is fragile
(re-downloads clobber it, it's not in our git). So instead we:

  1. Define an override `forward` (a8_forward) that mirrors Bonsai's stock
     forward but ALSO fake-quantizes the activations `x` before the matmul.
  2. At runtime, discover the live `QLinear` class, build a subclass
     `QLinearA8` from it, and re-point every QLinear instance at it via
     `module.__class__ = QLinearA8`. No parameter copying, cache untouched,
     the whole change lives here in git.

The A8 behavior is gated by a per-module `quantize_acts` flag, so the SAME
loaded model can be flipped between A16 (flag off) and A8 (flag on) for a
clean apples-to-apples comparison. Flag off reproduces stock behavior exactly.
"""
import sys
from pathlib import Path

# Make the 008 quantization code importable (src/ternary_quant.py lives at the
# llm-training/ root, two levels up from this experiment dir).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch.nn.functional as F
from src.ternary_quant import int8_activation, ste_round  # per-token absmax fake-quant


def fake_quant_activation(x, bits, eps=1e-5):
    """Per-token absmax fake-quant to `bits` bits (generalizes int8_activation).

    bits=8 -> 127 levels (same grid as int8_activation); bits=4 -> 7 levels,
    etc. Lower bits = coarser grid = more quantization error, so this is the
    knob for finding where activation quant starts to hurt.
    """
    qmax = 2 ** (bits - 1) - 1                     # 8->127, 4->7, 2->1
    s = x.abs().amax(dim=-1, keepdim=True) / qmax
    x_tilde = ste_round(x / (s + eps)).clamp(-qmax, qmax)
    return x_tilde * (s + eps)


def a8_forward(self, x):
    """Bonsai's QLinear.forward + optional INT8 activation quant.

    Mirrors the stock forward (STE ternary weight quant -> matmul ->
    per-output-channel `scales` -> bias). When `self.quantize_acts` is True,
    the activations are fake-quantized to INT8 first.
    """
    w = self.weight
    x = x.to(w.device)
    # STE ternary weight quantization (Bonsai's QAT: forward=ternary,
    # backward=identity). Shown here so it's visible/tinker-able, not hidden.
    w = w + (self.quantizer(w) - w).detach()

    if getattr(self, "quantize_acts", False):
        # THE LOAD-BEARING LINE (Nick): fake-quant activations before the
        # matmul, mirroring 008's BitLinear. act_bits picks the grid; the
        # default 8-bit path is the original int8_activation, other widths use
        # the generalized quant so you can sweep bit-width from the harness.
        bits = getattr(self, "act_bits", 8)
        x = int8_activation(x) if bits == 8 else fake_quant_activation(x, bits)

    y = F.linear(x, w)
    y = y * self.scales
    if self.bias is not None:
        y = y + self.bias
    return y


def swap_to_a8(model, enable=False, bits=8):
    """Re-point every Bonsai QLinear at a QLinearA8 subclass (in place).

    Returns (n_swapped, a8_class). `enable` sets the initial activation-quant
    flag on every swapped layer (default off == behaves like stock A16).
    `bits` sets the activation grid (8 = the original int8 path).
    """
    a8_cls = None
    n = 0
    for module in model.modules():
        if type(module).__name__ == "QLinear":
            if a8_cls is None:
                base = type(module)  # the real, dynamically-loaded QLinear
                a8_cls = type("QLinearA8", (base,), {"forward": a8_forward})
            module.__class__ = a8_cls
            module.quantize_acts = enable
            module.act_bits = bits
            n += 1
    if n == 0:
        raise RuntimeError("No QLinear layers found — is this a Bonsai model?")
    return n, a8_cls


def set_activation_quant(model, on):
    """Flip the A8 flag on every swapped layer. Returns count toggled."""
    n = 0
    for module in model.modules():
        if type(module).__name__ == "QLinearA8":
            module.quantize_acts = bool(on)
            n += 1
    return n


# ---- weight-quant schemes (full-precision -> ternary), for QAT ----------
# a8_forward runs `w + (self.quantizer(w) - w).detach()` (the STE), so swapping
# self.quantizer swaps the scheme WITHOUT touching the STE. On the shipped
# (already-ternary) checkpoint both are no-ops; they only diverge once training
# pushes the master weights off the ternary grid.

def clamp_round_q(w):
    """Bonsai's scheme: sign-only, FIXED 0.5 threshold, scale-blind."""
    return w.clamp(-1, 1).round()

def absmean_q(w, eps=1e-5):
    """Canonical BitNet: normalize by mean|w| first, so the threshold ADAPTS."""
    g = w.abs().mean()
    return (w / (g + eps)).round().clamp(-1, 1)


def set_weight_quantizer(model, fn):
    """Point every swapped layer's weight quantizer at `fn`. Returns count."""
    n = 0
    for module in model.modules():
        if type(module).__name__ == "QLinearA8":
            module.quantizer = fn
            n += 1
    return n
