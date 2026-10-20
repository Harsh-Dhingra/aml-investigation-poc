"""Constrained OpenAI Responses adapter shared by the graph nodes."""

import os
from typing import Literal

from pydantic import BaseModel


class OpenAIModel:
    def __init__(self, model_id, client=None):
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url="https://api.openai.com/v1", timeout=90, max_retries=1)
            if os.environ.get("LANGSMITH_TRACING", "false").lower() == "true":
                from langsmith.wrappers import wrap_openai

                client = wrap_openai(client)
        self.client, self.model_id = client, model_id

    def with_structured_output(self, schema):
        return StructuredOpenAI(self, schema)


class StructuredOpenAI:
    def __init__(self, model, schema):
        self.model, self.schema = model, schema

    def invoke(self, messages):
        inputs = []
        for role, content in messages:
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            if isinstance(content, list):
                blocks = []
                for block in content:
                    if block["type"] == "text":
                        blocks.append({"type": "input_text", "text": block["text"]})
                    elif block["type"] == "image":
                        source = block["source"]
                        blocks.append(
                            {
                                "type": "input_image",
                                "image_url": f"data:{source['media_type']};base64,{source['data']}",
                            }
                        )
                    else:
                        raise ValueError("Unsupported model input block")
                content = blocks
            inputs.append({"role": role, "content": content})
        options = {}
        if self.model.model_id.startswith(("gpt-5", "gpt-6")):
            options["reasoning"] = {"effort": "low"}
        result = self.model.client.responses.parse(
            model=self.model.model_id,
            input=inputs,
            text_format=self.schema,
            max_output_tokens=3500,
            store=False,
            **options,
        )
        if result.output_parsed is None:
            raise ValueError("The model refused or did not return a complete structured response")
        return result.output_parsed


class ConnectionCheck(BaseModel):
    status: Literal["ok"]


def verify_openai(key, requested_model=None):
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=90, max_retries=0)
    if requested_model:
        chosen = requested_model
    else:
        available = {model.id for model in client.models.list()}
        chosen = next(
            (name for name in ["gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini"] if name in available), None
        )
        if chosen is None:
            raise ValueError("Set AML_OPENAI_MODEL to a structured-output model enabled for this account")
    result = (
        OpenAIModel(chosen, client)
        .with_structured_output(ConnectionCheck)
        .invoke([("user", "Return status ok to confirm this structured-output connection.")])
    )
    if result.status != "ok":
        raise ValueError("Unexpected connection-check response")
    return chosen
