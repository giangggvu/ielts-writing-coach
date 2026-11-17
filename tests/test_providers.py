"""Real provider classes, tested against a fake HTTP server (no network, no key)."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm import (
    DemoProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
    ProviderError,
    build_provider,
)


def sse_body(payloads: list) -> bytes:
    lines = [f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in payloads]
    return "".join(lines).encode()


async def collect(provider) -> str:
    return "".join([c async for c in provider.stream("system", "prompt")])


async def test_gemini_streams_text_and_skips_thoughts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            content=sse_body(
                [
                    {"candidates": [{"content": {"parts": [{"text": "plan", "thought": True}]}}]},
                    {"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]},
                    {"candidates": [{"content": {"parts": [{"text": "world"}]}}]},
                ]
            ),
        )

    p = GeminiProvider("secret-key", "gemini-test", transport=httpx.MockTransport(handler))
    assert await collect(p) == "Hello world"

    req = seen["request"]
    assert req.url.path == "/v1beta/models/gemini-test:streamGenerateContent"
    assert req.headers["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in str(req.url)  # key never ends up in URLs or access logs
    assert json.loads(req.content)["systemInstruction"]["parts"][0]["text"] == "system"


async def test_openai_compatible_streams_deltas():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer k"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            content=sse_body(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"content": "Band "}}]},
                    {"choices": [{"delta": {"content": "7"}}]},
                    "[DONE]",
                ]
            ),
        )

    p = OpenAICompatibleProvider(
        "k", "m", base_url="https://api.example.com/v1/", transport=httpx.MockTransport(handler)
    )
    assert await collect(p) == "Band 7"


@pytest.mark.parametrize(("status", "words"), [(429, "rate limit"), (401, "API key"), (500, "500")])
async def test_http_errors_become_friendly_provider_errors(status, words):
    transport = httpx.MockTransport(lambda r: httpx.Response(status, text="secret details"))
    p = GeminiProvider("k", "m", transport=transport)
    with pytest.raises(ProviderError, match=words) as info:
        await collect(p)
    assert "secret details" not in str(info.value)


async def test_network_failure_becomes_provider_error():
    def boom(request):
        raise httpx.ConnectError("down")

    p = OpenAICompatibleProvider("k", "m", base_url="http://x", transport=httpx.MockTransport(boom))
    with pytest.raises(ProviderError):
        await collect(p)


def test_provider_is_chosen_by_environment():
    base = {"jwt_secret": "x" * 32}
    assert isinstance(build_provider(Settings(**base, llm_provider="fake")), DemoProvider)
    gemini = build_provider(Settings(**base, llm_provider="gemini", llm_api_key="k"))
    assert isinstance(gemini, GeminiProvider)
    groq = build_provider(
        Settings(
            **base,
            llm_provider="openai_compatible",
            llm_api_key="k",
            llm_base_url="https://api.groq.com/openai/v1",
            llm_model="openai/gpt-oss-120b",
        )
    )
    assert isinstance(groq, OpenAICompatibleProvider)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        build_provider(Settings(**base, llm_provider="gemini"))
