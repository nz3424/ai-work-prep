from src.generate import generate, load_checkpoint
from src.tokenizer import BPETokenizer
from src.train import TrainConfig, train_model
from src.transformer import ModelConfig, TinyTransformer


def _tiny_model_and_tokenizer():
    tokenizer = BPETokenizer(num_merges=10)
    tokenizer.train("hello world, this is a tiny training corpus for the tokenizer to learn merges from.")
    config = ModelConfig(
        vocab_size=tokenizer.vocab_size, context_length=32, d_model=16, n_layers=2, n_heads=2, d_ff=32
    )
    model = TinyTransformer(config)
    return model, tokenizer


def test_generate_extends_the_prompt():
    model, tokenizer = _tiny_model_and_tokenizer()
    output = generate(model, tokenizer, "hello", max_new_tokens=20, seed=0)

    assert isinstance(output, str)
    # decode() concatenates token bytes in order, so the prompt's own bytes
    # are always a prefix of the output regardless of what gets generated
    # after them.
    assert output.startswith("hello")
    assert len(output) > len("hello")


def test_generate_is_deterministic_with_top_k_1():
    model, tokenizer = _tiny_model_and_tokenizer()
    out1 = generate(model, tokenizer, "hello", max_new_tokens=15, top_k=1, seed=42)
    out2 = generate(model, tokenizer, "hello", max_new_tokens=15, top_k=1, seed=42)
    assert out1 == out2


def test_generate_beyond_context_length_does_not_crash():
    # _tiny_model_and_tokenizer() uses context_length=32. A short prompt plus
    # 50 new tokens forces the running sequence past that window, exercising
    # the sliding-window crop rather than just the case where everything
    # fits in one shot.
    model, tokenizer = _tiny_model_and_tokenizer()
    output = generate(model, tokenizer, "hello", max_new_tokens=50, seed=0)
    assert output.startswith("hello")


def test_load_checkpoint_and_generate_end_to_end(tmp_path):
    # Exercises the real contract between train.py and generate.py: trains a
    # tiny model for real, saves it through train_model's checkpoint format,
    # then loads it back through load_checkpoint and confirms generate() can
    # run against the reloaded model/tokenizer pair.
    data_path = tmp_path / "corpus.txt"
    data_path.write_text("the quick brown fox jumps over the lazy dog. " * 50)
    config = TrainConfig(
        data_path=str(data_path),
        checkpoint_path=str(tmp_path / "model.pt"),
        tokenizer_path=str(tmp_path / "tokenizer.json"),
        steps=5,
        batch_size=4,
        context_length=16,
        num_merges=10,
        d_model=16,
        n_layers=2,
        n_heads=2,
        d_ff=32,
    )
    train_model(config)

    model, tokenizer = load_checkpoint(config.checkpoint_path, config.tokenizer_path)
    output = generate(model, tokenizer, "the", max_new_tokens=10, seed=0)

    assert output.startswith("the")
