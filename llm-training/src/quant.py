import torch
from src.transformer import ModelConfig, TinyTransformer

def quantize(w, s: torch.Tensor, z=0, q_min=-127, q_max=127):
    # w_q = clip(round(w/s) + z, q_min, q_max)   — return integer tensor
    w_q = torch.clamp(torch.round(w/s) + z, q_min, q_max)
    return w_q.to(torch.int8)

def dequantize(w_q, s: torch.Tensor, z=0):

    w_hat = s * (w_q.to(torch.float32) - z)
    return w_hat

def absmax_scale(w, q_max=127, dim=None):
    # s = max(|w|) / q_max
    # add a dim
    if dim is None:
        s = torch.amax(torch.abs(w)) / q_max
    else:
        s = torch.amax(torch.abs(w), dim = dim, keepdim=True) / q_max
    return s


if __name__ == "__main__":
    torch.manual_seed(0)
    cfg = ModelConfig(vocab_size=1006)
    model = TinyTransformer(cfg)

    # W1: the FFN up-projection, shape (d_ff=512, d_model=128) — transformer.py:24
    W = model.blocks[0].ffn[0].weight.detach()

    # ------- quantization of the FFN up-projection weights -------
    s = absmax_scale(W)
    W_hat = dequantize(quantize(W, s), s)

    err = (W_hat - W)
    print("A: MSE =", (err**2).mean().item())
    print("A: max abs err =", err.abs().max().item(), " vs  s/2 =", (s/2).item())

    # ---- symmetric vs asymmetric quantization of the FFN post-GELU activations ----
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

    # --------- granularity: per-tensor vs per-channel (per output row) quantization ---------
    # per-tensor
    s_pt = absmax_scale(W)                 # scalar
    W_pt = dequantize(quantize(W, s_pt), s_pt)

    # per-channel (per output row)
    s_pc = absmax_scale(W, dim=1)          # (512, 1)
    W_pc = dequantize(quantize(W, s_pc), s_pc)

    print("per-tensor  MSE =", ((W_pt - W)**2).mean().item())
    print("per-channel MSE =", ((W_pc - W)**2).mean().item())
    print("\n")

    W_out = W.clone()
    W_out[0] *= 20.0        # one outlier row

    s_pt = absmax_scale(W_out)
    s_pc = absmax_scale(W_out, dim=1)
    # ... quantize/dequantize both, print MSE of each vs W_out ...

    W_pt_out = dequantize(quantize(W_out, s_pt), s_pt)

    # per-channel (per output row)
    W_pc_out = dequantize(quantize(W_out, s_pc), s_pc)

    print("per-tensor  MSE =", ((W_pt_out - W_out)**2).mean().item())
    print("per-channel MSE =", ((W_pc_out - W_out)**2).mean().item())

    # --------- check for outliers in attention weights, and how per-channel quantization helps ---------
    from src.generate import load_checkpoint
    trained, _ = load_checkpoint("checkpoints/002-rope/model.pt", "checkpoints/002-rope/tokenizer.json")
    print("\n--- TRAINED weights ---")
    b0t = trained.blocks[0]
    for name, Wp in [("ffn.W1", b0t.ffn[0].weight.detach()),
                    ("q_proj", b0t.attention.q_proj.weight.detach()),
                    ("k_proj", b0t.attention.k_proj.weight.detach()),
                    ("v_proj", b0t.attention.v_proj.weight.detach()),
                    ("out_proj", b0t.attention.out_proj.weight.detach())]:
        s_pt, s_pc = absmax_scale(Wp), absmax_scale(Wp, dim=1)
        mse_pt = ((dequantize(quantize(Wp, s_pt), s_pt) - Wp)**2).mean().item()
        mse_pc = ((dequantize(quantize(Wp, s_pc), s_pc) - Wp)**2).mean().item()
        print(f"{name:9s} per-tensor {mse_pt:.3e}  per-channel {mse_pc:.3e}  ratio {mse_pt/mse_pc:.2f}")
    