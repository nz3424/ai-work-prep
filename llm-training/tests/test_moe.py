import torch

from src.moe import MoEFeedForward, load_balance_loss
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


def test_balanced_uniform_routing_gives_minimum_aux():
    # N=4 experts, top_k=1, one token per expert, uniform gate probs.
    # f_i = 1/4 (each expert gets one of four tokens), P_i = 1/4.
    # aux = N * sum_i f_i * P_i = 4 * (4 * (1/4)*(1/4)) = 1.0  -> the balanced minimum.
    n_experts = 4
    gate_probs = torch.full((4, n_experts), 0.25)
    topi = torch.tensor([[0], [1], [2], [3]])
    aux = load_balance_loss(gate_probs, topi, n_experts)
    assert aux.shape == ()  # scalar
    assert torch.isclose(aux, torch.tensor(1.0), atol=1e-5)


def test_collapsed_routing_has_higher_aux_than_balanced():
    n_experts = 4
    # Collapsed: every token routed to expert 0, and probs concentrated there.
    collapsed_probs = torch.tensor([[0.7, 0.1, 0.1, 0.1]] * 4)
    collapsed_topi = torch.zeros(4, 1, dtype=torch.long)
    collapsed = load_balance_loss(collapsed_probs, collapsed_topi, n_experts)
    # Balanced reference.
    balanced = load_balance_loss(torch.full((4, n_experts), 0.25),
                                 torch.tensor([[0], [1], [2], [3]]), n_experts)
    assert collapsed > balanced


def test_aux_is_non_negative_scalar_after_forward():
    torch.manual_seed(0)
    moe = MoEFeedForward(_cfg())
    moe(torch.randn(2, 5, 16))
    assert moe.last_aux_loss.shape == ()
    assert moe.last_aux_loss.item() >= 0.0
    assert torch.isfinite(moe.last_aux_loss)
