"""LLM provider factory. Credentials come only from settings/environment; none are hardcoded.

Supported providers (optional extras, see requirements-llm.txt):
  openai    -> langchain-openai    ChatOpenAI     (OPENAI_API_KEY, LLM_MODEL)
  anthropic -> langchain-anthropic ChatAnthropic  (ANTHROPIC_API_KEY, LLM_MODEL)
  watsonx   -> langchain-ibm       ChatWatsonx    (WATSONX_APIKEY, WATSONX_PROJECT_ID, LLM_MODEL)

``build_llm`` returns ``None`` when LLM_PROVIDER is "none". It raises ``LlmConfigError`` (with a
non-secret message) when a provider is selected but incomplete or its package is missing.
Constructing a client does not contact the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from civiclens.config import Settings


class LlmConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmHandle:
    model: Any  # a LangChain BaseChatModel
    provider: str
    model_name: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model_name}"


def _need(value: Any, what: str) -> Any:
    if value is None or (hasattr(value, "get_secret_value") and not value.get_secret_value()):
        raise LlmConfigError(f"{what} is not set.")
    return value.get_secret_value() if hasattr(value, "get_secret_value") else value


def llm_configured(settings: Settings) -> bool:
    return settings.llm_provider != "none"


def build_llm(settings: Settings) -> LlmHandle | None:
    provider = settings.llm_provider
    if provider == "none":
        return None
    model_name = _need(settings.llm_model, "LLM_MODEL")
    timeout = settings.llm_timeout_s
    try:
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            model: Any = ChatOpenAI(
                model=model_name,
                api_key=_need(settings.openai_api_key, "OPENAI_API_KEY"),
                timeout=timeout,
                max_retries=1,
                temperature=0,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            model = ChatAnthropic(
                model=model_name,
                api_key=_need(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
                timeout=timeout,
                max_retries=1,
                temperature=0,
            )
        elif provider == "watsonx":
            from langchain_ibm import ChatWatsonx

            model = ChatWatsonx(
                model_id=model_name,
                url=settings.watsonx_url,
                apikey=_need(settings.watsonx_apikey, "WATSONX_APIKEY"),
                project_id=_need(settings.watsonx_project_id, "WATSONX_PROJECT_ID"),
                params={"temperature": 0, "max_tokens": 1500},
            )
        else:  # pragma: no cover - guarded by the Literal type
            raise LlmConfigError(f"Unknown provider {provider!r}.")
    except ImportError as exc:
        raise LlmConfigError(
            f"Provider package for {provider!r} is not installed (pip install -r requirements-llm.txt)."
        ) from exc
    return LlmHandle(model=model, provider=provider, model_name=model_name)
