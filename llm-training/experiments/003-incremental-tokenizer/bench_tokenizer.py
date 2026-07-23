"""Before/after wall-clock for the incremental BPE tokenizer (PR #29 / exp 003).

Times tokenizer training on the real corpus at the SAME num_merges the fleet
run uses, for two implementations on the same machine:

  * naive   -- the pre-#29 loop: a full _get_pair_counts + _merge_pair rescan
               of the whole corpus on every merge. Vendored below so this
               script is self-contained and does not depend on git history.
  * current -- src.tokenizer.BPETokenizer, incremental MergeState bookkeeping.

002 predates the timing instrumentation, so there is no recorded naive
baseline; this script produces the apples-to-apples pair on one box. It does
NOT touch the model or write any checkpoint.

Run from the llm-training/ directory:
    python3.11 experiments/003-incremental-tokenizer/bench_tokenizer.py
"""

import sys
import time
from pathlib import Path

# experiments/003-incremental-tokenizer/bench_tokenizer.py -> llm-training/
LLM_TRAINING = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LLM_TRAINING))

from src.tokenizer import BPETokenizer, _get_pair_counts, _merge_pair  # noqa: E402

CORPUS_PATH = LLM_TRAINING / "data" / "tinyshakespeare.txt"
NUM_MERGES = 750  # keep in sync with run_fleet.sh


def naive_train(text: str, num_merges: int) -> dict:
    """The pre-#29 merge loop: full-corpus rescan per merge."""
    ids = list(text.encode("utf-8"))
    merges: dict = {}
    for _ in range(num_merges):
        frequencies = _get_pair_counts(ids)
        if not frequencies:
            break
        pair = max(frequencies, key=frequencies.get)
        if frequencies[pair] < 2:
            break
        new_id = 256 + len(merges)
        merges[pair] = new_id
        ids = _merge_pair(ids, pair, new_id)
    return merges


def main() -> None:
    text = CORPUS_PATH.read_text()

    start = time.perf_counter()
    naive_merges = naive_train(text, NUM_MERGES)
    naive_seconds = time.perf_counter() - start

    tokenizer = BPETokenizer(num_merges=NUM_MERGES)
    start = time.perf_counter()
    tokenizer.train(text)
    incremental_seconds = time.perf_counter() - start

    speedup = naive_seconds / incremental_seconds if incremental_seconds else float("inf")

    print(f"corpus:            {CORPUS_PATH.name} ({len(text):,} chars)")
    print(f"num_merges:        {NUM_MERGES}")
    print(f"naive_seconds:     {naive_seconds:.2f}")
    print(f"incremental_seconds: {incremental_seconds:.2f}")
    print(f"speedup:           {speedup:.1f}x")
    # Sanity: both should learn the same NUMBER of merges (the set/order may
    # differ by tie-break; that is the documented, intentional drift).
    print(f"naive_merge_count: {len(naive_merges)}")
    print(f"incremental_merge_count: {len(tokenizer.merges)}")
    print(f"merges_identical:  {naive_merges == tokenizer.merges}")


if __name__ == "__main__":
    main()
