from __future__ import annotations

from fastapi.testclient import TestClient
from google.genai import errors

from app import main
from app.config import Settings
from tests.conftest import FakeClient, make_response


def test_health_does_not_call_gemini(api: TestClient, fake_client: FakeClient) -> None:
    res = api.get("/health")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ok",
        "model": "gemini-test-model",
        "backend": "developer-api",
        "configured": True,
    }
    assert fake_client.models.calls == []


def test_health_works_with_no_credentials() -> None:
    main.app.dependency_overrides[main.get_settings] = lambda: Settings(api_key=None)
    try:
        with TestClient(main.app) as client:
            assert client.get("/health").json()["configured"] is False
            # Generation needs credentials, so it is refused cleanly.
            assert client.post("/v1/generate", json={"prompt": "hi"}).status_code == 503
    finally:
        main.app.dependency_overrides.clear()


def test_generate_returns_text_and_usage(api: TestClient) -> None:
    res = api.post("/v1/generate", json={"prompt": "Say hello"})
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "hello"
    assert body["finish_reason"] == "STOP"
    assert body["usage"]["total_tokens"] == 10


def test_generate_validates_input(api: TestClient) -> None:
    assert api.post("/v1/generate", json={"prompt": ""}).status_code == 422
    assert api.post("/v1/generate", json={"prompt": "x", "temperature": 3}).status_code == 422


def test_generate_rejects_oversized_prompt(api: TestClient) -> None:
    res = api.post("/v1/generate", json={"prompt": "x" * 20_001})
    assert res.status_code == 413


def test_blocked_answer_maps_to_422(api: TestClient, fake_client: FakeClient) -> None:
    fake_client.models.next_response = make_response(finish_reason="SAFETY")
    res = api.post("/v1/generate", json={"prompt": "something"})
    assert res.status_code == 422
    assert "SAFETY" in res.json()["detail"]


def test_quota_error_maps_to_429(api: TestClient, fake_client: FakeClient) -> None:
    fake_client.models.raise_error = errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )
    assert api.post("/v1/generate", json={"prompt": "hi"}).status_code == 429


def test_stream_emits_sse_events(api: TestClient, fake_client: FakeClient) -> None:
    fake_client.models.stream_chunks = ["line one\nline two", "!"]
    res = api.post("/v1/generate/stream", json={"prompt": "hi"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    assert "data: line one\ndata: line two\n\n" in res.text
    assert res.text.endswith("event: done\ndata: [DONE]\n\n")


def test_count_tokens(api: TestClient) -> None:
    res = api.post("/v1/tokens", json={"text": "one two three"})
    assert res.json() == {"model": "gemini-test-model", "total_tokens": 3}


def test_triage_returns_structured_object(api: TestClient, fake_client: FakeClient) -> None:
    fake_client.models.next_response = make_response(
        '{"category":"billing","priority":"p2","summary":"Charged twice.","needs_human":true}'
    )
    res = api.post("/v1/triage", json={"ticket": "I was charged twice, refund please"})
    assert res.status_code == 200
    assert res.json()["needs_human"] is True


def test_triage_rejects_invalid_model_json(api: TestClient, fake_client: FakeClient) -> None:
    fake_client.models.next_response = make_response('{"category":"nope"}')
    assert api.post("/v1/triage", json={"ticket": "hello"}).status_code == 502
