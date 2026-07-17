import math

import pytest
import torch
import torch.nn.functional as F

from src.transformer import ModelConfig, TinyTransformer


def test_forward_pass_shape():
    config = ModelConfig(vocab_size=300, context_length=16, d_model=32, n_layers=2, n_heads=4, d_ff=64)
    model = TinyTransformer(config)
    idx = torch.randint(0, config.vocab_size, (2, 10))
    logits = model(idx)
    assert logits.shape == (2, 10, config.vocab_size)


def test_untrained_loss_near_uniform_baseline():
    config = ModelConfig(vocab_size=300, context_length=16, d_model=32, n_layers=2, n_heads=4, d_ff=64)
    model = TinyTransformer(config)
    model.eval()

    idx = torch.randint(0, config.vocab_size, (8, 15))
    targets = torch.randint(0, config.vocab_size, (8, 15))

    with torch.no_grad():
        logits = model(idx)
        loss = F.cross_entropy(logits.view(-1, config.vocab_size), targets.view(-1))

    baseline = math.log(config.vocab_size)
    # An untrained model's logits are small/near-zero-mean, so its loss
    # should be close to the uniform-distribution baseline -log(1/vocab_size)
    # — this confirms the model isn't structurally broken or biased before
    # any training happens.
    assert abs(loss.item() - baseline) < 0.75


def test_raises_when_sequence_exceeds_context_length():
    config = ModelConfig(vocab_size=50, context_length=8, d_model=16, n_layers=1, n_heads=2, d_ff=32)
    model = TinyTransformer(config)
    idx = torch.randint(0, config.vocab_size, (1, 9))  # one more than context_length

    with pytest.raises(AssertionError):
        model(idx)


def test_gradients_flow_to_all_parameters():
    config = ModelConfig(vocab_size=50, context_length=16, d_model=16, n_layers=2, n_heads=2, d_ff=32)
    model = TinyTransformer(config)
    idx = torch.randint(0, config.vocab_size, (2, 10))
    targets = torch.randint(0, config.vocab_size, (2, 10))

    logits = model(idx)
    loss = F.cross_entropy(logits.view(-1, config.vocab_size), targets.view(-1))
    loss.backward()

    # Catches wiring bugs where a submodule (an embedding table, a block, the
    # final head) is constructed but never actually used in forward().
    for name, param in model.named_parameters():
        assert param.grad is not None, f"{name} received no gradient"


def test_different_inputs_produce_different_logits():
    config = ModelConfig(vocab_size=50, context_length=16, d_model=16, n_layers=2, n_heads=2, d_ff=32)
    model = TinyTransformer(config)
    model.eval()

    torch.manual_seed(0)
    idx1 = torch.randint(0, config.vocab_size, (1, 10))
    idx2 = idx1.clone()
    idx2[0, 0] = (idx2[0, 0] + 1) % config.vocab_size  # change one token

    with torch.no_grad():
        out1 = model(idx1)
        out2 = model(idx2)

    assert not torch.allclose(out1, out2)
