from app.config import Settings
from app.llm.base import LLMProvider, ProviderError
from app.llm.fake import DemoProvider, FakeProvider
from app.llm.gemini import GeminiProvider
from app.llm.openai_compat import OpenAICompatibleProvider

__all__ = [
    "DemoProvider",
    "FakeProvider",
    "GeminiProvider",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "ProviderError",
    "build_provider",
]


def build_provider(settings: Settings) -> LLMProvider:
    """Pick the provider from LLM_PROVIDER. Switching providers needs no code change."""
    if settings.llm_provider == "fake":
        return DemoProvider()

    if settings.llm_api_key is None:
        raise RuntimeError(f"LLM_API_KEY is required when LLM_PROVIDER={settings.llm_provider}")
    key = settings.llm_api_key.get_secret_value()

    if settings.llm_provider == "gemini":
        return GeminiProvider(
            key,
            settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )
    if not settings.llm_base_url:
        raise RuntimeError("LLM_BASE_URL is required when LLM_PROVIDER=openai_compatible")
    return OpenAICompatibleProvider(
        key,
        settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
    )
