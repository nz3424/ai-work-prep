#!/usr/bin/env bash
set -euo pipefail
EXPERIMENT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EXPERIMENT_DIR"

REPO_ROOT="$(git rev-parse --show-toplevel)"
# From `terraform output checkpoint_bucket_name` in llm-training/terraform/ —
# update this if the fleet's S3 bucket is ever destroyed and recreated.
CHECKPOINT_BUCKET="llm-training-fleet-checkpoints-10e3d44d"

EXPERIMENT_ID="008-activation-quant"
BASELINE_ID="002-rope"

# Hyperparameters are intentionally IDENTICAL to 007 so that the ONLY variable
# under test is 8-bit activation quantization inside BitLinear (adds A8 on top
# of 007's ternary weights = BitNet W1.58A8). Do not tune these. num_merges is
# omitted on purpose: we LOAD 002's tokenizer rather than rebuild.
STEPS=3000
BATCH_SIZE=32
CONTEXT_LENGTH=256
LR=3e-4
SEED=0

echo "Installing Python dependencies..."
# Shared installer: CPU-only torch to avoid the GPU-wheel disk overflow. See
# fleet/install_deps.sh for the full rationale.
"$REPO_ROOT/llm-training/fleet/install_deps.sh"

echo "Fetching 002's tokenizer (keeps 008 on the exact 004-007 measurement axis)..."
# Reusing 002's tokenizer.json verbatim is what makes 008's perplexity directly
# comparable to the 66.6 (FP) / 627 (PTQ) / 52.7 (007 QAT) numbers on the 002
# checkpoint axis.
mkdir -p "$REPO_ROOT/llm-training/checkpoints/$BASELINE_ID"
aws s3 cp "s3://$CHECKPOINT_BUCKET/$BASELINE_ID/tokenizer.json" \
  "$REPO_ROOT/llm-training/checkpoints/$BASELINE_ID/tokenizer.json"

echo "Archiving source snapshot..."
rm -rf source_archive
cp -r "$REPO_ROOT/llm-training/src" source_archive

cat > training_config.txt <<CONFIG
experiment=$EXPERIMENT_ID
baseline=007-qat-ternary
quantization=ternary_absmean_qat_ste_weights + int8_pertoken_absmax_activations
quantized_layers=body_only_head_and_embedding_held_out
tokenizer=loaded_from_${BASELINE_ID}
steps=$STEPS
batch_size=$BATCH_SIZE
context_length=$CONTEXT_LENGTH
lr=$LR
seed=$SEED
CONFIG

echo "Starting training run..."
# Run as `-m src.train` from llm-training/, not `python3.11 .../src/train.py`.
(
  cd "$REPO_ROOT/llm-training"
  python3.11 -m src.train \
    --data-path data/tinyshakespeare.txt \
    --checkpoint-path "checkpoints/$EXPERIMENT_ID/model.pt" \
    --tokenizer-path "checkpoints/$EXPERIMENT_ID/tokenizer.json" \
    --load-tokenizer-path "checkpoints/$BASELINE_ID/tokenizer.json" \
    --quantize-linears \
    --quantize-activations \
    --steps "$STEPS" \
    --batch-size "$BATCH_SIZE" \
    --context-length "$CONTEXT_LENGTH" \
    --lr "$LR" \
    --seed "$SEED" \
    --log-path "$EXPERIMENT_DIR/training.log"
)

echo "Archiving checkpoint + log to S3..."
aws s3 cp "$REPO_ROOT/llm-training/checkpoints/$EXPERIMENT_ID/model.pt" \
  "s3://$CHECKPOINT_BUCKET/$EXPERIMENT_ID/model.pt"
aws s3 cp "$REPO_ROOT/llm-training/checkpoints/$EXPERIMENT_ID/tokenizer.json" \
  "s3://$CHECKPOINT_BUCKET/$EXPERIMENT_ID/tokenizer.json"
aws s3 cp training.log "s3://$CHECKPOINT_BUCKET/$EXPERIMENT_ID/training.log"

echo "Done. Next: evaluate the 008 checkpoint on 005's 20-fixed-batch harness"
echo "(same axis as 66.6 / 627 / 52.7), write results.md, then:"
echo "  git add source_archive training_config.txt training.log results.md"
echo "  git commit"
