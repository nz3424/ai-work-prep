import argparse
import time
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from pathlib import Path
from src.tokenizer import BPETokenizer
from src.transformer import ModelConfig, TinyTransformer
@dataclass

class TrainConfig:
    data_path: str
    checkpoint_path: str
    tokenizer_path: str
    steps: int = 200
    batch_size: int = 16
    context_length: int = 256
    lr: float = 3e-4
    num_merges: int = 500
    seed: int = 0
    log_path: str | None = None
    d_model: int = 128
    n_layers: int = 4
    n_heads: int = 4
    d_ff: int = 512
    val_fraction: float = 0.1
    eval_interval: int = 50

@dataclass
class TrainResult:
    losses: list[float]
    val_losses: dict[int, float]
    checkpoint_path: str
    tokenizer_path: str
    tokenizer_seconds: float = 0.0
    training_seconds: float = 0.0
    total_seconds: float = 0.0

def get_batch(data: torch.Tensor, context_length: int, batch_size: int, generator: torch.Generator) -> tuple[torch.Tensor, torch.Tensor]:
    seq_len = data.size(0)
    starts = torch.randint(0, seq_len - context_length - 1, (batch_size,), generator=generator)
    offsets = torch.arange(context_length)
    idx = starts.unsqueeze(1) + offsets.unsqueeze(0) 
    x = data[idx]
    y = data[idx + 1]
    return x, y
def train_model(config: TrainConfig) -> TrainResult:
    torch.manual_seed(config.seed)
    generator = torch.Generator().manual_seed(config.seed)

    Path(config.tokenizer_path).parent.mkdir(parents=True, exist_ok=True)
    log_file = open(config.log_path, "w") if config.log_path else None

    def emit(line: str) -> None:
        # Print and (if logging) append+flush, so `tail -f` on the log shows
        # live step/timing progress during a long unattended fleet run.
        print(line)
        if log_file:
            log_file.write(line + "\n")
            log_file.flush()

    try:
        run_start = time.perf_counter()
        corpus_text = Path(config.data_path).read_text()

        # Time the tokenizer build separately — its naive per-merge corpus
        # rescan is usually the slowest single phase of a run.
        tokenizer = BPETokenizer(num_merges=config.num_merges)
        tokenizer_start = time.perf_counter()
        tokenizer.train(corpus_text)
        tokenizer_seconds = time.perf_counter() - tokenizer_start
        tokenizer.save(config.tokenizer_path)
        emit(f"timing tokenizer_build_seconds {tokenizer_seconds:.2f}")

        encoded_data = torch.tensor(tokenizer.encode(corpus_text), dtype=torch.long)
        val_size = int(len(encoded_data) * config.val_fraction)
        train_data = encoded_data[:-val_size]
        val_data = encoded_data[-val_size:]

        assert len(train_data) > config.context_length, "train split shorter than context_length"
        assert len(val_data) > config.context_length, "val split shorter than context_length"

        model_config = ModelConfig(
            vocab_size=tokenizer.vocab_size,
            context_length=config.context_length,
            d_model=config.d_model,
            n_layers=config.n_layers,
            n_heads=config.n_heads,
            d_ff=config.d_ff,
        )
        model = TinyTransformer(model_config)
        optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)

        losses = []
        val_losses = {}
        training_start = time.perf_counter()
        for step in range(config.steps):
            x, y = get_batch(train_data, config.context_length, config.batch_size, generator)
            logits = model(x) # logits is (batch, context_length, vocab_size)
            loss = F.cross_entropy(logits.view(-1,model_config.vocab_size), y.view(-1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
            line = f"step {step} train_loss {loss.item():.4f}"

            if step % config.eval_interval == 0 or step == config.steps - 1:
                model.eval()
                with torch.no_grad():
                    val_x, val_y = get_batch(val_data, config.context_length, config.batch_size, generator)
                    val_logits = model(val_x)
                    val_loss = F.cross_entropy(val_logits.view(-1, model_config.vocab_size), val_y.view(-1))
                model.train()
                val_losses[step] = val_loss.item()
                line += f" val_loss {val_loss.item():.4f}"

            emit(line)

        training_seconds = time.perf_counter() - training_start
        total_seconds = time.perf_counter() - run_start
        steps_per_second = config.steps / training_seconds if training_seconds > 0 else 0.0
        emit(f"timing training_seconds {training_seconds:.2f}")
        emit(f"timing steps_per_second {steps_per_second:.2f}")
        emit(f"timing total_seconds {total_seconds:.2f}")
    finally:
        if log_file:
            log_file.close()

    Path(config.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"model_state_dict": model.state_dict(), "model_config": model_config.__dict__},config.checkpoint_path,
        )
    return TrainResult(
        losses=losses,
        val_losses=val_losses,
        checkpoint_path=config.checkpoint_path,
        tokenizer_path=config.tokenizer_path,
        tokenizer_seconds=tokenizer_seconds,
        training_seconds=training_seconds,
        total_seconds=total_seconds,
    )


def _parse_args() -> TrainConfig:
    parser = argparse.ArgumentParser(description="Train the from-scratch transformer on a text corpus.")
    parser.add_argument("--data-path", default="data/tinyshakespeare.txt")
    parser.add_argument("--checkpoint-path", default="checkpoints/model.pt")
    parser.add_argument("--tokenizer-path", default="checkpoints/tokenizer.json")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--context-length", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--num-merges", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--log-path", default=None)
    args = parser.parse_args()
    return TrainConfig(
        data_path=args.data_path,
        checkpoint_path=args.checkpoint_path,
        tokenizer_path=args.tokenizer_path,
        steps=args.steps,
        batch_size=args.batch_size,
        context_length=args.context_length,
        lr=args.lr,
        num_merges=args.num_merges,
        seed=args.seed,
        log_path=args.log_path,
    )


if __name__ == "__main__":
    train_model(_parse_args())