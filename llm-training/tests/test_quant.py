import torch

from src.ternary_quant import ste_round


def test_ste_round_forward_is_round():
    x = torch.tensor([-1.4, -0.4, 0.6, 1.9])
    assert torch.equal(ste_round(x), torch.tensor([-1.0, 0.0, 1.0, 2.0]))


def test_ste_round_backward_is_identity():
    x = torch.tensor([-1.4, 0.6, 1.9], requires_grad=True)
    ste_round(x).sum().backward()
    assert torch.equal(x.grad, torch.ones_like(x))  # not zeros
