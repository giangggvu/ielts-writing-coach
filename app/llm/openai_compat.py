from collections.abc import AsyncIterator

import httpx

from app.llm.base import ProviderError, friendly_http_error, iter_sse_json


class OpenAICompatibleProvider:
    """Any Chat Completions-compatible API: Groq, OpenRouter, OpenAI, a local Ollama...

    Set LLM_BASE_URL, e.g. https://api.groq.com/openai/v1
    """

    name = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str,
        timeout: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        body = {
            "model": self.model,
            "stream": True,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
                client.stream("POST", url, json=body, headers=headers) as r,
            ):
                if r.status_code != 200:
                    raise friendly_http_error("AI provider", r.status_code)
                async for payload in iter_sse_json(r):
                    for choice in payload.get("choices", [])[:1]:
                        if text := (choice.get("delta") or {}).get("content"):
                            yield text
        except httpx.TimeoutException as exc:
            raise ProviderError("The AI provider took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Could not reach the AI provider. Please try again.") from exc
