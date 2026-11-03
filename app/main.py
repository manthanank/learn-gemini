"""FastAPI entry point: `uvicorn app.main:app --host 0.0.0.0 --port 8000`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from google.genai import errors
from pydantic import ValidationError

from app import __version__
from app.config import Settings
from app.gemini import (
    GeminiBlocked,
    GeminiService,
    GeminiUnavailable,
    api_error_status,
    build_client,
)
from app.schemas import (
    GenerateRequest,
    GenerateResponse,
    TicketTriage,
    TokenCountRequest,
    TokenCountResponse,
    TriageRequest,
)


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


_service: GeminiService | None = None


def get_service(settings: Settings = Depends(get_settings)) -> GeminiService:
    """Build the SDK client lazily so /health works without credentials."""
    global _service
    if _service is None:
        try:
            _service = GeminiService(build_client(settings), settings)
        except GeminiUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _service


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    global _service
    if _service is not None:
        close = getattr(_service._client, "close", None)
        if callable(close):
            close()
        _service = None


app = FastAPI(title="learn-gemini starter", version=__version__, lifespan=lifespan)


def _guard(settings: Settings, text: str) -> None:
    if len(text) > settings.max_prompt_chars:
        raise HTTPException(status_code=413, detail="prompt too long")


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "model": settings.model,
        "backend": settings.backend,
        "configured": settings.configured,
    }


@app.post("/v1/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    settings: Settings = Depends(get_settings),
    service: GeminiService = Depends(get_service),
) -> GenerateResponse:
    _guard(settings, req.prompt)
    try:
        text, finish, usage = service.generate(req)
    except GeminiBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except errors.APIError as exc:
        raise HTTPException(status_code=api_error_status(exc), detail=exc.message) from exc
    return GenerateResponse(text=text, model=service.model, finish_reason=finish, usage=usage)


@app.post("/v1/generate/stream")
def generate_stream(
    req: GenerateRequest,
    settings: Settings = Depends(get_settings),
    service: GeminiService = Depends(get_service),
) -> StreamingResponse:
    _guard(settings, req.prompt)

    def events() -> Iterator[str]:
        try:
            for delta in service.stream(req):
                # One SSE event per delta. Newlines inside data need their own
                # "data:" prefix, so split and re-join.
                payload = "\ndata: ".join(delta.split("\n"))
                yield f"data: {payload}\n\n"
            yield "event: done\ndata: [DONE]\n\n"
        except errors.APIError as exc:
            yield f"event: error\ndata: {exc.code} {exc.message}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/v1/tokens", response_model=TokenCountResponse)
def count_tokens(
    req: TokenCountRequest,
    service: GeminiService = Depends(get_service),
) -> TokenCountResponse:
    try:
        total = service.count_tokens(req.text)
    except errors.APIError as exc:
        raise HTTPException(status_code=api_error_status(exc), detail=exc.message) from exc
    return TokenCountResponse(model=service.model, total_tokens=total)


@app.post("/v1/triage", response_model=TicketTriage)
def triage(
    req: TriageRequest,
    settings: Settings = Depends(get_settings),
    service: GeminiService = Depends(get_service),
) -> TicketTriage:
    _guard(settings, req.ticket)
    try:
        return service.triage(req.ticket)
    except GeminiBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="model returned invalid JSON") from exc
    except errors.APIError as exc:
        raise HTTPException(status_code=api_error_status(exc), detail=exc.message) from exc
