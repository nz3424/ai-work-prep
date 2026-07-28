"""
LoRA instruction fine-tune of Bonsai (ternary base) on a tiny instruct slice.

Stages: load -> wrap(LoRA) -> data(format+mask) -> train -> save+compare.
The base ternary weights are FROZEN; only the LoRA A/B adapters train.

Run:  ../../.venv-hf/bin/python lora_finetune.py

Three TODOs are yours to fill (marked TODO-YOU). I wired the rest.
"""
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "hf-cache"))

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    Trainer, TrainingArguments, DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model

MODEL_ID = "deepgrove/Bonsai"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
OUT_DIR = str(Path(__file__).parent / "lora-adapter")
MAX_LEN = 512
N_EXAMPLES = 512     # tiny slice for a first run on MPS


# --------------------------------------------------------------------------
# Stage 1: load base + tokenizer
# --------------------------------------------------------------------------
def load_base():
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token          # Mistral tokenizer has no pad by default
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, trust_remote_code=True, torch_dtype=torch.float16,
    ).to(DEVICE)
    return model, tok


# --------------------------------------------------------------------------
# Stage 2: wrap with LoRA
# --------------------------------------------------------------------------
def add_lora(model):
    # TODO-YOU (decision 1): the LoRA config.
    #   target_modules — the 7 QLinear leaf names we confirmed
    #     (q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj), or a subset.
    #   r, lora_alpha — capacity vs. regularization. Common start: r=8, alpha=16.
    #   lora_dropout — e.g. 0.05.  task_type="CAUSAL_LM".
    lora_cfg = LoraConfig(
        r = 8,
        lora_alpha = 16,
        target_modules = ["q_proj", "v_proj"], # add more later
        lora_dropout = 0.05,
        task_type = "CAUSAL_LM"
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()   # sanity: should be a tiny % of 513.8M
    return model


# --------------------------------------------------------------------------
# Stage 3: data — format + tokenize with LABEL MASKING
# --------------------------------------------------------------------------
def build_dataset(tok):
    ds = load_dataset("tatsu-lab/alpaca", split=f"train[:{N_EXAMPLES}]")

    def format_example(ex):
        if ex["input"]:
            prompt = f"### Instruction:\n{ex['instruction']}\n### Input:\n{ex['input']}\n### Response:\n"
        else:
            prompt = f"### Instruction:\n{ex['instruction']}\n### Response:\n"
        answer = ex["output"] + tok.eos_token
        return {"prompt": prompt, "answer": answer}
        

    def tokenize(ex):
        # TODO-YOU (decision 3): the teaching bit — SFT label masking.
        # Tokenize prompt and answer, concatenate into input_ids. Build `labels`
        # equal to input_ids but with the PROMPT positions set to -100 so loss is
        # computed only on the answer tokens. Truncate to MAX_LEN.
        prompt_ids = tok(ex["prompt"], add_special_tokens=False)["input_ids"]
        answer_ids = tok(ex["answer"], add_special_tokens=False)["input_ids"]
        input_ids = prompt_ids + answer_ids
        labels = [-100] * len(prompt_ids) + answer_ids
        # Truncate to MAX_LEN
        input_ids = input_ids[:MAX_LEN]
        labels = labels[:MAX_LEN]
        return {"input_ids": input_ids, "labels": labels}


    ds = ds.map(format_example)
    ds = ds.map(tokenize, remove_columns=ds.column_names)
    return ds


# --------------------------------------------------------------------------
# Stage 4 + 5: train, save, compare
# --------------------------------------------------------------------------
def main():
    print(f"device={DEVICE}")
    model, tok = load_base()

    before = quick_gen(model, tok, "### Instruction:\nName three primary colors.\n### Response:\n")

    model = add_lora(model)
    ds = build_dataset(tok)

    args = TrainingArguments(
        output_dir=OUT_DIR,
        # TODO (fine, sensible defaults — tweak later):
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        num_train_epochs=1,
        learning_rate=2e-4,
        logging_steps=10,
        save_strategy="no",
        report_to="none",
    )
    # pads input_ids/attention_mask AND your masked labels (-100), preserving them
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    trainer = Trainer(model=model, args=args, train_dataset=ds, data_collator=collator)
    trainer.train()

    model.save_pretrained(OUT_DIR)       # saves ONLY the adapter (few MB)
    print(f"\nadapter saved to {OUT_DIR}")

    after = quick_gen(model, tok, "### Instruction:\nName three primary colors.\n### Response:\n")
    print("\n=== BEFORE ===\n", before, "\n=== AFTER ===\n", after)


@torch.no_grad()
def quick_gen(model, tok, prompt):
    ids = tok(prompt, return_tensors="pt").to(DEVICE)
    out = model.generate(**ids, max_new_tokens=40, do_sample=False)
    return tok.decode(out[0], skip_special_tokens=True)


if __name__ == "__main__":
    main()
