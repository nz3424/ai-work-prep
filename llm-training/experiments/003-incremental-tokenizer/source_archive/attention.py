import math
import torch
import torch.nn as nn
import torch.nn.functional as F

def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x[..., :x.shape[-1] // 2], x[..., x.shape[-1] // 2:]
    return torch.cat([-x2, x1], dim=-1)

def _rope_cos_sin(positions: torch.Tensor,
                  frequencies: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    # Builds the (len(positions), d_head) cos/sin tables. Pure function of
    # position and the fixed frequencies, so the result is cacheable.
    angle_table = torch.outer(positions, frequencies)
    cos, sin = angle_table.cos(), angle_table.sin()
    return torch.cat([cos, cos], dim=-1), torch.cat([sin, sin], dim=-1)


def _apply_rope(x: torch.Tensor, cos: torch.Tensor,
                sin: torch.Tensor) -> torch.Tensor:
    return x * cos + _rotate_half(x) * sin

class CausalSelfAttention(nn.Module):
    def __init__(self, d_model: int, n_heads: int):
        super().__init__() 
        self.d_model = d_model
        self.n_heads = n_heads
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"
        self.d_head = d_model // n_heads

        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)

        # for rotary embeddings
        self.register_buffer("frequencies", torch.pow(10000, -torch.arange(0, self.d_head, 2) / self.d_head), persistent=False)

        # Lazily built/grown in forward() since seq_len isn't known until then;
        # persistent=False keeps this derived tensor out of state_dict()/checkpoints.
        self.register_buffer("causal_mask", None, persistent=False)
        # RoPE cos/sin tables, cached and grown the same lazy way as the mask.
        self.register_buffer("cos_cached", None, persistent=False)
        self.register_buffer("sin_cached", None, persistent=False)

    def _cos_sin(self, seq_len: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
        # Rebuild the cache only when we see a longer sequence than before;
        # otherwise slice the existing table down to seq_len.
        if self.cos_cached is None or self.cos_cached.size(0) < seq_len:
            positions = torch.arange(seq_len, device=device, dtype=torch.float32)
            self.cos_cached, self.sin_cached = _rope_cos_sin(positions, self.frequencies)
        return self.cos_cached[:seq_len], self.sin_cached[:seq_len]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size, seq_len, _ = x.shape
        q = self.q_proj(x).reshape(batch_size, seq_len, self.n_heads, self.d_head).transpose(1, 2)
        k = self.k_proj(x).reshape(batch_size, seq_len, self.n_heads, self.d_head).transpose(1, 2)
        v = self.v_proj(x).reshape(batch_size, seq_len, self.n_heads, self.d_head).transpose(1, 2)

        cos, sin = self._cos_sin(seq_len, x.device)
        k_rot = _apply_rope(k, cos, sin)
        q_rot = _apply_rope(q, cos, sin)
        
        attention_scores = torch.matmul(q_rot, k_rot.transpose(-2, -1)) / math.sqrt(self.d_head)
        if self.causal_mask is None or self.causal_mask.size(0) < seq_len:
            self.causal_mask = torch.triu(
                torch.ones(seq_len, seq_len, dtype=torch.bool, device=x.device), diagonal=1
            )
        mask = self.causal_mask[:seq_len, :seq_len]
        attention_scores = attention_scores.masked_fill(mask, float('-inf'))

        attention_probs = F.softmax(attention_scores, dim=-1)
        attention_output = torch.matmul(attention_probs, v) 
        attention_output = attention_output.transpose(1, 2).reshape(batch_size, seq_len, self.d_model) 
        output = self.out_proj(attention_output)
        return output
