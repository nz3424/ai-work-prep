# QAT + STE Ternary Weights (007) Implementation Plan

> **Mode: guided / hands-on.** Nick writes the load-bearing code (STE,
> quantizer, `BitLinear`); Claude guides and reviews. Per-task, the **test is
> given in full** (the target to satisfy) and the **interface + hints** are
> given, but the implementation body is intentionally left for Nick. Claude
> holds a reference solution and reveals it only at review. Boilerplate
> (experiment scaffold, config plumbing) Claude may write outright.

**Goal:** Add a `BitLinear` layer that fake-quantizes weights to ternary during
training via a straight-through estimator, swap it into the 24 body Linears,
and run 007 as a single-variable A/B against the 002-rope FP baseline.

**Architecture:** New `src/quant.py` holds the STE, the pluggable quantizers
(`ternary_absmean` default, `int8_absmax` sanity path), and `BitLinear`
(subclass of `nn.Linear`; keeps ternary matrix W̃ and per-tensor scale γ
separate, applying γ at the matmul output — representation (ii)). A
`quantize_linears` flag on `ModelConfig` swaps `nn.Linear → BitLinear` for body
projections only; `head` and `token_embedding` stay FP32.

**Tech Stack:** Python 3.11, PyTorch (CPU-only wheel on the fleet), pytest.

## Global Constraints

- Run the trainer as a module from `llm-training/`: `python3.11 -m src.train …`
  (never `python3.11 src/train.py`).
- FP baseline path must be **byte-identical** when `quantize_linears=False` —
  the 002 comparison depends on it.
- The quantizer must match BitNet b1.58 eqs (1)–(3) exactly (verified in the
  design doc): `γ = mean|W|` per-tensor, `W/(γ+ε)` with ε *inside* the
  denominator, `RoundClip = round then clamp(-1,1)`.
- 007 reuses **002's `tokenizer.json`** — do not rebuild the tokenizer.
- Body-only quantization: `head` + `token_embedding` held out in FP32.
- Commit frequently on branch `llm-training/007-qat-ternary`.

---

### Task 1: Straight-through round (the STE core)

**Files:**
- Create: `src/quant.py`
- Test: `tests/test_quant.py`

**Interfaces:**
- Produces: `ste_round(x: Tensor) -> Tensor` — forward returns `x.round()`;
  backward passes gradient straight through as identity (`d out/d x = 1`).

**The test (target — write/confirm this first):**

```python
import torch
from src.quant import ste_round

def test_ste_round_forward_is_round():
    x = torch.tensor([-1.4, -0.4, 0.6, 1.9])
    assert torch.equal(ste_round(x), torch.tensor([-1., 0., 1., 2.]))

def test_ste_round_backward_is_identity():
    x = torch.tensor([-1.4, 0.6, 1.9], requires_grad=True)
    ste_round(x).sum().backward()
    assert torch.equal(x.grad, torch.ones_like(x))  # not zeros
```

**Steps:**
- [ ] Step 1: Confirm the two tests above are in `tests/test_quant.py`.
- [ ] Step 2: Run them, verify they FAIL (`ImportError` / not defined).
      `PYTHONPATH=. python3.11 -m pytest tests/test_quant.py -q`
- [ ] Step 3: **Nick writes `ste_round`.** Hint: the whole trick is one line —
      make the forward value `round(x)` while the graph's gradient path runs
      through a term whose derivative is 1. Recall the `+ (… ).detach()` idiom.
- [ ] Step 4: Run the tests, verify PASS.
- [ ] Step 5: Commit (`git add src/quant.py tests/test_quant.py && git commit`).

---

### Task 2: Ternary absmean quantizer (BitNet eqs 1–3)

**Files:**
- Modify: `src/quant.py`
- Test: `tests/test_quant.py`

**Interfaces:**
- Consumes: `ste_round`.
- Produces: `ternary_absmean(w: Tensor, eps: float = 1e-5) -> tuple[Tensor,
  Tensor]` — returns `(w_tilde, gamma)`. `w_tilde ∈ {-1,0,+1}` **ste-valued**
  (ternary on forward, gradient flows to `w`); `gamma` is the per-tensor scalar
  `mean|W|`. Representation (ii): γ is **not** folded into `w_tilde`.

**The test (target):**

```python
import torch
from src.quant import ternary_absmean

def test_ternary_absmean_matches_paper():
    # γ = mean|W|; W̃ = RoundClip(W/(γ+ε), -1, 1)
    w = torch.tensor([[0.0, 0.2, -0.2], [0.4, -0.4, 0.05]])
    gamma_expected = w.abs().mean()                       # 0.2083...
    w_tilde, gamma = ternary_absmean(w)
    assert torch.allclose(gamma, gamma_expected)
    # hand-check: W/γ ≈ [[0,0.96,-0.96],[1.92,-1.92,0.24]] → round → clamp
    expected = torch.tensor([[0., 1., -1.], [1., -1., 0.]])
    assert torch.equal(w_tilde, expected)

def test_ternary_absmean_is_ste():
    w = torch.tensor([[0.4, -0.4, 0.05]], requires_grad=True)
    w_tilde, _ = ternary_absmean(w)
    w_tilde.sum().backward()
    assert w.grad is not None and w.grad.abs().sum() > 0   # gradient reached w
```

**Steps:**
- [ ] Step 1: Add both tests. Run, verify FAIL.
- [ ] Step 2: **Nick writes `ternary_absmean`.** Hints: `gamma = w.abs().mean()`;
      scale `w / (gamma + eps)`; ternarize with `ste_round(...).clamp(-1, 1)`;
      return `(w_tilde, gamma)` — keep γ separate. Decide during coding whether
      γ is detached (it depends on `w` via `mean|W|`); the Task-4 sanity test
      will catch a wrong choice.
- [ ] Step 3: Run, verify PASS. Commit.

---

### Task 3: INT8 absmax quantizer (the sanity path)

**Files:**
- Modify: `src/quant.py`
- Test: `tests/test_quant.py`

**Interfaces:**
- Consumes: `ste_round`.
- Produces: `int8_absmax(w: Tensor, eps: float = 1e-5) -> tuple[Tensor,
  Tensor]` — per-tensor absmax INT8 fake-quant, same `(codes, scale)` shape as
  `ternary_absmean` so `BitLinear` treats them interchangeably. `scale =
  max|W| / 127`; `codes = RoundClip(W/scale, -127, 127)` ste-valued.

**The test (target):**

```python
import torch
from src.quant import int8_absmax

def test_int8_absmax_roundtrips_near_identity():
    torch.manual_seed(0)
    w = torch.randn(64, 64)
    codes, scale = int8_absmax(w)
    assert codes.abs().max() <= 127
    approx = codes * scale
    assert (approx - w).abs().max() < scale        # error bounded by one step
```

**Steps:**
- [ ] Step 1: Add the test. Run, verify FAIL.
- [ ] Step 2: **Nick writes `int8_absmax`.** Hint: mirror `ternary_absmean` but
      `scale = w.abs().max()/127` and clamp to `[-127, 127]`.
- [ ] Step 3: Run, verify PASS. Commit.

---

### Task 4: `BitLinear` layer

**Files:**
- Modify: `src/quant.py`
- Test: `tests/test_quant.py`

**Interfaces:**
- Consumes: `ternary_absmean` (default `quant_fn`), any `(codes, scale)`
  quantizer.
- Produces: `class BitLinear(nn.Linear)` with `__init__(self, in_features,
  out_features, bias=True, quant_fn=ternary_absmean)` and a `forward` computing
  `y = scale * F.linear(x, codes) (+ bias)` — γ applied at the **output**
  (representation ii, the seam for 008's activation scale).

**The test (target):**

```python
import torch
import torch.nn.functional as F
from src.quant import BitLinear, ternary_absmean

def test_bitlinear_forward_equals_scale_times_ternary_matmul():
    torch.manual_seed(0)
    layer = BitLinear(8, 4, bias=False)
    x = torch.randn(3, 8)
    codes, scale = ternary_absmean(layer.weight)
    expected = scale * F.linear(x, codes)
    assert torch.allclose(layer(x), expected, atol=1e-6)

def test_bitlinear_gradient_flows_to_weight():
    layer = BitLinear(8, 4, bias=False)
    layer(torch.randn(3, 8)).sum().backward()
    assert layer.weight.grad is not None and layer.weight.grad.abs().sum() > 0

def test_bitlinear_int8_sanity_is_near_fp(  ):
    # STE harness correctness independent of ternary difficulty
    from src.quant import int8_absmax
    torch.manual_seed(0)
    layer = BitLinear(64, 64, bias=False, quant_fn=int8_absmax)
    x = torch.randn(16, 64)
    fp = F.linear(x, layer.weight)
    assert (layer(x) - fp).abs().max() < 0.5 * layer.weight.abs().max()
```

**Steps:**
- [ ] Step 1: Add the three tests. Run, verify FAIL.
- [ ] Step 2: **Nick writes `BitLinear`.** Hints: subclass `nn.Linear` so
      `self.weight`/`self.bias` come for free; in `forward` call
      `codes, scale = self.quant_fn(self.weight)`, then
      `y = scale * F.linear(x, codes)`, add `self.bias` after if present.
- [ ] Step 3: Run, verify PASS. Commit.

---

### Task 5: Integrate — config flag + swap body Linears

**Files:**
- Modify: `src/transformer.py` (`ModelConfig`, `TransformerBlock`, `make_linear`)
- Modify: `src/attention.py` (`CausalSelfAttention` q/k/v/out_proj)
- Test: `tests/test_quant_integration.py`

**Interfaces:**
- Consumes: `BitLinear`.
- Produces: `ModelConfig.quantize_linears: bool = False`; a module-level
  `make_linear(config, in_f, out_f, bias=True) -> nn.Linear | BitLinear` used
  by both `TransformerBlock.ffn` and `CausalSelfAttention`. `head` and
  `token_embedding` never call it.

**The test (target):**

```python
import torch
from src.transformer import ModelConfig, TinyTransformer
from src.quant import BitLinear

def _cfg(quantize):
    return ModelConfig(vocab_size=32, context_length=16, d_model=16,
                       n_layers=2, n_heads=2, d_ff=32, quantize_linears=quantize)

def test_flag_off_uses_plain_linear_and_is_unchanged():
    torch.manual_seed(0); fp = TinyTransformer(_cfg(False))
    assert not any(isinstance(m, BitLinear) for m in fp.modules())
    # FP path byte-identical: same seed → identical initial params
    torch.manual_seed(0); fp2 = TinyTransformer(_cfg(False))
    for a, b in zip(fp.parameters(), fp2.parameters()):
        assert torch.equal(a, b)

def test_flag_on_quantizes_body_but_holds_out_head_and_embedding():
    m = TinyTransformer(_cfg(True))
    body = [mod for name, mod in m.named_modules()
            if any(k in name for k in ("q_proj","k_proj","v_proj","out_proj","ffn"))
            and hasattr(mod, "weight") and mod.weight.dim() == 2]
    assert body and all(isinstance(b, BitLinear) for b in body)
    assert not isinstance(m.head, BitLinear)          # head held out
    assert type(m.token_embedding).__name__ == "Embedding"
```

**Steps:**
- [ ] Step 1: Add the tests. Run, verify FAIL.
- [ ] Step 2: **Nick writes** `quantize_linears` on `ModelConfig`, the
      `make_linear` helper, and swaps the body `nn.Linear(...)` constructions in
      `transformer.py`/`attention.py` to `make_linear(config, ...)`. Thread
      `config` into `CausalSelfAttention.__init__` (it currently takes only
      `d_model, n_heads`). Leave `head` as plain `nn.Linear`.
- [ ] Step 3: Run, verify PASS. Run the full suite to confirm no regression.
      Commit.

---

### Task 6: Train harness — tokenizer load + quantize flag

**Files:**
- Modify: `src/train.py` (`TrainConfig`, `_parse_args`, `train_model`)
- Test: `tests/test_train_config.py`

**Interfaces:**
- Produces: `TrainConfig.quantize_linears: bool = False` and
  `TrainConfig.load_tokenizer_path: str | None = None`; CLI flags
  `--quantize-linears` (store_true) and `--load-tokenizer-path`. When
  `load_tokenizer_path` is set, `train_model` loads it via
  `BPETokenizer.load(...)` instead of `tokenizer.train(corpus_text)`, and skips
  the build-timing block.

**The test (target):**

```python
from src.train import TrainConfig

def test_trainconfig_has_new_fields_defaulting_off():
    c = TrainConfig(data_path="d", checkpoint_path="c", tokenizer_path="t")
    assert c.quantize_linears is False
    assert c.load_tokenizer_path is None
```

Plus a manual check (guided, not automated): loading `checkpoints/002-rope`'s
tokenizer and encoding→decoding a line round-trips.

**Steps:**
- [ ] Step 1: Add the test. Run, verify FAIL.
- [ ] Step 2: **Nick writes** the two `TrainConfig` fields, the argparse flags,
      the load-vs-build branch in `train_model`, and passes `quantize_linears`
      into `ModelConfig`. Claude confirms the `BPETokenizer.load` signature
      first.
- [ ] Step 3: Run, verify PASS. Commit.

---

### Task 7: Scaffold experiment 007 (Claude writes boilerplate)

**Files:**
- Create: `experiments/007-qat-ternary/mission.md`
- Create: `experiments/007-qat-ternary/run_fleet.sh` (copied from the most
  recent structural experiment → inherits `fleet/install_deps.sh`, the
  `-m src.train` invocation, the S3 upload)
- Create: `experiments/007-qat-ternary/results.md` (skeleton)
- `source_archive/` is captured at run time, not now.

**Steps:**
- [ ] Step 1: Claude copies `run_fleet.sh` from `002-rope` (last structural
      experiment) and edits it to reuse 002's tokenizer + set
      `--quantize-linears`, matching 002's steps/lr/seed.
- [ ] Step 2: Claude writes `mission.md` (hypothesis, baselines 66.6 / 627,
      success criteria from the design doc) and a `results.md` skeleton.
- [ ] Step 3: Nick reviews the scaffold. Commit.
- [ ] Step 4: (Later, separate session) launch the fleet run, fill `results.md`.

---

## Self-Review

- **Spec coverage:** STE (T1), quantizer eqs 1–3 (T2), pluggable/sanity path
  (T3, T4), BitLinear rep (ii) (T4), hold-out + flag + FP-path-identical (T5),
  tokenizer reuse + quantize flag (T6), experiment A/B scaffold (T7). All
  design sections mapped.
- **Placeholders:** none — every learning task carries a full test as its
  target; implementation bodies are intentionally Nick's (guide-mode, stated in
  header), not vague "implement later" placeholders.
- **Type consistency:** `(codes/w_tilde, scale/gamma)` tuple shape is uniform
  across `ternary_absmean`/`int8_absmax`/`BitLinear`; `make_linear`/
  `quantize_linears` names consistent across T5/T6.
