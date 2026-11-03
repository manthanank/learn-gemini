from __future__ import annotations

import pytest

from app.config import DEFAULT_MODEL, Settings

ENV_VARS = [
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_MODEL",
    "GOOGLE_GENAI_USE_ENTERPRISE",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_env() -> None:
    s = Settings.from_env()
    assert s.model == DEFAULT_MODEL
    assert s.backend == "developer-api"
    assert s.configured is False


def test_google_api_key_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "google")
    assert Settings.from_env().api_key == "google"


def test_enterprise_needs_a_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    s = Settings.from_env()
    assert s.backend == "agent-platform"
    assert s.configured is False
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    assert Settings.from_env().configured is True


def test_legacy_vertexai_flag_still_selects_enterprise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
    assert Settings.from_env().enterprise is True


def test_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert Settings.from_env().model == "gemini-2.5-flash"
