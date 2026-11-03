"""Stage 3: Files API upload, explicit context cache, cost check, cleanup.

Run:  GEMINI_API_KEY=... python examples/03_files_and_cache.py path/to/large.pdf

The Files API and this cache flow use the Gemini Developer API. On Agent
Platform (formerly Vertex AI) you reference gs:// URIs instead of uploading.
"""

from __future__ import annotations

import os
import sys
import time

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")


def wait_until_active(client: genai.Client, name: str, timeout_s: float = 120) -> types.File:
    """Large video and audio files are processed asynchronously after upload."""
    deadline = time.monotonic() + timeout_s
    while True:
        f = client.files.get(name=name)
        if f.state == types.FileState.ACTIVE:
            return f
        if f.state == types.FileState.FAILED or time.monotonic() > deadline:
            raise RuntimeError(f"file {name} not usable: state={f.state}")
        time.sleep(2)


def main(path: str) -> None:
    with genai.Client() as client:
        uploaded = client.files.upload(file=path)
        uploaded = wait_until_active(client, uploaded.name)
        print(f"uploaded {uploaded.name} ({uploaded.mime_type})")
        print(f"expires {uploaded.expiration_time}")

        size = client.models.count_tokens(model=MODEL, contents=[uploaded])
        print(f"document tokens: {size.total_tokens}")

        cache = None
        try:
            cache = client.caches.create(
                model=MODEL,
                config=types.CreateCachedContentConfig(
                    display_name="stage3-demo",
                    system_instruction="Answer only from the attached document. Cite page numbers.",
                    contents=[uploaded],
                    ttl="900s",
                ),
            )
            print(f"cache {cache.name} expires {cache.expire_time}")

            for question in ("What is the document about?", "List every date it mentions."):
                response = client.models.generate_content(
                    model=MODEL,
                    contents=question,
                    config=types.GenerateContentConfig(cached_content=cache.name),
                )
                usage = response.usage_metadata
                print(f"\nQ: {question}\nA: {response.text}")
                print(
                    f"prompt={usage.prompt_token_count} "
                    f"cached={usage.cached_content_token_count or 0}"
                )
        except Exception as exc:  # demo prints the reason and still cleans up
            print(f"cache step failed ({exc}); the document may be below the model's minimum")
        finally:
            if cache is not None:
                client.caches.delete(name=cache.name)
            client.files.delete(name=uploaded.name)
            print("\ncleaned up cache and file")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python examples/03_files_and_cache.py <file>")
    main(sys.argv[1])
