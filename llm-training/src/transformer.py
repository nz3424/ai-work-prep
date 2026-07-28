from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.utils.checkpoint

from src.attention import CausalSelfAttention
from src.ternary_quant import make_linear
@dataclass
class ModelConfig:
    vocab_size: int
    context_length: int = 256
    d_model: int = 128
    n_layers: int = 4
    n_heads: int = 4
    d_ff: int = 512
    quantize_linears: bool = False
    quantize_activations: bool = False
    grad_checkpoint: bool = False

class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.d_model)
        self.attention = CausalSelfAttention(config.d_model, config.n_heads, quantize_linears=config.quantize_linears, quantize_activations=config.quantize_activations)
        self.ln2 = nn.LayerNorm(config.d_model)
        self.ffn = nn.Sequential(
            make_linear(config.quantize_linears, config.d_model, config.d_ff, quantize_activations=config.quantize_activations),
            nn.GELU(),
            make_linear(config.quantize_linears, config.d_ff, config.d_model, quantize_activations=config.quantize_activations),
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
            if self.config.grad_checkpoint and self.training:
                # Recompute block activations in backward instead of storing
                # them — trades ~30% compute for a large drop in peak memory.
                # Numerically transparent (deterministic block, no dropout).
                x = torch.utils.checkpoint.checkpoint(block, x, use_reentrant=False)
            else:
                x = block(x)
        x = self.ln(x)
        logits = self.head(x)
        return logits
  