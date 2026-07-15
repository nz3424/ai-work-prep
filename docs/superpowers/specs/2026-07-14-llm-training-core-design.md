# LLM Training Track — Core Design (Transformer From Scratch)

**Maps to:** Track 3 (`llm-training/`), core goal — see `../../../GOALS.md` and
`llm-training/README.md` for full track context and priority order.

## Scope

This spec covers only the **core** goal: building a small decoder-only
transformer from scratch (own BPE tokenizer, attention, transformer block,
training loop, generation) to get in-practice understanding of how an LLM is
actually trained, using tinyshakespeare as the training corpus.

The **stretch** goal — ternary weight quantization following BitNet b1.58 — is
explicitly out of scope for this spec. It reuses this same model/tokenizer/data
pipeline as a variant (swapping `nn.Linear` for a `BitLinear`-equivalent), so it
will be designed as a separate spec once the core model is working, and will
live as additional experiment folders in this same repo rather than a new
project.

**Sequencing note (EC2 fleet):** all actual training runs — including the
first one — are gated on a separate, upcoming sub-project: a simplified
EC2 + tmux training fleet (SSH into an EC2 box, run detached tmux sessions,
survive laptop sleep/disconnect), modeled on the workflow described in Dave
Blundin's "DB2 stack" writeup. That sub-project will get its own spec and
plan, built and verified *before* `experiments/001-first-training-run/`
executes. This spec's code (tokenizer/attention/model/training loop) is
execution-location-agnostic — `run_fleet.sh` is the seam where "run locally"
vs. "run via SSH+tmux on EC2" plugs in, so nothing here needs to change once
the fleet exists.

## Approach: staged bottom-up build

Each component is built and verified in isolation before the next is started,
rather than writing a full skeleton end-to-end first. This matches the
first-principles, minimal-guide learning goal — you can't move to attention
until the tokenizer is proven correct, forcing real understanding at each
layer rather than integration-level "it kind of works."

Build style: PyTorch tensors, `nn.Linear`/`nn.Parameter`, and PyTorch's
autograd/optimizers for gradient computation — but no high-level shortcuts
(no `nn.MultiheadAttention`, no `nn.TransformerEncoderLayer`, no training
framework/`Trainer` abstraction). This is the standard meaning of "transformer
from scratch" in ML education (nanoGPT, Karpathy's course): the learning
target is architecture, tokenization, and attention mechanics — not
reimplementing calculus/autodiff.

## Repo structure

```
llm-training/
  src/
    tokenizer.py       # BPE tokenizer: train(), encode(), decode()
    attention.py        # causal multi-head self-attention, built from raw tensor ops
    transformer.py        # embeddings + transformer block(s) + output head (the model)
    train.py               # training loop: batching, loss, optimizer step, checkpointing
    generate.py              # autoregressive sampling from a checkpoint
  tests/
    test_tokenizer.py
    test_attention.py
    test_transformer.py
  experiments/
    001-first-training-run/
      mission.md            # hypothesis + success criteria, written before running
      run_fleet.sh           # exact command(s) that launched the run
      training_config.txt     # every hyperparameter, flat, for reproducibility
      source_archive/          # snapshot of src/ as it existed for this run,
                                # populated by run_fleet.sh at launch time (not
                                # a git SHA reference, so uncommitted tweaks at
                                # launch time are still captured)
      training.log             # raw stdout / loss curve
      results.md                # filled in after: outcome vs. prediction,
                                 # sample generations, learnings
  data/
    tinyshakespeare.txt
  checkpoints/          # gitignored
  docs/
    bitnet-b1.58-2402.17764.pdf   (already present)
```

`tests/` (pytest) covers correctness/shape checks and runs fast, no ceremony.
`experiments/` is reserved for actual hypothesis-driven training runs, not
component-level correctness checks — component debugging lives in `tests/`.

## Component build order & definition of done

1. **Tokenizer** (`tokenizer.py`) — BPE from scratch: build a merge-rule
   vocabulary from `tinyshakespeare.txt`, `encode()`/`decode()`.
   **Done when:** `decode(encode(text)) == text` for the full corpus and
   held-out strings, and the vocab is inspectable/explainable (e.g. can name
   why the top merges happened first).

2. **Attention block** (`attention.py`) — Causal multi-head self-attention:
   `nn.Linear` for Q/K/V/output projections, manual scaled dot-product +
   causal mask + softmax.
   **Done when:** a unit test on a small hand-traceable input (e.g. 3 tokens,
   2 heads, tiny `d_model`) matches a manually-computed attention weight and
   the correct output shape; causal masking is verified (token *i* cannot
   attend to token *i+1*).

3. **Transformer block & full model** (`transformer.py`) — Token + positional
   embeddings; block = attention + feed-forward/activation + layer norm +
   residual connections, stacked N times; final linear head to vocab logits.
   **Done when:** a forward pass on a batch produces correctly-shaped logits
   `(batch, seq_len, vocab_size)`, and untrained-model loss is close to
   `-log(1/vocab_size)` (confirms the model isn't broken/biased pre-training).

4. **Training loop** (`train.py`) — Cross-entropy loss, AdamW, batching via
   random crops of the corpus, checkpointing, per-step loss logging.
   **Done when:** loss decreases monotonically (with noise) over a short
   local smoke-test run (a few hundred steps). This smoke test is cheap and
   local — it does not need an `experiments/` folder.

5. **Generation** (`generate.py`) — Autoregressive sampling (temperature,
   top-k) from a checkpoint.
   **Done when:** a prompt produces text end-to-end; quality doesn't matter
   yet, only that the pipeline runs.

Only after all five pass their local smoke-test bar does
`experiments/001-first-training-run/` happen — a real, longer training run
(on the EC2 fleet, per the sequencing note above) with a `mission.md`
prediction (target loss, expected qualitative coherence) and a `results.md`
write-up afterward.

## Model architecture & hyperparameters

Decoder-only, GPT-style (causal self-attention only — matches BitNet b1.58's
own architecture, so the future stretch goal needs a layer swap, not an
architecture change):

| Parameter | Value | Why |
|---|---|---|
| Vocab size | ~500–1000 BPE merges | tinyshakespeare's character set is small; a few hundred merges shows real subword structure without a vocab that overwhelms the dataset |
| Context length | 256 tokens | Captures Shakespeare's sentence/line structure while keeping attention cheap |
| `d_model` | 128 | Keeps the model at ~1–5M params — trains fast, small enough to reason about by hand while debugging |
| Layers | 4 | Enough depth for real hierarchical structure without burying bugs |
| Heads | 4 | 32 dims/head — a clean, inspectable size for tracing attention weights |
| Feed-forward dim | 512 (4x `d_model`) | Standard ratio from the original Transformer paper |

Deliberately small: the goal is understanding, not benchmark performance, and
a model this size trains fast enough that debugging iteration doesn't cost
real time, locally or on the fleet.

## Data pipeline

`tinyshakespeare.txt` downloaded once into `data/`, split ~90/10 train/val by
character offset (not by line, to avoid overlap-adjacent leakage at the
boundary). `train.py` samples random `context_length`-token windows from the
train split each step; validation loss is checked periodically on held-out
windows from the val split and logged into the experiment's `training.log`.

## Testing

- `tests/test_tokenizer.py`: round-trip correctness on full corpus + edge
  cases (empty string, unseen characters, whitespace-heavy strings).
- `tests/test_attention.py`: shape correctness, causal masking, and a
  hand-traceable small-input numeric check.
- `tests/test_transformer.py`: end-to-end forward-pass shape check and the
  untrained-loss sanity check described in milestone 3.
- No test coverage is expected for `experiments/` outputs — those are
  evaluated via `results.md`, not pytest.
