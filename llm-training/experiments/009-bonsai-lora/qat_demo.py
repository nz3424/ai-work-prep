"""
Micro weight-QAT demo (Option 2): does the straight-through estimator actually
let a NON-differentiable ternary round LEARN, and do Bonsai's clamp-round vs
canonical absmean behave differently as weights evolve?

No model, no tokenizer, no text — one linear layer fitting a fixed random
target, on CPU, in seconds. This isolates the QAT *mechanism* so you can watch
it work before scaling the same STE code up to real Bonsai (Option 1).

Setup:
  target  Y = X @ Wtrue^T          (Wtrue = fixed random full-precision matrix)
  model   pred = (X @ Wq^T) * s    (Wq = ternary quant of a trainable master W,
                                     s = a learned scale, mirroring Bonsai's
                                     "ternary weights + learned magnitude")
  train   W and s by SGD; Wq is re-quantized every step via the STE.

Run:  ../../.venv-hf/bin/python qat_demo.py
"""
import torch

torch.manual_seed(0)

# ---- toy problem (tiny, CPU) --------------------------------------------
IN, OUT, N, STEPS = 64, 32, 256, 400
X = torch.randn(N, IN)
Wtrue = torch.randn(OUT, IN)          # the target's true (full-precision) weights
Y = X @ Wtrue.t()                     # what we're trying to reproduce


# ---- the two weight-quant schemes (forward mapping to ternary) ----------
def clamp_round_q(w):
    """Bonsai's scheme: sign only, FIXED threshold at 0.5, scale-blind."""
    return w.clamp(-1, 1).round()

def absmean_q(w, eps=1e-5):
    """Canonical BitNet: normalize by mean|w| first, so the threshold ADAPTS
    to the weight scale."""
    g = w.abs().mean()
    return (w / (g + eps)).round().clamp(-1, 1)


def ternary_stats(wq):
    n = wq.numel()
    return (f"-1:{(wq==-1).sum().item()/n:.2f} "
            f"0:{(wq==0).sum().item()/n:.2f} "
            f"+1:{(wq==1).sum().item()/n:.2f}")


def train(quant, label):
    W = torch.randn(OUT, IN, requires_grad=True)   # full-precision MASTER weight
    s = (torch.ones(1)*0.4).requires_grad_(True)      # learned scale

    # break-the-scale init
  #  W = (torch.randn(OUT, IN) * 0.15).requires_grad_(True)  
  #  s = torch.ones(1)*5# make s not a learned value

    opt = torch.optim.Adam([W, s], lr=0.02) # add s as a trainable param for scale learning

    for step in range(STEPS):
        opt.zero_grad()
        # ----------------------------------------------------------------
        # weight: forward uses quant(W) (ternary), but the gradient must flow
        # back to the full-precision master W as if quant were the identity.
        # Pattern (same trick as the activation quant): W + (quant(W) - W).detach()
        Wq = W + (quant(W) - W).detach()
        # ----------------------------------------------------------------
        pred = (X @ Wq.t()) * s
        loss = ((pred - Y) ** 2).mean()
        loss.backward()
        opt.step()
        if step % 100 == 0 or step == STEPS - 1:
            with torch.no_grad():
                print(f"  [{label:11s}] step {step:3d}  loss {loss.item():8.4f}  "
                      f"scale {s.item():.3f}  {ternary_stats(quant(W))}")
    return loss.item()


def main():
    print("Micro weight-QAT: fit a fixed random target with TERNARY weights.\n")
    print("--- clamp-round (Bonsai) ---")
    l1 = train(clamp_round_q, "clamp-round")
    print("\n--- absmean (canonical BitNet) ---")
    l2 = train(absmean_q, "absmean")
    print(f"\nfinal loss  clamp-round={l1:.4f}  absmean={l2:.4f}  "
          f"-> {'absmean' if l2 < l1 else 'clamp-round'} fit better")


if __name__ == "__main__":
    main()
