import torch

def ste_round(x:torch.Tensor) -> torch.Tensor:
    """
    Straight-through estimator for rounding.
    Forward pass: rounds to nearest integer.
    Backward pass: identity (gradient is 1).
    """
    return x + (x.round() - x).detach()