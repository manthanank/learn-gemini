"""Request, response and structured-output models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system_instruction: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=65_536)
    thinking_level: Literal["minimal", "low", "medium", "high"] | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0


class GenerateResponse(BaseModel):
    text: str
    model: str
    finish_reason: str
    usage: Usage


class TokenCountRequest(BaseModel):
    text: str = Field(min_length=1)


class TokenCountResponse(BaseModel):
    model: str
    total_tokens: int


class TriageRequest(BaseModel):
    ticket: str = Field(min_length=1)


class TicketTriage(BaseModel):
    """Schema Gemini must fill in. Field descriptions are sent to the model."""

    category: Literal["billing", "bug", "feature_request", "account", "other"]
    priority: Literal["p0", "p1", "p2", "p3"] = Field(
        description="p0 means production is down for many users; p3 is cosmetic."
    )
    summary: str = Field(description="One sentence, under 25 words.")
    needs_human: bool = Field(
        description="True when the ticket mentions refunds, legal threats or data loss."
    )
