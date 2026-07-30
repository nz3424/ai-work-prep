#!/usr/bin/env bash
set -euo pipefail
EXPERIMENT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EXPERIMENT_DIR"

REPO_ROOT="$(git rev-parse --show-toplevel)"
# From `terraform output checkpoint_bucket_name` in llm-training/terraform/ —
# update this if the fleet's S3 bucket is ever destroyed and recreated.
CHECKPOINT_BUCKET="llm-training-fleet-checkpoints-10e3d44d"

EXPERIMENT_ID="010-moe"
BASELINE_ID="002-rope"

# Hyperparameters are intentionally IDENTICAL to 002-rope so that the ONLY
# variable under test is the block FFN: dense nn.Sequential -> MoEFeedForward
# (4 experts, top-2, compute-matched, FP32). Do not tune these. num_merges is
# omitted on purpose: we LOAD 002's tokenizer rather than rebuild.
#
# MoE knobs (the change under test):
#   --use-moe --n-experts 4 --top-k 2 --moe-aux-loss-coef 0.01
# --grad-checkpoint is numerically transparent (recompute in backward, no
# dropout) and only cuts peak memory — safe headroom for the ~4x FFN params of
# the compute-all-then-mask MoE on the GPU-less fleet box; it does NOT affect
# the result vs 002.
STEPS=3000
BATCH_SIZE=32
CONTEXT_LENGTH=256
LR=3e-4
SEED=0
N_EXPERTS=4
TOP_K=2
MOE_AUX_LOSS_COEF=0.01

echo "Installing Python dependencies..."
# Shared installer: CPU-only torch to avoid the GPU-wheel disk overflow. See
# fleet/install_deps.sh for the full rationale.
"$REPO_ROOT/llm-training/fleet/install_deps.sh"

echo "Fetching 002's tokenizer (keeps 010 on the exact 002 measurement axis)..."
# Reusing 002's tokenizer.json verbatim is what makes 010's perplexity directly
# comparable to the 66.6 (FP) number on the 002 checkpoint axis.
mkdir -p "$REPO_ROOT/llm-training/checkpoints/$BASELINE_ID"
aws s3 cp "s3://$CHECKPOINT_BUCKET/$BASELINE_ID/tokenizer.json" \
  "$REPO_ROOT/llm-training/checkpoints/$BASELINE_ID/tokenizer.json"

echo "Archiving source snapshot..."
rm -rf source_archive
cp -r "$REPO_ROOT/llm-training/src" source_archive

cat > training_config.txt <<CONFIG
experiment=$EXPERIMENT_ID
baseline=$BASELINE_ID
change_under_test=dense_ffn_to_moe_ffn
moe=top${TOP_K}_of_${N_EXPERTS}_experts_compute_matched
router=fp32_nn_linear
experts=fp32_make_linear_quantize_linears_false
load_balance=switch_gshard_aux_loss
moe_aux_loss_coef=$MOE_AUX_LOSS_COEF
memory=grad_checkpoint_blocks
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
    --use-moe \
    --n-experts "$N_EXPERTS" \
    --top-k "$TOP_K" \
    --moe-aux-loss-coef "$MOE_AUX_LOSS_COEF" \
    --grad-checkpoint \
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

echo "Done. Next: evaluate the 010 checkpoint on 005's 20-fixed-batch harness"
echo "  (cd $REPO_ROOT/llm-training && PYTHONPATH=. python3.11 experiments/010-moe/eval_005harness.py)"
echo "then write results.md and commit:"
echo "  git add experiments/010-moe/{source_archive,training_config.txt,training.log,results.md}"
echo "  git commit"
echo
echo "Optional collapse demo (aux off) — expect expert_frac to split toward [~1,~1,~0,~0]:"
echo "  python3.11 -m src.train --data-path data/tinyshakespeare.txt \\"
echo "    --checkpoint-path checkpoints/010-moe-collapse/model.pt \\"
echo "    --tokenizer-path checkpoints/010-moe-collapse/tokenizer.json \\"
echo "    --load-tokenizer-path checkpoints/002-rope/tokenizer.json \\"
echo "    --use-moe --moe-aux-loss-coef 0 --grad-checkpoint \\"
echo "    --steps 500 --batch-size 32 --context-length 256 --lr 3e-4 --seed 0"
