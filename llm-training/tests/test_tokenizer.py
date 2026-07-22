from src.tokenizer import BPETokenizer


def test_encode_decode_roundtrip_with_no_merges():
    tokenizer = BPETokenizer(num_merges=0)
    assert tokenizer.encode("hi") == [104, 105]
    assert tokenizer.decode([104, 105]) == "hi"


def test_train_learns_merges_for_repeated_pairs():
    tokenizer = BPETokenizer(num_merges=3)
    tokenizer.train("aaaaaaaaaa")  # only one repeated pair possible: ('a', 'a')

    assert len(tokenizer.merges) > 0
    assert tokenizer.vocab_size == 256 + len(tokenizer.merges)


def test_train_stops_early_when_no_pair_repeats():
    tokenizer = BPETokenizer(num_merges=100)
    tokenizer.train("abcdefg")  # every byte is unique, no pair ever repeats

    assert len(tokenizer.merges) == 0


def test_encode_applies_learned_merges():
    tokenizer = BPETokenizer(num_merges=1)
    tokenizer.train("aaaa")
    # after training, 'a'+'a' (97, 97) is merged into one new token
    assert tokenizer.encode("aa") == [256]
    assert tokenizer.encode("aaa") == [256, 97]


def test_roundtrip_on_real_corpus_slice():
    from pathlib import Path

    corpus = Path(__file__).parent.parent / "data" / "tinyshakespeare.txt"
    text = corpus.read_text()[:50_000]

    tokenizer = BPETokenizer(num_merges=200)
    tokenizer.train(text)

    assert tokenizer.decode(tokenizer.encode(text)) == text


def test_roundtrip_edge_cases():
    tokenizer = BPETokenizer(num_merges=50)
    tokenizer.train("the quick brown fox jumps over the lazy dog " * 20)

    for text in ["", "   \n\t  ", "no merges apply to this: xyzq", "café 🎭 unicode outside training data"]:
        assert tokenizer.decode(tokenizer.encode(text)) == text


def test_decode_replaces_invalid_utf8_instead_of_raising():
    tokenizer = BPETokenizer(num_merges=0)
    # 0x80 is a UTF-8 continuation byte and is never valid as the start of a
    # sequence on its own — this simulates what generate.py's autoregressive
    # sampling could produce, since nothing constrains a sampled id sequence
    # to be valid UTF-8 the way encode()'s output always is.
    result = tokenizer.decode([104, 128, 105])  # "h" + invalid byte + "i"
    assert result == "h�i"


def test_mergestate_init_matches_naive():
    from src.merge_state import MergeState
    from src.tokenizer import _get_pair_counts

    for text in ["", "a", "aaaa", "abab", "the the the"]:
        ids = list(text.encode())
        state = MergeState(ids)
        assert state.pair_counts == _get_pair_counts(ids)
        assert state.live_ids() == ids


def test_apply_merge_keeps_counts_consistent():
    from src.merge_state import MergeState
    from src.tokenizer import _get_pair_counts

    for text in ["aaaa", "aaaaa", "abababab", "the theatre theme"]:
        state = MergeState(list(text.encode()))
        next_id = 256
        for _ in range(5):
            if not state.pair_counts:
                break
            pair = max(state.pair_counts, key=state.pair_counts.get)
            state.apply_merge(pair, next_id)
            next_id += 1
            live = state.live_ids()
            assert state.pair_counts == _get_pair_counts(live), (text, live)
            assert all(len(state.pair_positions[p]) == c
                       for p, c in state.pair_counts.items())


def test_save_and_load_roundtrip(tmp_path):
    tokenizer = BPETokenizer(num_merges=30)
    tokenizer.train("the quick brown fox jumps over the lazy dog " * 20)

    path = tmp_path / "tokenizer.json"
    tokenizer.save(str(path))

    loaded = BPETokenizer.load(str(path))

    assert loaded.vocab_size == tokenizer.vocab_size
    text = "the lazy fox"
    assert loaded.encode(text) == tokenizer.encode(text)
    assert loaded.decode(tokenizer.encode(text)) == text
