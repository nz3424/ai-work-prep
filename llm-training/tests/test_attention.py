import math

import torch
import torch.nn.functional as F

from src.attention import CausalSelfAttention


def test_output_shape_matches_input():
    attn = CausalSelfAttention(d_model=8, n_heads=2)
    x = torch.randn(2, 3, 8)
    out = attn(x)
    assert out.shape == (2, 3, 8)


def test_causal_masking_blocks_future_tokens():
    d_model = 4
    attn = CausalSelfAttention(d_model=d_model, n_heads=1)
    attn.eval()

    torch.manual_seed(0)
    x1 = torch.randn(1, 3, d_model)
    x2 = x1.clone()
    x2[0, 2, :] = torch.randn(d_model)  # change only the last token

    out1 = attn(x1)
    out2 = attn(x2)

    # Tokens 0 and 1 can only attend to positions <= themselves, so changing
    # token 2 must not change their output.
    assert torch.allclose(out1[0, 0], out2[0, 0], atol=1e-6)
    assert torch.allclose(out1[0, 1], out2[0, 1], atol=1e-6)


def test_matches_manual_computation_with_identity_projections():
    d_model = 4
    attn = CausalSelfAttention(d_model=d_model, n_heads=1)
    with torch.no_grad():
        for proj in (attn.q_proj, attn.k_proj, attn.v_proj, attn.out_proj):
            proj.weight.copy_(torch.eye(d_model))
            proj.bias.zero_()

    x = torch.tensor([[
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ]])  # (1, 3, 4)

    out = attn(x)

    # With identity Q/K/V/out projections, scores = x @ x.T / sqrt(d_model).
    scores = x[0] @ x[0].T / math.sqrt(d_model)
    causal_mask = torch.triu(torch.ones(3, 3, dtype=torch.bool), diagonal=1)
    scores = scores.masked_fill(causal_mask, float("-inf"))
    expected_weights = F.softmax(scores, dim=-1)
    expected_out = (expected_weights @ x[0]).unsqueeze(0)

    assert torch.allclose(out, expected_out, atol=1e-6)
