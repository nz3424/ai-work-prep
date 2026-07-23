import torch
from src.transformer import ModelConfig, TinyTransformer

def quantize(w, s, z=0, q_min=-127, q_max=127):
    # w_q = clip(round(w/s) + z, q_min, q_max)   — return integer tensor
    w_q = torch.clamp(torch.round(w/s) + z, q_min, q_max)
    return w_q.to(torch.int8)

def dequantize(w_q, s, z=0):
    w_hat = s * (w_q.to(torch.float32) - z)
    return w_hat

def absmax_scale(w, q_max=127):
    # s = max(|w|) / q_max
    s = torch.max(torch.abs(w)) / q_max
    return s


if __name__ == "__main__":
    torch.manual_seed(0)
    cfg = ModelConfig(vocab_size=1006)
    model = TinyTransformer(cfg)

    # W1: the FFN up-projection, shape (d_ff=512, d_model=128) — transformer.py:24
    W = model.blocks[0].ffn[0].weight.detach()

    s = absmax_scale(W)
    W_hat = dequantize(quantize(W, s), s)

    err = (W_hat - W)
    print("A: MSE =", (err**2).mean().item())
    print("A: max abs err =", err.abs().max().item(), " vs  s/2 =", (s/2).item())

    with torch.no_grad():
        idx = torch.randint(0, cfg.vocab_size, (4, 32))     # (batch, seq)
        x = model.token_embedding(idx)
        b0 = model.blocks[0]
        ffn_in    = b0.ln2(x + b0.attention(b0.ln1(x)))     # input to FFN
        post_gelu = b0.ffn[1](b0.ffn[0](ffn_in))            # GELU output — mostly >= 0

    # --- symmetric (z=0): wastes the negative half of the code range ---
    s_sym = absmax_scale(post_gelu)
    sym_hat = dequantize(quantize(post_gelu, s_sym), s_sym)

    # --- asymmetric: fit s and z to the ACTUAL [min, max] ---
    q_min, q_max = -127, 127
    mn, mx = post_gelu.min(), post_gelu.max()
    s_asym = (mx - mn) / (q_max - q_min)
    z_asym = int(torch.round(q_min - mn / s_asym))          # zero-point, an int
    asym_hat = dequantize(quantize(post_gelu, s_asym, z=z_asym), s_asym, z=z_asym)

    print("B: sym  MSE =", ((sym_hat  - post_gelu)**2).mean().item())
    print("B: asym MSE =", ((asym_hat - post_gelu)**2).mean().item())
