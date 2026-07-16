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

    corpus_text = Path(config.data_path).read_text()

    tokenizer = BPETokenizer(num_merges=config.num_merges)
    Path(config.tokenizer_path).parent.mkdir(parents=True, exist_ok=True)
    tokenizer.train(corpus_text)
    tokenizer.save(config.tokenizer_path)

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
    for step in range(config.steps):
        x, y = get_batch(train_data, config.context_length, config.batch_size, generator)
        logits = model(x) # logits is (batch, context_length, vocab_size)
        loss = F.cross_entropy(logits.view(-1,model_config.vocab_size), y.view(-1))
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
        if step % config.eval_interval == 0 or step == config.steps - 1:
            model.eval()
            with torch.no_grad():
                val_x, val_y = get_batch(val_data, config.context_length, config.batch_size, generator)
                val_logits = model(val_x)
                val_loss = F.cross_entropy(val_logits.view(-1, model_config.vocab_size), val_y.view(-1))
            model.train()
            val_losses[step] = val_loss.item()
    Path(config.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"model_state_dict": model.state_dict(), "model_config": model_config.__dict__},config.checkpoint_path,
        )
    return TrainResult(
        losses=losses,
        val_losses=val_losses,
        checkpoint_path=config.checkpoint_path,
        tokenizer_path=config.tokenizer_path,
    )