"""Stage 2: multi-turn chat, thinking control and structured output.

Run:  GEMINI_API_KEY=... python examples/02_chat_structured_thinking.py
"""

from __future__ import annotations

import os
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")


class Incident(BaseModel):
    service: str
    severity: Literal["sev1", "sev2", "sev3"]
    probable_cause: str = Field(description="One sentence.")
    next_steps: list[str] = Field(max_length=3)


def chat_demo(client: genai.Client) -> None:
    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction="You are a terse SRE mentor. Answer in at most three sentences.",
        ),
    )
    print(chat.send_message("What is an error budget?").text)
    # The SDK resends the whole history, so "it" resolves to "error budget".
    print(chat.send_message("How do I compute it for a 99.9% SLO over 30 days?").text)
    print(f"turns kept client-side: {len(chat.get_history())}")


def thinking_demo(client: genai.Client) -> None:
    response = client.models.generate_content(
        model=MODEL,
        contents="A queue receives 120 msg/s; each worker handles 7 msg/s. "
        "How many workers keep utilisation under 80%?",
        config=types.GenerateContentConfig(
            # Gemini 3 models take thinking_level. Gemini 2.5 models take
            # thinking_budget (a token count) instead; do not send both.
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW, include_thoughts=True
            ),
        ),
    )
    for part in response.candidates[0].content.parts:
        label = "THOUGHT SUMMARY" if part.thought else "ANSWER"
        print(f"[{label}] {part.text}")
    print(f"thinking tokens billed: {response.usage_metadata.thoughts_token_count}")


def structured_demo(client: genai.Client) -> None:
    log = (
        "2026-10-30T02:14Z checkout-api p99 latency 9.8s, error rate 31%. "
        "Postgres connections at max_connections=200. Deploy 4f2a rolled out 02:05Z."
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=log,
        config=types.GenerateContentConfig(
            system_instruction="Turn the alert into an incident record.",
            response_mime_type="application/json",
            response_json_schema=Incident.model_json_schema(),
        ),
    )
    incident = Incident.model_validate_json(response.text)
    print(incident.model_dump_json(indent=2))


if __name__ == "__main__":
    with genai.Client() as c:
        chat_demo(c)
        thinking_demo(c)
        structured_demo(c)
