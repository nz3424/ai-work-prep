import json

def _get_pair_counts(ids: list[int]) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for pair in zip(ids, ids[1:]):
        counts[pair] = counts.get(pair, 0) + 1
    return counts


def _merge_pair(ids: list[int], pair: tuple[int, int], new_id: int) -> list[int]:
    merged = []
    i = 0
    while i < len(ids):
        if i < len(ids) - 1 and ids[i] == pair[0] and ids[i + 1] == pair[1]:
            merged.append(new_id)
            i += 2
        else:
            merged.append(ids[i])
            i += 1
    return merged

class BPETokenizer:
    def __init__(self, num_merges: int = 500):
        self.num_merges = num_merges
        self.merges = {}
        self.vocab: dict[int, bytes] = {}

    @property
    def vocab_size(self) -> int:
        return len(self.vocab) + 256


    def train(self, text: str) -> None:
        ids = list(text.encode("utf-8"))
        for _ in range(self.num_merges):
            frequencies = _get_pair_counts(ids)
            if not frequencies:
                break
            most_frequent_pair = max(frequencies, key=frequencies.get)
            if frequencies[most_frequent_pair] < 2:
                break

            new_id = 256 + len(self.merges)
            first, second = most_frequent_pair
            first_bytes = self.vocab[first] if first >= 256 else bytes([first])
            second_bytes = self.vocab[second] if second >= 256 else bytes([second])

            self.merges[most_frequent_pair] = new_id
            self.vocab[new_id] = first_bytes + second_bytes
            ids = _merge_pair(ids, most_frequent_pair, new_id)

    def encode(self, text: str) -> list[int]:
        ids = list(text.encode("utf-8"))
        while len(ids) > 1:
            frequencies = _get_pair_counts(ids)
            earliest_learned_pair = min(frequencies, key = lambda pair:(self.merges[pair] if pair in self.merges else float('inf')))
            if earliest_learned_pair not in self.merges:
                break
            ids = _merge_pair(ids, earliest_learned_pair, self.merges[earliest_learned_pair])
        
        return ids
    
    def decode(self, ids: list[int]) -> str:
        output = []
        for id in ids:
            if id < 256:
                output.append(bytes([id]))
            else:
                if id not in self.vocab:
                    raise ValueError(f"token id {id} not in vocab (vocab_size={self.vocab_size})")
                output.append(self.vocab[id])
        return b"".join(output).decode("utf-8", errors="replace")

    def save(self, path: str) -> None: 
        data = {
            "num_merges": self.num_merges,
            "merges": [[list(pair), new_id] for pair, new_id in self.merges.items()]
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> "BPETokenizer":
        with open(path, "r") as f:
            data = json.load(f)
        tokenizer = cls(num_merges=data["num_merges"])
        tokenizer.merges = {tuple(pair): new_id for pair, new_id in data["merges"]}
        for pair, new_id in data["merges"]:
            first, second = pair
            first_bytes = tokenizer.vocab[first] if first >= 256 else bytes([first])
            second_bytes = tokenizer.vocab[second] if second >= 256 else bytes([second])
            tokenizer.vocab[new_id] = first_bytes + second_bytes
        return tokenizer