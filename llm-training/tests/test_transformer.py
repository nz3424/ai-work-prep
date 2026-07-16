import math

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
