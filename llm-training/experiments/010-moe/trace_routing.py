"""Trace one MoE forward pass in slow motion.

Mechanics checkpoint for exp 010: feed a tiny batch through a single
MoEFeedForward and print every intermediate tensor, so the routing can be
eyeballed before trusting a full training run.

Run from the llm-training dir:  python3 -m experiments.010-moe.trace_routing
"""

import torch
import torch.nn.functional as F

from src.moe import MoEFeedForward
from src.transformer import ModelConfig


def main() -> None:
    torch.manual_seed(0)

    # 1. Small, readable config: 4 experts, top-2, tiny dims.
    config = ModelConfig(vocab_size=100, d_model=16, d_ff=32,
                         use_moe=True, n_experts=4, top_k=2)
    moe = MoEFeedForward(config)

    # 2. One short sequence keeps the printout small: (batch=1, seq=6, d_model=16).
    x = torch.randn(1, 6, config.d_model)

    # 3. Run the layer once. This populates moe.last_gate_weights and
    #    moe.last_aux_loss as a side effect.
    out = moe(x)

    # 4. Recompute the routing internals for display (forward doesn't expose
    #    them). Mirror the first few lines of MoEFeedForward.forward:
    flat = x.reshape(-1, config.d_model)          # (T, d_model), T = 6
    gate_logits = moe.router(flat) # score the tokens for each expert
    gate_probs = F.softmax(gate_logits, dim=-1)

    topv, topi = gate_probs.topk(moe.top_k, dim = -1)
    topv = topv / topv.sum(dim=-1, keepdim=True) 

    # 5. Print each stage. Suggested order + what to confirm by eye:
    torch.set_printoptions(precision=3, sci_mode=False)
    print("gate_logits:\n", gate_logits)
    print("gate_probs:\n", gate_probs)
    print("topv:\n", topv)
    print("topi:\n", topi)
    print("moe.last_gate_weights:\n", moe.last_gate_weights)
    print("per-expert counts:\n", (moe.last_gate_weights > 0).sum(dim=0))
    print("moe.last_aux_loss:\n", moe.last_aux_loss)
    print("out.shape:\n", out.shape)



if __name__ == "__main__":
    main()
