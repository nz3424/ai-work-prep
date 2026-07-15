from types import SimpleNamespace

from llm_client import LLMClient, compute_cost


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class FakeAnthropic:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def make_fake_response(text="hello", input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_call_returns_parsed_response():
    fake_client = FakeAnthropic(make_fake_response(text="def reverse(s): return s[::-1]"))
    client = LLMClient(client=fake_client)
    result = client.call(model="claude-sonnet-5", prompt="reverse a string", temperature=0.2)
    assert result.text == "def reverse(s): return s[::-1]"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.cost_usd > 0
    assert result.latency_ms >= 0


def test_compute_cost_known_model():
    cost = compute_cost("claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 3.0 + 15.0


def test_compute_cost_haiku_is_cheaper_than_opus():
    haiku_cost = compute_cost("claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=1000)
    opus_cost = compute_cost("claude-opus-4-8", input_tokens=1000, output_tokens=1000)
    assert haiku_cost < opus_cost


def test_call_includes_output_config_effort_when_provided():
    fake_client = FakeAnthropic(make_fake_response())
    client = LLMClient(client=fake_client)
    client.call(model="claude-sonnet-5", prompt="write code", temperature=0.2, effort="xhigh")
    assert fake_client.messages.last_kwargs["output_config"] == {"effort": "xhigh"}


def test_call_omits_output_config_when_effort_not_provided():
    fake_client = FakeAnthropic(make_fake_response())
    client = LLMClient(client=fake_client)
    client.call(model="claude-haiku-4-5-20251001", prompt="write code", temperature=0.2)
    assert "output_config" not in fake_client.messages.last_kwargs
