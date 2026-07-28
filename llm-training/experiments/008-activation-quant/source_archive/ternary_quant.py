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

def int8_activation(x: torch.Tensor, eps: float = 1e-5) -> torch.Tensor:
    """INT8 per-token absmax fake-quant. Returns the dequantized activation on
    the 8-bit grid (real-valued); STE carries the gradient straight through."""
    gamma = x.abs().amax(dim=-1, keepdim=True)
    s = gamma / 127
    x_tilde = ste_round(x / (s + eps)).clamp(-127, 127)
    return x_tilde * (s + eps)

class BitLinear(nn.Linear):
    def __init__(self, in_features, out_features, bias=True, quant_fn=ternary_absmean, quantize_activations: bool = False):
        super().__init__(in_features, out_features, bias=bias)
        self.quant_fn = quant_fn
        self.quantize_activations = quantize_activations

    def forward(self, x):
        codes, scale = self.quant_fn(self.weight)
        if self.quantize_activations:
            x = int8_activation(x)
        out = scale * F.linear(x, codes)
        if self.bias is not None:
            out = out + self.bias
        return out

def make_linear(quantize: bool, in_features: int, out_features: int, bias: bool = True, quantize_activations: bool = False) -> nn.Module:
    if quantize:
        return BitLinear(in_features, out_features, bias=bias, quantize_activations=quantize_activations)
    else:
        return nn.Linear(in_features, out_features, bias=bias)