from __future__ import annotations

import pytest
from google.genai import types

from app.config import Settings
from app.gemini import (
    GeminiBlocked,
    GeminiService,
    GeminiUnavailable,
    build_client,
    build_config,
    check_finished,
    usage_from,
)
from app.schemas import GenerateRequest
from tests.conftest import FakeClient, make_response


def test_build_config_sends_only_fields_that_were_set() -> None:
    config = build_config(GenerateRequest(prompt="hi"))
    assert config.temperature is None
    assert config.system_instruction is None
    assert config.thinking_config is None


def test_build_config_maps_thinking_level_to_sdk_enum() -> None:
    config = build_config(
        GenerateRequest(prompt="hi", thinking_level="low", temperature=0.4, max_output_tokens=256)
    )
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert config.temperature == 0.4
    assert config.max_output_tokens == 256


def test_usage_reads_thinking_and_cached_tokens() -> None:
    usage = usage_from(make_response(prompt_tokens=10, output_tokens=5, thinking_tokens=20))
    assert usage.prompt_tokens == 10
    assert usage.output_tokens == 5
    assert usage.thinking_tokens == 20
    assert usage.total_tokens == 35


@pytest.mark.parametrize("reason", ["STOP", "MAX_TOKENS"])
def test_check_finished_accepts_normal_endings(reason: str) -> None:
    assert check_finished(make_response(finish_reason=reason)) == reason


def test_check_finished_raises_on_blocked_prompt() -> None:
    with pytest.raises(GeminiBlocked, match="prompt blocked"):
        check_finished(make_response(block_reason="SAFETY"))


def test_check_finished_raises_on_safety_stop() -> None:
    with pytest.raises(GeminiBlocked, match="SAFETY"):
        check_finished(make_response(finish_reason="SAFETY"))


def test_generate_passes_model_and_prompt(settings: Settings, fake_client: FakeClient) -> None:
    service = GeminiService(fake_client, settings)
    text, finish, usage = service.generate(GenerateRequest(prompt="Explain TPUs"))
    call = fake_client.models.calls[-1]
    assert call["model"] == "gemini-test-model"
    assert call["contents"] == "Explain TPUs"
    assert (text, finish, usage.total_tokens) == ("hello", "STOP", 10)


def test_stream_yields_only_text_deltas(settings: Settings, fake_client: FakeClient) -> None:
    fake_client.models.stream_chunks = ["a", "", "b"]
    service = GeminiService(fake_client, settings)
    assert list(service.stream(GenerateRequest(prompt="x"))) == ["a", "b"]


def test_triage_requests_json_schema(settings: Settings, fake_client: FakeClient) -> None:
    fake_client.models.next_response = make_response(
        '{"category":"bug","priority":"p1","summary":"Export fails.","needs_human":false}'
    )
    result = GeminiService(fake_client, settings).triage("CSV export returns 500")
    config = fake_client.models.calls[-1]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["properties"]["priority"]["enum"] == ["p0", "p1", "p2", "p3"]
    assert result.category == "bug"


def test_build_client_refuses_without_credentials() -> None:
    with pytest.raises(GeminiUnavailable):
        build_client(Settings(api_key=None))


def test_build_client_with_key_creates_developer_api_client() -> None:
    client = build_client(Settings(api_key="fake-key"))
    try:
        assert client.vertexai is False
    finally:
        client.close()
