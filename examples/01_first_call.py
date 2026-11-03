"""Stage 1: first request, token accounting and streaming.

Run:  GEMINI_API_KEY=... python examples/01_first_call.py
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")


def main() -> None:
    # The client reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment.
    with genai.Client() as client:
        prompt = "In two sentences, explain what a token is to a new backend engineer."

        before = client.models.count_tokens(model=MODEL, contents=prompt)
        print(f"prompt tokens (count_tokens): {before.total_tokens}")

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=400),
        )
        print(response.text)

        usage = response.usage_metadata
        if usage is not None:
            print(
                f"prompt={usage.prompt_token_count} output={usage.candidates_token_count} "
                f"thinking={usage.thoughts_token_count or 0} total={usage.total_token_count}"
            )
        print(f"finish_reason={response.candidates[0].finish_reason}")

        print("\n--- streaming ---")
        for chunk in client.models.generate_content_stream(
            model=MODEL, contents="List three uses of a context window, one per line."
        ):
            print(chunk.text or "", end="", flush=True)
        print()


if __name__ == "__main__":
    main()
