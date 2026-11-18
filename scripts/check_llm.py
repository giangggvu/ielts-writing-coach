"""Check the configured AI provider: python scripts/check_llm.py"""

import asyncio
import time

import httpx

from app.config import get_settings
from app.llm import build_provider


async def main() -> None:
    s = get_settings()
    print(f"Provider: {s.llm_provider} | Model: {s.llm_model}")

    if s.llm_provider == "gemini" and s.llm_api_key:
        r = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": s.llm_api_key.get_secret_value()},
            params={"pageSize": 200},
            timeout=20,
        )
        names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])]
        print(f"HTTP {r.status_code} | Flash models:", ", ".join(n for n in names if "flash" in n))

    provider = build_provider(s)
    start = time.perf_counter()
    first = None
    text = ""
    try:
        async for chunk in provider.stream("Answer briefly.", "Say hello in five words."):
            first = first if first is not None else time.perf_counter() - start
            text += chunk
        print(f"First chunk: {first:.1f}s | Total: {time.perf_counter() - start:.1f}s | {text!r}")
    except Exception as exc:
        print(f"Failed after {time.perf_counter() - start:.1f}s: {exc}")


asyncio.run(main())
