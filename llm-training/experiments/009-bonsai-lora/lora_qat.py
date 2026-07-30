"""
CAPSTONE: can a LoRA adapter recover Bonsai from activation-quant damage?

The story tying the whole experiment together:
  - Weight-QAT stalled (qat_finetune.py) because ternary weights are a discrete
    staircase — you can't nudge them smoothly.
  - LoRA sidesteps that: it adds a CONTINUOUS, full-precision low-rank
    correction ALONGSIDE the frozen ternary base. No bin-crossing problem.

So here we deliberately break Bonsai with A5 activation quant (fluent-but-wrong
facts), then LoRA-finetune WITH the quant on, and see if the adapter learns to
correct the quantized base.

Key ordering: swap in the quantized layers and enable A5 BEFORE training, so the
training loss is computed against the broken base and the adapter has something
to fix. Base ternary weights stay frozen; only the LoRA A/B adapters move.

Run:  ../../.venv-hf/bin/python lora_qat.py
      ../../.venv-hf/bin/python lora_qat.py --bits 5 --max-steps 60   # quick
"""
import argparse
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "hf-cache"))

import torch
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    Trainer, TrainingArguments, DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model

from quant_a8 import swap_to_a8, set_activation_quant
import lora_finetune                       # module ref so we can shrink MAX_LEN
from lora_finetune import build_dataset, MODEL_ID, DEVICE, OUT_DIR

# Factual prompts where A5 was shown to fail (fluent but wrong).
PROMPTS = [
    "### Instruction:\nWhat is the capital of Italy?\n### Response:\n",
    "### Instruction:\nWhat is the capital of France?\n### Response:\n",
    "### Instruction:\nName three primary colors.\n### Response:\n",
]

# Held-out factual text. Recovery should show up as LOWER perplexity here.
EVAL_TEXT = (
    "Paris is the capital of France. Rome is the capital of Italy. "
    "The three additive primary colors are red, green, and blue. "
    "Water is made of hydrogen and oxygen."
)


@torch.no_grad()
def perplexity(model, tok, text):
    """exp(mean cross-entropy) on `text`, in whatever quant state the model is
    currently in. Lower = less surprised = better. The quantitative recovery
    signal to sit next to the generations."""
    ids = tok(text, return_tensors="pt").to(DEVICE)
    return torch.exp(model(**ids, labels=ids["input_ids"]).loss).item()


@torch.no_grad()
def measure(model, tok, label):
    ppl = perplexity(model, tok, EVAL_TEXT)
    print(f"\n--- {label}   (perplexity on EVAL_TEXT: {ppl:.2f}) ---")
    for p in PROMPTS:
        ids = tok(p, return_tensors="pt").to(DEVICE)
        out = model.generate(**ids, max_new_tokens=32, do_sample=False)
        text = tok.decode(out[0], skip_special_tokens=True).replace(p, "").strip()
        q = p.split("Instruction:\n")[1].split("\n")[0]
        print(f"  Q: {q}\n  A: {text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, default=5, help="activation bit-width to break with")
    ap.add_argument("--lora-r", type=int, default=8)
    ap.add_argument("--max-steps", type=int, default=-1, help="-1 = full epoch")
    # MPS tractability knobs. Per-step cost ~ (batch * grad-accum * max-len).
    # Keep it small: fp32 on MPS OOMs / crawls otherwise.
    ap.add_argument("--batch", type=int, default=1, help="micro-batch (keep at 1 on MPS)")
    ap.add_argument("--grad-accum", type=int, default=4, help="effective batch = batch * this")
    ap.add_argument("--max-len", type=int, default=128, help="truncation length")
    ap.add_argument("--no-quant", action="store_true",
                    help="CONTROL: keep activations at A16 throughout (LoRA-only, "
                         "no quant). Isolates instruction-tuning from quant recovery.")
    args = ap.parse_args()

    q_on = not args.no_quant                 # is activation quant applied?
    tag = "A16 (no-quant control)" if args.no_quant else f"A{args.bits}"

    lora_finetune.MAX_LEN = args.max_len   # build_dataset reads this at call time

    print(f"device={DEVICE} | {tag} | lora r={args.lora_r} | "
          f"batch {args.batch}x{args.grad_accum} | max_len {args.max_len}")
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, trust_remote_code=True, torch_dtype=torch.float32,
    ).to(DEVICE)

    # Swap in our controllable layers (activations off = stock A16 for now).
    swap_to_a8(model, enable=False, bits=args.bits)

    set_activation_quant(model, False)
    measure(model, tok, "A16 reference (stock)")
    set_activation_quant(model, q_on)
    measure(model, tok, f"{tag} BEFORE LoRA" + (" (broken)" if q_on else ""))

    # Wrap with LoRA on all 7 projections, then re-assert quant ON so training
    # sees the broken base. set_activation_quant finds the QLinearA8 base layers
    # now nested inside the PEFT wrappers.
    lora_cfg = LoraConfig(
        r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)
    n_on = set_activation_quant(model, q_on)          # quant state during training
    print(f"\nactivation quant = {q_on} on {n_on} base layers after LoRA wrap")
    model.print_trainable_parameters()

    ds = build_dataset(tok)
    targs = TrainingArguments(
        output_dir=OUT_DIR + "-qat",
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=1,
        max_steps=args.max_steps,
        learning_rate=2e-4,
        logging_steps=10,
        save_strategy="no",
        report_to="none",
    )
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    Trainer(model=model, args=targs, train_dataset=ds, data_collator=collator).train()

    set_activation_quant(model, q_on)
    measure(model, tok, f"{tag} AFTER LoRA" + (" (recovered?)" if q_on else ""))


if __name__ == "__main__":
    main()
