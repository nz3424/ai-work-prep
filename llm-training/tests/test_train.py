import torch

from src.train import TrainConfig, train_model
from src.transformer import ModelConfig, TinyTransformer


SYNTHETIC_TEXT = "the quick brown fox jumps over the lazy dog. " * 200


def _tiny_config(tmp_path, **overrides) -> TrainConfig:
    data_path = tmp_path / "corpus.txt"
    data_path.write_text(SYNTHETIC_TEXT)
    defaults = dict(
        data_path=str(data_path),
        checkpoint_path=str(tmp_path / "model.pt"),
        tokenizer_path=str(tmp_path / "tokenizer.json"),
        steps=300,
        batch_size=8,
        context_length=32,
        lr=3e-3,
        num_merges=20,
        seed=0,
        d_model=32,
        n_layers=2,
        n_heads=2,
        d_ff=64,
        eval_interval=100,
    )
    defaults.update(overrides)
    return TrainConfig(**defaults)


def test_loss_decreases_over_smoke_run(tmp_path):
    result = train_model(_tiny_config(tmp_path))

    first_chunk = result.losses[:60]
    last_chunk = result.losses[-60:]
    assert sum(last_chunk) / len(last_chunk) < sum(first_chunk) / len(first_chunk)


def test_checkpoint_is_saved_and_loadable(tmp_path):
    result = train_model(_tiny_config(tmp_path, steps=20))

    checkpoint = torch.load(result.checkpoint_path, map_location="cpu")
    assert "model_state_dict" in checkpoint
    assert "model_config" in checkpoint

    reloaded_config = ModelConfig(**checkpoint["model_config"])
    reloaded_model = TinyTransformer(reloaded_config)
    reloaded_model.load_state_dict(checkpoint["model_state_dict"])  # raises on shape mismatch
