import torch
import torch.nn as nn
import torch.nn.functional as F

def ste_round(x: torch.Tensor) -> torch.Tensor:
    """
    Straight-through estimator for rounding.
    Forward pass: rounds to nearest integer.
    Backward pass: identity (gradient is 1).
    """
    return x + (x.round() - x).detach()

def ternary_absmean(w: torch.Tensor, eps: float = 1e-5) -> tuple[torch.Tensor, torch.Tensor]:
    """
    BitNet b1.58 absmean weight quantizer (eqs 1-3).
    Returns (w_tilde, gamma): ternary matrix in {-1,0,+1} and the per-tensor scale.
    """
    gamma = w.abs().mean()
    w_tilde = ste_round(w / (gamma + eps)).clamp(-1, 1)
    return w_tilde, gamma

def int8_absmax(w: torch.Tensor, eps: float = 1e-5) -> tuple[torch.Tensor, torch.Tensor]:
    """INT8 per-tensor absmax fake-quant. Sanity path for the STE harness."""
    s = w.abs().max()/127
    w_tilde = ste_round(w / (s + eps)).clamp(-127, 127)
    return w_tilde, s

class BitLinear(nn.Linear):
    def __init__(self, in_features, out_features, bias=True, quant_fn=ternary_absmean):
        super().__init__(in_features, out_features, bias=bias)
        self.quant_fn = quant_fn

    def forward(self, x):
        codes, scale = self.quant_fn(self.weight)
        out = scale * F.linear(x, codes)
        if self.bias is not None:
            out = out + self.bias
        return out

def make_linear(quantize: bool, in_features: int, out_features: int, bias: bool = True):
    cls = BitLinear if quantize else nn.Linear
    return cls(in_features, out_features, bias=bias)