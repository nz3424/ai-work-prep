import torch

from src.moe import MoEFeedForward
from src.transformer import ModelConfig


def _cfg(**overrides) -> ModelConfig:
    base = dict(vocab_size=100, d_model=16, d_ff=32, n_experts=4, top_k=2, use_moe=True)
    base.update(overrides)
    return ModelConfig(**base)


def test_output_shape_is_preserved():
    torch.manual_seed(0)
    moe = MoEFeedForward(_cfg())
    x = torch.randn(2, 5, 16)
    out = moe(x)
    assert out.shape == x.shape


def test_router_selects_exactly_top_k_experts_per_token():
    # After a forward, exactly top_k experts should have nonzero gate weight
    # for each token. The layer must expose the per-token weight matrix used
    # to combine experts as `moe.last_gate_weights` with shape (T, n_experts).
    torch.manual_seed(0)
    moe = MoEFeedForward(_cfg(n_experts=4, top_k=2))
    x = torch.randn(3, 7, 16)
    moe(x)
    w = moe.last_gate_weights  # (T, n_experts), T = 3*7
    nonzero_per_token = (w > 0).sum(dim=-1)
    assert torch.all(nonzero_per_token == 2)


def test_kept_gate_weights_sum_to_one_per_token():
    torch.manual_seed(0)
    moe = MoEFeedForward(_cfg(n_experts=4, top_k=2))
    x = torch.randn(3, 7, 16)
    moe(x)
    w = moe.last_gate_weights  # (T, n_experts)
    row_sums = w.sum(dim=-1)
    assert torch.allclose(row_sums, torch.ones_like(row_sums), atol=1e-5)


def test_unselected_experts_do_not_affect_output():
    # If an expert's weight is zero for every token, perturbing that expert's
    # parameters must not change the output. Pick the globally least-used expert.
    torch.manual_seed(0)
    moe = MoEFeedForward(_cfg(n_experts=4, top_k=1))  # top_k=1 => 3 experts unused per token
    x = torch.randn(1, 4, 16)
    out_before = moe(x).clone()
    w = moe.last_gate_weights  # (T, n_experts)
    dead_expert = int((w > 0).sum(dim=0).argmin())
    assert (w[:, dead_expert] == 0).all()  # confirm it's unused for all tokens
    with torch.no_grad():
        for p in moe.experts[dead_expert].parameters():
            p.add_(100.0)
    out_after = moe(x)
    assert torch.allclose(out_before, out_after, atol=1e-5)
