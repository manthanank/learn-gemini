"""Thin service layer over the Google Gen AI SDK (`google-genai`).

Routes never touch the SDK directly. They call `GeminiService`, which
builds the request config, calls the model, and turns the SDK response into
plain values. Tests swap the SDK client for a fake with the same shape.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import errors, types

from app.config import Settings
from app.schemas import GenerateRequest, TicketTriage, Usage

TRIAGE_INSTRUCTION = (
    "You triage customer support tickets for a SaaS product. "
    "Classify the ticket, pick a priority, and write a one-sentence summary. "
    "Never invent details that are not in the ticket."
)

# Finish reasons that mean "the model produced a normal answer".
_OK_FINISH = {types.FinishReason.STOP, types.FinishReason.MAX_TOKENS}


class GeminiUnavailable(RuntimeError):
    """No credentials configured, so the service cannot call Gemini."""


class GeminiBlocked(RuntimeError):
    """The prompt or the answer was stopped (safety, recitation, and so on)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"generation stopped: {reason}")
        self.reason = reason


def build_client(settings: Settings) -> genai.Client:
    """Create one SDK client per process. It holds a pooled HTTP connection."""
    if not settings.configured:
        raise GeminiUnavailable(
            "Set GEMINI_API_KEY, or GOOGLE_GENAI_USE_ENTERPRISE=true with GOOGLE_CLOUD_PROJECT."
        )
    http_options = types.HttpOptions(
        timeout=settings.timeout_ms,
        retry_options=types.HttpRetryOptions(
            attempts=settings.retry_attempts,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        ),
    )
    if settings.enterprise:
        return genai.Client(
            enterprise=True,
            project=settings.project,
            location=settings.location,
            http_options=http_options,
        )
    return genai.Client(api_key=settings.api_key, http_options=http_options)


def build_config(req: GenerateRequest) -> types.GenerateContentConfig:
    """Translate an API request into a GenerateContentConfig.

    Only fields the caller set are sent, so model defaults stay in charge.
    Gemini 3 models are tuned for temperature 1.0; leave it unset unless you
    have measured that a different value helps.
    """
    kwargs: dict[str, Any] = {}
    if req.system_instruction:
        kwargs["system_instruction"] = req.system_instruction
    if req.temperature is not None:
        kwargs["temperature"] = req.temperature
    if req.max_output_tokens is not None:
        kwargs["max_output_tokens"] = req.max_output_tokens
    if req.thinking_level is not None:
        kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=types.ThinkingLevel(req.thinking_level.upper())
        )
    return types.GenerateContentConfig(**kwargs)


def usage_from(response: types.GenerateContentResponse) -> Usage:
    meta = response.usage_metadata
    if meta is None:
        return Usage()
    return Usage(
        prompt_tokens=meta.prompt_token_count or 0,
        output_tokens=meta.candidates_token_count or 0,
        thinking_tokens=meta.thoughts_token_count or 0,
        cached_tokens=meta.cached_content_token_count or 0,
        total_tokens=meta.total_token_count or 0,
    )


def check_finished(response: types.GenerateContentResponse) -> str:
    """Return the finish reason name, or raise GeminiBlocked.

    A blocked prompt has no candidates at all, only `prompt_feedback`.
    A blocked answer has a candidate whose finish_reason is not STOP/MAX_TOKENS.
    """
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        raise GeminiBlocked(f"prompt blocked ({feedback.block_reason.name})")
    if not response.candidates:
        raise GeminiBlocked("no candidates returned")
    reason = response.candidates[0].finish_reason
    if reason is not None and reason not in _OK_FINISH:
        raise GeminiBlocked(reason.name)
    return reason.name if reason is not None else "STOP"


class GeminiService:
    def __init__(self, client: Any, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def model(self) -> str:
        return self._settings.model

    def generate(self, req: GenerateRequest) -> tuple[str, str, Usage]:
        response = self._client.models.generate_content(
            model=self.model,
            contents=req.prompt,
            config=build_config(req),
        )
        finish = check_finished(response)
        return response.text or "", finish, usage_from(response)

    def stream(self, req: GenerateRequest) -> Iterator[str]:
        """Yield text deltas. Chunks with no text (for example thought-only) are skipped."""
        for chunk in self._client.models.generate_content_stream(
            model=self.model,
            contents=req.prompt,
            config=build_config(req),
        ):
            if chunk.text:
                yield chunk.text

    def count_tokens(self, text: str) -> int:
        result = self._client.models.count_tokens(model=self.model, contents=text)
        return result.total_tokens or 0

    def triage(self, ticket: str) -> TicketTriage:
        response = self._client.models.generate_content(
            model=self.model,
            contents=ticket,
            config=types.GenerateContentConfig(
                system_instruction=TRIAGE_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=TicketTriage.model_json_schema(),
            ),
        )
        check_finished(response)
        # Validate on our side too: the schema constrains decoding, but the
        # service boundary should still refuse anything that does not parse.
        return TicketTriage.model_validate_json(response.text or "")


def api_error_status(exc: errors.APIError) -> int:
    """Map an SDK error to the HTTP status this service returns."""
    if exc.code == 429:
        return 429
    if exc.code in (400, 404):
        return 400
    # 401/403 mean our credentials are wrong, and 5xx is upstream trouble.
    # Neither is the caller's fault, so both surface as a bad gateway.
    return 502
