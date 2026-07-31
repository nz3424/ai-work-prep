import torch

from src.transformer import ModelConfig, TinyTransformer


def _cfg(use_moe: bool) -> ModelConfig:
    return ModelConfig(vocab_size=50, context_length=32, d_model=16, n_layers=2,
                       n_heads=2, d_ff=32, use_moe=use_moe, n_experts=4, top_k=2)


def test_moe_model_forward_shape():
    torch.manual_seed(0)
    model = TinyTransformer(_cfg(use_moe=True))
    idx = torch.randint(0, 50, (2, 8))
    logits = model(idx)
    assert logits.shape == (2, 8, 50)


def test_dense_path_unchanged_when_moe_off():
    # use_moe=False must build the dense nn.Sequential FFN, and aux loss must be zero.
    torch.manual_seed(0)
    model = TinyTransformer(_cfg(use_moe=False))
    assert isinstance(model.blocks[0].ffn, torch.nn.Sequential)
    idx = torch.randint(0, 50, (2, 8))
    model(idx)
    assert float(model.collect_moe_aux_loss()) == 0.0


def test_collect_aux_loss_positive_after_moe_forward():
    torch.manual_seed(0)
    model = TinyTransformer(_cfg(use_moe=True))
    idx = torch.randint(0, 50, (2, 8))
    model(idx)
    aux = model.collect_moe_aux_loss()
    assert aux.shape == ()
    assert aux.item() > 0.0
