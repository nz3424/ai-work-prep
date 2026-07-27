from src.train import TrainConfig


def test_trainconfig_has_new_fields_defaulting_off():
    c = TrainConfig(data_path="d", checkpoint_path="c", tokenizer_path="t")
    assert c.quantize_linears is False
    assert c.load_tokenizer_path is None
