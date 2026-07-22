#!/usr/bin/env bash
# Shared Python-dependency install for every fleet training experiment.
#
# Call this from an experiment's run_fleet.sh instead of invoking pip directly,
# so the CPU-only-torch fix lives in ONE place and can't drift per-experiment
# (which is exactly how the disk-overflow bug recurred between experiments 001
# and 002).
#
# Why not a plain `pip install -r requirements.txt`: the fleet box is GPU-less,
# but default-PyPI `torch` pulls the CUDA build plus multi-hundred-MB
# nvidia-*-cu* / triton / cublas wheels that overflow the small root disk and
# the RAM-backed /tmp (tmpfs) -> `[Errno 28] No space left on device`. The
# CPU-only wheel (~200 MB) is both far smaller and the correct build for a box
# with no GPU. First diagnosed in experiment 001's results.md.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Keep pip's temp/build dir off the small RAM-backed /tmp (tmpfs); large wheel
# unpacks then land on the root volume, which has more headroom.
export TMPDIR="${TMPDIR:-$HOME/tmp}"
mkdir -p "$TMPDIR"

# CPU-only torch first, from the dedicated index...
python3.11 -m pip install --user --index-url https://download.pytorch.org/whl/cpu torch
# ...then the rest; torch is already satisfied, so this won't re-pull it.
python3.11 -m pip install --user -r "$REPO_ROOT/llm-training/requirements.txt"
