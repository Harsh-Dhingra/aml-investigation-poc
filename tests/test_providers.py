from types import SimpleNamespace

import pytest

from aml_poc.providers import ConnectionCheck, OpenAIModel


def test_openai_responses_preserves_roles_schema_and_no_storage():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=ConnectionCheck(status="ok"))

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    model = OpenAIModel("test-model", client)
    result = model.with_structured_output(ConnectionCheck).invoke(
        [("system", "Use cited evidence only"), ("human", "Test")]
    )
    assert result.status == "ok"
    assert captured["input"][1]["role"] == "user"
    assert captured["store"] is False
    assert captured["text_format"] is ConnectionCheck


def test_openai_refusal_cannot_be_used_as_an_assessment():
    client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(output_parsed=None))
    )
    with pytest.raises(ValueError, match="refused"):
        OpenAIModel("test-model", client).with_structured_output(ConnectionCheck).invoke([("human", "Test")])


def test_openai_image_adapter_retains_media_type():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=ConnectionCheck(status="ok"))

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    OpenAIModel("test-model", client).with_structured_output(ConnectionCheck).invoke(
        [("human", [{"type": "image", "source": {"media_type": "image/png", "data": "sample"}}])]
    )
    assert captured["input"][0]["content"][0]["image_url"] == "data:image/png;base64,sample"
