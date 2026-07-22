#!/usr/bin/env bash
set -euo pipefail
EXPERIMENT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EXPERIMENT_DIR"

REPO_ROOT="$(git rev-parse --show-toplevel)"
# From `terraform output checkpoint_bucket_name` in llm-training/terraform/ —
# update this if the fleet's S3 bucket is ever destroyed and recreated.
CHECKPOINT_BUCKET="llm-training-fleet-checkpoints-10e3d44d"

STEPS=3000
BATCH_SIZE=32
CONTEXT_LENGTH=256
LR=3e-4
NUM_MERGES=750
SEED=0

echo "Installing Python dependencies..."
# Shared installer: CPU-only torch to avoid the GPU-wheel disk overflow. See
# fleet/install_deps.sh for the full rationale.
"$REPO_ROOT/llm-training/fleet/install_deps.sh"

echo "Archiving source snapshot..."
rm -rf source_archive
cp -r "$REPO_ROOT/llm-training/src" source_archive

cat > training_config.txt <<CONFIG
steps=$STEPS
batch_size=$BATCH_SIZE
context_length=$CONTEXT_LENGTH
lr=$LR
num_merges=$NUM_MERGES
seed=$SEED
CONFIG

echo "Starting training run..."
# Run as `-m src.train` from llm-training/, not `python3.11 .../src/train.py`
# — invoking the file directly puts src/ itself on sys.path instead of
# llm-training/, so `from src.tokenizer import ...` fails to resolve. The
# subshell keeps this script's own cwd (EXPERIMENT_DIR) unaffected for the
# S3 upload step below.
(
  cd "$REPO_ROOT/llm-training"
  python3.11 -m src.train \
    --data-path data/tinyshakespeare.txt \
    --checkpoint-path checkpoints/001-first-training-run/model.pt \
    --tokenizer-path checkpoints/001-first-training-run/tokenizer.json \
    --steps "$STEPS" \
    --batch-size "$BATCH_SIZE" \
    --context-length "$CONTEXT_LENGTH" \
    --lr "$LR" \
    --num-merges "$NUM_MERGES" \
    --seed "$SEED" \
    --log-path "$EXPERIMENT_DIR/training.log"
)

echo "Archiving checkpoint + log to S3..."
aws s3 cp "$REPO_ROOT/llm-training/checkpoints/001-first-training-run/model.pt" \
  "s3://$CHECKPOINT_BUCKET/001-first-training-run/model.pt"
aws s3 cp "$REPO_ROOT/llm-training/checkpoints/001-first-training-run/tokenizer.json" \
  "s3://$CHECKPOINT_BUCKET/001-first-training-run/tokenizer.json"
aws s3 cp training.log "s3://$CHECKPOINT_BUCKET/001-first-training-run/training.log"

echo "Done. Next: sample with generate.py, write results.md, then:"
echo "  git add source_archive training_config.txt training.log results.md"
echo "  git commit"
