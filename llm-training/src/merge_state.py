
"""Incremental pair-count bookkeeping for BPE training.

Replaces ``train()``'s full-corpus rescan on every merge (flagged in
experiment 001's results.md as the slowest part of the whole run). The
sequence is held as a doubly-linked list over the original byte positions
(``symbol``/``nxt``/``prv``/``alive``), alongside a maintained
``pair_counts`` and ``pair_positions`` index. Applying a merge touches only
the sites adjacent to each occurrence instead of scanning the corpus, so the
per-merge cost drops from O(corpus length) to O(occurrences of that pair).

Behavioural caveat (intentional): the argmax over ``pair_counts`` breaks ties
differently from the old naive loop's ``max`` over a freshly-rebuilt dict, so
the exact set and order of learned merges can differ from a tokenizer trained
with the pre-incremental code. BPE encode/decode roundtripping is invariant to
which pair is chosen among ties, so correctness is unaffected -- but a
retrained ``tokenizer.json`` is not guaranteed byte-identical to older
checkpoints.
"""


class MergeState:
    def __init__(self, ids: list[int]):
        n = len(ids)
        self.symbol = list(ids)
        self.nxt = [i+1 for i in range(n)]
        self.prv = [i-1 for i in range(n)]
        self.alive = [True] * n

        if n > 0:
            self.nxt[-1] = -1
        self.pair_counts: dict[tuple[int, int], int] = {}
        self.pair_positions: dict[tuple[int, int], set[int]] = {}

        for i in range(n-1):
            pair = (self.symbol[i], self.symbol[i+1])
            self.pair_counts[pair] = self.pair_counts.get(pair, 0) + 1
            self.pair_positions.setdefault(pair, set()).add(i)
            
    def _add(self, pair, pos):
        self.pair_counts[pair] = self.pair_counts.get(pair, 0) + 1
        self.pair_positions.setdefault(pair, set()).add(pos)
        
    def _remove(self, pair, pos):
        self.pair_positions[pair].discard(pos)
        self.pair_counts[pair] -= 1
        if self.pair_counts[pair] == 0:
            del self.pair_counts[pair]
            del self.pair_positions[pair]

    def live_ids(self) -> list[int]:
        if not self.symbol:
            return []
        result = []
        i = 0
        while i != -1:
            result.append(self.symbol[i])
            i = self.nxt[i]
        return result
    
    def apply_merge(self, pair, new_id):
        A, B = pair
        positions = list(self.pair_positions.get(pair, ()))
        i = 0
        for i in positions:
            j = self.nxt[i]
            if not self.alive[i] or j == -1 or self.symbol[i] != A or self.symbol[j] != B:
                continue

            p = self.prv[i]
            q = self.nxt[j]
            if p != -1:
                self._remove((self.symbol[p], A), p)
            if q != -1:
                self._remove((B, self.symbol[q]), j)

            self.symbol[i] = new_id
            self.nxt[i] = q
            if q != -1:
                self.prv[q] = i
            self.alive[j] = False

            if p != -1:
                self._add((self.symbol[p], new_id), p)
            if q != -1:
                self._add((new_id, self.symbol[q]), i)
            self._remove(pair, i)
        self.pair_counts.pop(pair, None)
        self.pair_positions.pop(pair, None)
            
                
        