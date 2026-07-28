import torch

from src.train import TrainConfig, get_batch, train_model
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


def test_quantize_activations_persists_to_saved_model_config(tmp_path):
    # Load-bearing: the flag must survive into the checkpoint's model_config,
    # or eval on the 005 harness reconstructs an activation-FP model and the
    # 66.6/627/52.7 measurement axis silently breaks.
    result = train_model(_tiny_config(tmp_path, steps=20, quantize_linears=True,
                                      quantize_activations=True))

    checkpoint = torch.load(result.checkpoint_path, map_location="cpu")
    assert checkpoint["model_config"]["quantize_activations"] is True

    # And it round-trips: rebuilding from the saved config yields the quantized
    # forward pass eval depends on.
    reloaded = ModelConfig(**checkpoint["model_config"])
    assert reloaded.quantize_activations is True


def test_grad_checkpoint_run_matches_plain_run(tmp_path):
    # End-to-end proof of the OOM fix: gradient checkpointing must leave the
    # loss trajectory bit-identical (same seed everywhere), so it's purely a
    # memory optimization — 008's ppl stays comparable to 007's.
    plain_dir = tmp_path / "plain"
    ckpt_dir = tmp_path / "ckpt"
    plain_dir.mkdir()
    ckpt_dir.mkdir()

    r_plain = train_model(_tiny_config(plain_dir, steps=30))
    r_ckpt = train_model(_tiny_config(ckpt_dir, steps=30, grad_checkpoint=True))

    assert r_plain.losses == r_ckpt.losses


def test_get_batch_shapes_and_next_token_shift():
    # data[i] == i, so for any valid window y must equal x + 1 elementwise —
    # this pins the shape *and* the "y is x shifted one position later"
    # correctness property in one check, independent of get_batch's internals.
    data = torch.arange(0, 1000)
    generator = torch.Generator().manual_seed(0)

    x, y = get_batch(data, context_length=10, batch_size=4, generator=generator)

    assert x.shape == (4, 10)
    assert y.shape == (4, 10)
    assert torch.equal(y, x + 1)


def test_get_batch_windows_stay_in_bounds():
    data = torch.arange(0, 50)
    generator = torch.Generator().manual_seed(1)

    for _ in range(20):
        x, y = get_batch(data, context_length=10, batch_size=8, generator=generator)
        assert x.min() >= 0
        assert y.max() <= 49


def test_train_model_is_reproducible_with_same_seed(tmp_path):
    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"
    run1_dir.mkdir()
    run2_dir.mkdir()

    result1 = train_model(_tiny_config(run1_dir, steps=30))
    result2 = train_model(_tiny_config(run2_dir, steps=30))

    # Same seed everywhere (model init, get_batch sampling) must produce
    # bit-identical loss curves — this is what makes an experiment's
    # results.md reproducible from its training_config.txt.
    assert result1.losses == result2.losses


def test_val_losses_recorded_at_eval_interval_steps(tmp_path):
    config = _tiny_config(tmp_path, steps=250, eval_interval=100)
    result = train_model(config)

    assert set(result.val_losses.keys()) == {0, 100, 200, 249}


def test_timing_is_recorded(tmp_path):
    # Every experiment should capture phase timing so future run-length
    # estimates are grounded in measured data, not guesses.
    log_path = tmp_path / "training.log"
    result = train_model(_tiny_config(tmp_path, steps=20, log_path=str(log_path)))

    assert result.tokenizer_seconds > 0
    assert result.training_seconds > 0
    # Total spans both phases (plus encode/setup), so it can't be smaller.
    assert result.total_seconds >= result.training_seconds

    # The durations are also persisted to the log for committed experiments.
    log_text = log_path.read_text()
    assert "timing tokenizer_build_seconds" in log_text
    assert "timing training_seconds" in log_text
    assert "timing total_seconds" in log_text
