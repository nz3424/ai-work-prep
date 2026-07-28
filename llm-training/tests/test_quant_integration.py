import torch

from src.ternary_quant import BitLinear
from src.transformer import ModelConfig, TinyTransformer


def _cfg(quantize):
    return ModelConfig(
        vocab_size=32,
        context_length=16,
        d_model=16,
        n_layers=2,
        n_heads=2,
        d_ff=32,
        quantize_linears=quantize,
    )


def test_flag_off_uses_plain_linear_and_is_unchanged():
    torch.manual_seed(0)
    fp = TinyTransformer(_cfg(False))
    assert not any(isinstance(m, BitLinear) for m in fp.modules())
    # FP path byte-identical: same seed -> identical initial params
    torch.manual_seed(0)
    fp2 = TinyTransformer(_cfg(False))
    for a, b in zip(fp.parameters(), fp2.parameters()):
        assert torch.equal(a, b)


def test_flag_on_quantizes_body_but_holds_out_head_and_embedding():
    m = TinyTransformer(_cfg(True))
    body = [
        mod
        for name, mod in m.named_modules()
        if any(k in name for k in ("q_proj", "k_proj", "v_proj", "out_proj", "ffn"))
        and hasattr(mod, "weight")
        and mod.weight.dim() == 2
    ]
    assert body and all(isinstance(b, BitLinear) for b in body)
    assert not isinstance(m.head, BitLinear)  # head held out in FP
    assert type(m.token_embedding).__name__ == "Embedding"  # embedding held out
