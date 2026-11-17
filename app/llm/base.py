import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx


class ProviderError(Exception):
    """The AI provider could not be reached or refused the request.

    The message is safe to show to end users (no keys, no raw provider bodies).
    """


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        """Yield the model's answer as text chunks."""
        ...


def friendly_http_error(provider: str, status_code: int) -> ProviderError:
    if status_code == 429:
        return ProviderError(f"{provider} rate limit reached. Please try again in a minute.")
    if status_code in (401, 403):
        return ProviderError(f"{provider} rejected the API key. Check LLM_API_KEY.")
    if status_code == 404:
        return ProviderError(f"{provider} does not know this model. Check LLM_MODEL.")
    return ProviderError(f"{provider} returned HTTP {status_code}. Please try again later.")


async def iter_sse_json(response: httpx.Response) -> AsyncIterator[dict]:
    """Parse a provider's Server-Sent Events stream into JSON payloads."""
    async for line in response.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue
