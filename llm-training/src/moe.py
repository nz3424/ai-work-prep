import torch
import torch.nn as nn
import torch.nn.functional as F

from src.ternary_quant import make_linear

def load_balance_loss(gate_probs, topi, n_experts) -> torch.Tensor:
    # gate_probs: (T, n_experts)
    # topi: (T, top_k)
    # n_experts: int
    P = gate_probs.mean(dim = 0)

    chosen = F.one_hot(topi, n_experts).sum(dim=1).clamp(max=1)
    f = chosen.float().mean(dim=0)
    aux = n_experts * (P * f).sum()

    return aux

class MoEFeedForward(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.n_experts = config.n_experts
        self.top_k = config.top_k

        # decision maker to route to the top-k experts
        self.router = nn.Linear(config.d_model, self.n_experts, bias=False)

        self.experts = nn.ModuleList([
            nn.Sequential(
                make_linear(config.quantize_linears, config.d_model, config.d_ff, quantize_activations=config.quantize_activations),
                nn.GELU(),
                make_linear(config.quantize_linears, config.d_ff, config.d_model, quantize_activations=config.quantize_activations)
            )
            for _ in range(self.n_experts)
        ])

        self.last_gate_weights = None  # store the last gate weights for auxiliary loss computation
        self.last_aux_loss = None # store the last auxiliary loss for logging
    
    def forward(self, x):
        # x is (batch, seq_len, d_model)
        batch_size, seq_len, d_model = x.shape
        flat = x.reshape(batch_size * seq_len, d_model) #  flatten to token list

        gate_logits = self.router(flat) # score the tokens for each expert
        gate_probs = F.softmax(gate_logits, dim=-1)

        topv, topi = gate_probs.topk(self.top_k, dim = -1)
        topv = topv / topv.sum(dim=-1, keepdim=True) 

        weights = torch.zeros_like(gate_probs)
        self.last_gate_weights = weights
        weights.scatter_(1, topi, topv)

        out = torch.zeros_like(flat)
        for e in range(self.n_experts):
            out = out + weights[:, e:e+1] * self.experts[e](flat)

        self.last_aux_loss = load_balance_loss(gate_probs, topi, self.n_experts)

        return out.reshape(batch_size, seq_len, d_model)