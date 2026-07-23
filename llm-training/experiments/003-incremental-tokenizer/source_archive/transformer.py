from dataclasses import dataclass

import torch
import torch.nn as nn

from src.attention import CausalSelfAttention

@dataclass
class ModelConfig:
    vocab_size: int
    context_length: int = 256
    d_model: int = 128
    n_layers: int = 4
    n_heads: int = 4
    d_ff: int = 512

class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.d_model)
        self.attention = CausalSelfAttention(config.d_model, config.n_heads)
        self.ln2 = nn.LayerNorm(config.d_model)
        self.ffn = nn.Sequential(
            nn.Linear(config.d_model, config.d_ff),
            nn.GELU(),
            nn.Linear(config.d_ff, config.d_model),
        )
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x is (batch, seq_len, d_model) in, same shape out
        x = x + self.attention(self.ln1(x))
        x = x + self.ffn(self.ln2(x))
        return x

class TinyTransformer(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model)

        self.blocks = nn.ModuleList([TransformerBlock(config) for _ in range(config.n_layers)])
        self.ln = nn.LayerNorm(config.d_model)
        #* check if we should have bias
        self.head = nn.Linear(config.d_model, config.vocab_size, bias=False)
    def forward(self, idx: torch.Tensor) -> torch.Tensor: 
    # idx is (batch, seq_len) of token ids, out is (batch, seq_len, vocab_size) logits
    # must also expose self.config — train.py/generate.py read .config.context_length
        _, seq_len = idx.size()
        assert seq_len <= self.config.context_length, f"sequence length {seq_len} exceeds context_length {self.config.context_length}"
        token_embeddings = self.token_embedding(idx)

        x = token_embeddings
        for block in self.blocks:
            x = block(x)
        x = self.ln(x)
        logits = self.head(x)
        return logits
  