import torch

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
    s = w / (gamma + eps)
    w_tilde = ste_round(s).clamp(-1, 1)
    return w_tilde, gamma