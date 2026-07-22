import torch

from src.attention import CausalSelfAttention, _apply_rope, _rope_cos_sin, _rotate_half


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


def test_rope_position_zero_is_identity():
    # At position 0 the rotation angle is 0 (cos=1, sin=0), so RoPE must leave
    # the vector untouched.
    attn = CausalSelfAttention(d_model=16, n_heads=2)
    torch.manual_seed(0)
    x = torch.randn(1, attn.d_head)  # a single token's head vector

    cos, sin = _rope_cos_sin(torch.tensor([0.0]), attn.frequencies)
    rotated = _apply_rope(x, cos, sin)

    assert torch.allclose(rotated, x, atol=1e-6)


def test_rope_score_depends_only_on_relative_position():
    # The defining property of RoPE: the dot product between a query rotated at
    # position m and a key rotated at position n depends only on (m - n). So
    # shifting both positions by the same delta must leave the score unchanged.
    attn = CausalSelfAttention(d_model=16, n_heads=2)
    freq = attn.frequencies

    torch.manual_seed(0)
    q = torch.randn(1, attn.d_head)
    k = torch.randn(1, attn.d_head)

    def score(m, n):
        cos_m, sin_m = _rope_cos_sin(torch.tensor([float(m)]), freq)
        cos_n, sin_n = _rope_cos_sin(torch.tensor([float(n)]), freq)
        q_rot = _apply_rope(q, cos_m, sin_m)
        k_rot = _apply_rope(k, cos_n, sin_n)
        return (q_rot * k_rot).sum()

    for m, n, delta in [(0, 0, 5), (3, 1, 4), (7, 2, 10)]:
        assert torch.allclose(score(m, n), score(m + delta, n + delta), atol=1e-5)


def test_rope_preserves_norm():
    # Rotation is orthogonal, so it cannot change a vector's length regardless
    # of position.
    attn = CausalSelfAttention(d_model=16, n_heads=2)
    torch.manual_seed(0)
    x = torch.randn(1, attn.d_head)
    original_norm = x.norm(dim=-1)

    for m in [0, 1, 7, 42, 500]:
        cos, sin = _rope_cos_sin(torch.tensor([float(m)]), attn.frequencies)
        rotated = _apply_rope(x, cos, sin)
        assert torch.allclose(rotated.norm(dim=-1), original_norm, atol=1e-5)


def test_rotate_half():
    # Half-split convention: [a, b, c, d] -> [-c, -d, a, b].
    out = _rotate_half(torch.tensor([1.0, 2.0, 3.0, 4.0]))
    assert torch.equal(out, torch.tensor([-3.0, -4.0, 1.0, 2.0]))


def test_gradients_flow_through_all_projections():
    attn = CausalSelfAttention(d_model=8, n_heads=2)
    x = torch.randn(2, 5, 8, requires_grad=True)

    out = attn(x)
    out.sum().backward()

    for name, proj in (("q_proj", attn.q_proj), ("k_proj", attn.k_proj),
                        ("v_proj", attn.v_proj), ("out_proj", attn.out_proj)):
        assert proj.weight.grad is not None, f"{name}.weight got no gradient"
        assert not torch.all(proj.weight.grad == 0), f"{name}.weight gradient is all zero"


def test_batch_items_do_not_leak_into_each_other():
    attn = CausalSelfAttention(d_model=8, n_heads=2)
    attn.eval()

    torch.manual_seed(0)
    x = torch.randn(2, 4, 8)

    out_batched = attn(x)
    out_single = attn(x[0:1])

    # Attention with a proper batch dimension must treat each batch item
    # independently — item 0's output shouldn't depend on what's sitting in
    # item 1's slot. A reshape/transpose bug that accidentally mixes the
    # batch dimension into the sequence or head dimension would break this.
    assert torch.allclose(out_batched[0], out_single[0], atol=1e-6)


def test_output_correct_after_mask_cache_grows_then_shrinks():
    # CausalSelfAttention lazily grows a cached causal_mask buffer sized to
    # the largest seq_len seen so far, then slices it down for smaller calls.
    # This pins that a later, smaller-seq_len call still masks correctly
    # after the cache has already grown from an earlier, longer call.
    attn = CausalSelfAttention(d_model=4, n_heads=1)
    attn.eval()

    torch.manual_seed(0)
    attn(torch.randn(1, 6, 4))  # grows the cached mask to 6x6

    x1 = torch.randn(1, 3, 4)
    x2 = x1.clone()
    x2[0, 2, :] = torch.randn(4)  # change only the last token

    out1 = attn(x1)
    out2 = attn(x2)

    assert torch.allclose(out1[0, 0], out2[0, 0], atol=1e-6)
    assert torch.allclose(out1[0, 1], out2[0, 1], atol=1e-6)


def test_rope_cache_slice_matches_fresh_build():
    # The RoPE cos/sin cache grows to the largest seq_len seen and slices down
    # for smaller calls. A shorter forward after a longer one must produce the
    # exact same output as one whose cache was built fresh at that length —
    # i.e. the [:seq_len] slice returns correct values, not just a valid shape.
    cold = CausalSelfAttention(d_model=8, n_heads=2)
    cold.eval()
    warm = CausalSelfAttention(d_model=8, n_heads=2)
    warm.eval()
    warm.load_state_dict(cold.state_dict())

    torch.manual_seed(0)
    x = torch.randn(1, 3, 8)

    out_cold = cold(x)              # cache built fresh at seq_len 3
    warm(torch.randn(1, 6, 8))      # grow warm's cache to seq_len 6 first
    out_warm = warm(x)             # then seq_len 3 must slice the cache

    assert warm.cos_cached.size(0) == 6  # cache grew and was not rebuilt smaller
    assert torch.allclose(out_cold, out_warm, atol=1e-6)
