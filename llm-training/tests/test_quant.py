import torch
import torch.nn.functional as F

from src.ternary_quant import BitLinear, int8_absmax, ste_round, ternary_absmean


def test_ste_round_forward_is_round():
    x = torch.tensor([-1.4, -0.4, 0.6, 1.9])
    assert torch.equal(ste_round(x), torch.tensor([-1.0, 0.0, 1.0, 2.0]))


def test_ste_round_backward_is_identity():
    x = torch.tensor([-1.4, 0.6, 1.9], requires_grad=True)
    ste_round(x).sum().backward()
    assert torch.equal(x.grad, torch.ones_like(x))  # not zeros


def test_ternary_absmean_matches_paper():
    # gamma = mean|W|;  W_tilde = RoundClip(W / (gamma + eps), -1, 1)
    w = torch.tensor([[0.0, 0.2, -0.2], [0.4, -0.4, 0.05]])
    gamma_expected = w.abs().mean()  # 0.2083...
    w_tilde, gamma = ternary_absmean(w)
    assert torch.allclose(gamma, gamma_expected)
    # hand-check: W/gamma ~ [[0, 0.96, -0.96], [1.92, -1.92, 0.24]]
    #             -> round -> clamp(-1, 1)
    expected = torch.tensor([[0.0, 1.0, -1.0], [1.0, -1.0, 0.0]])
    assert torch.equal(w_tilde, expected)


def test_ternary_absmean_is_ste():
    w = torch.tensor([[0.4, -0.4, 0.05]], requires_grad=True)
    w_tilde, _ = ternary_absmean(w)
    w_tilde.sum().backward()
    assert w.grad is not None and w.grad.abs().sum() > 0  # gradient reached w


def test_ternary_absmean_zero_tensor_stays_finite():
    # gamma == 0 is exactly what eps (inside the denominator) guards against
    w = torch.zeros(2, 3)
    w_tilde, gamma = ternary_absmean(w)
    assert torch.isfinite(w_tilde).all()  # no NaN from 0/0
    assert torch.equal(w_tilde, torch.zeros_like(w))


def test_int8_absmax_roundtrips_near_identity():
    torch.manual_seed(0)
    w = torch.randn(64, 64)
    codes, scale = int8_absmax(w)
    assert codes.abs().max() <= 127
    approx = codes * scale
    assert (approx - w).abs().max() < scale  # error bounded by one step


def test_bitlinear_forward_equals_scale_times_ternary_matmul():
    torch.manual_seed(0)
    layer = BitLinear(8, 4, bias=False)
    x = torch.randn(3, 8)
    codes, scale = ternary_absmean(layer.weight)
    expected = scale * F.linear(x, codes)
    assert torch.allclose(layer(x), expected, atol=1e-6)


def test_bitlinear_gradient_flows_to_weight():
    layer = BitLinear(8, 4, bias=False)
    layer(torch.randn(3, 8)).sum().backward()
    assert layer.weight.grad is not None and layer.weight.grad.abs().sum() > 0


def test_bitlinear_int8_sanity_is_near_fp():
    # STE harness correctness independent of ternary difficulty
    torch.manual_seed(0)
    layer = BitLinear(64, 64, bias=False, quant_fn=int8_absmax)
    x = torch.randn(16, 64)
    fp = F.linear(x, layer.weight)
    assert (layer(x) - fp).abs().max() < 0.5 * layer.weight.abs().max()
