import torch

from src.train import TrainConfig, train_model


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
