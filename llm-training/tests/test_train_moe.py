import torch

from src.train import TrainConfig, train_model, _parse_args


def test_cli_flags_thread_moe_into_trainconfig(monkeypatch):
    # Regression: the --use-moe family of flags must actually reach TrainConfig.
    # A prior bug parsed them but dropped them from the returned config, so
    # `--use-moe` runs silently trained a dense model.
    monkeypatch.setattr(
        "sys.argv",
        ["train.py", "--use-moe", "--n-experts", "8", "--top-k", "3",
         "--moe-aux-loss-coef", "0.02"],
    )
    cfg = _parse_args()
    assert cfg.use_moe is True
    assert cfg.n_experts == 8
    assert cfg.top_k == 3
    assert cfg.moe_aux_loss_coef == 0.02


def test_moe_training_runs_and_loss_decreases(tmp_path):
    data = tmp_path / "corpus.txt"
    # Varied text: a repeated sentence collapses under BPE to a handful of
    # tokens, starving the val split. 150 distinct "words" keep enough entropy.
    data.write_text(" ".join(f"word{i % 150}" for i in range(3000)))
    cfg = TrainConfig(
        data_path=str(data),
        checkpoint_path=str(tmp_path / "m.pt"),
        tokenizer_path=str(tmp_path / "tok.json"),
        steps=40, batch_size=8, context_length=16, num_merges=60,
        eval_interval=20, d_model=16, n_layers=2, n_heads=2, d_ff=32,
        use_moe=True, n_experts=4, top_k=2, moe_aux_loss_coef=0.01,
    )
    result = train_model(cfg)
    assert len(result.losses) == 40
    # Later-window mean below early-window mean: the MoE model is learning.
    assert sum(result.losses[-10:]) / 10 < sum(result.losses[:10]) / 10
