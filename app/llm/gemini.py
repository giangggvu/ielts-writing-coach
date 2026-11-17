from collections.abc import AsyncIterator

import httpx

from app.llm.base import ProviderError, friendly_http_error, iter_sse_json

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiProvider:
    """Google Gemini API (has a free tier via Google AI Studio)."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str | None = None,
        timeout: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        url = f"{self._base_url}/v1beta/models/{self.model}:streamGenerateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
        }
        headers = {"x-goog-api-key": self._api_key}
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
                client.stream("POST", url, params={"alt": "sse"}, json=body, headers=headers) as r,
            ):
                if r.status_code != 200:
                    raise friendly_http_error("Gemini", r.status_code)
                async for payload in iter_sse_json(r):
                    for candidate in payload.get("candidates", [])[:1]:
                        for part in candidate.get("content", {}).get("parts", []):
                            if part.get("thought"):
                                continue
                            if text := part.get("text"):
                                yield text
        except httpx.TimeoutException as exc:
            raise ProviderError("Gemini took too long to answer. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Could not reach Gemini. Please try again later.") from exc
