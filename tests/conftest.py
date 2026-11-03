"""Test doubles. No test talks to the real Gemini API.

`FakeClient` has the same attribute path as `genai.Client`
(`client.models.generate_content`, and so on) and returns real
`google.genai.types` objects, so the code under test parses genuine SDK types.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from app import main
from app.config import Settings
from app.gemini import GeminiService


def make_response(
    text: str = "hello",
    finish_reason: str = "STOP",
    *,
    prompt_tokens: int = 7,
    output_tokens: int = 3,
    thinking_tokens: int = 0,
    block_reason: str | None = None,
) -> types.GenerateContentResponse:
    if block_reason:
        return types.GenerateContentResponse.model_validate(
            {"prompt_feedback": {"block_reason": block_reason}}
        )
    return types.GenerateContentResponse.model_validate(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "finish_reason": finish_reason,
                }
            ],
            "usage_metadata": {
                "prompt_token_count": prompt_tokens,
                "candidates_token_count": output_tokens,
                "thoughts_token_count": thinking_tokens,
                "total_token_count": prompt_tokens + output_tokens + thinking_tokens,
            },
        }
    )


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_response: types.GenerateContentResponse = make_response()
        self.stream_chunks: list[str] = ["Hel", "lo"]
        self.raise_error: Exception | None = None

    def generate_content(self, **kwargs: Any) -> types.GenerateContentResponse:
        self.calls.append(kwargs)
        if self.raise_error:
            raise self.raise_error
        return self.next_response

    def generate_content_stream(self, **kwargs: Any) -> Iterator[types.GenerateContentResponse]:
        self.calls.append(kwargs)
        for piece in self.stream_chunks:
            yield make_response(piece)

    def count_tokens(self, **kwargs: Any) -> types.CountTokensResponse:
        self.calls.append(kwargs)
        return types.CountTokensResponse(total_tokens=len(str(kwargs["contents"]).split()))


class FakeClient:
    def __init__(self) -> None:
        self.models = FakeModels()
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def settings() -> Settings:
    return Settings(model="gemini-test-model", api_key="test-key")


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def api(settings: Settings, fake_client: FakeClient) -> Iterator[TestClient]:
    service = GeminiService(fake_client, settings)
    main.app.dependency_overrides[main.get_settings] = lambda: settings
    main.app.dependency_overrides[main.get_service] = lambda: service
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()
