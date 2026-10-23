"""Shared multi-provider chat model configuration and invocation helpers."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import TypeAdapter, ValidationError

from google.api_core.exceptions import (
    NotFound,
    ResourceExhausted,
    ServiceUnavailable,
    TooManyRequests,
)
from google.genai.errors import ServerError
from langchain_google_genai.chat_models import (
    GoogleModelNotFoundError,
    GoogleRateLimitError,
)

load_dotenv()
logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


MODEL_CONFIG: dict[ModelTier, dict[str, Any]] = {
    ModelTier.LOW: {
        "model": "gemini-3.5-flash-lite",
        "reasoning_effort": "minimal",
    },
    ModelTier.MEDIUM: {
        "model": "gemini-3.5-flash-lite",
        "reasoning_effort": "low",
    },
    ModelTier.HIGH: {
        "model": "gemini-3.5-flash-lite",
        "reasoning_effort": "medium",
    },
}

DEFAULT_PROVIDER_PRIORITY = ("groq", "openrouter", "gemini")
DEFAULT_GROQ_MODELS = {
    ModelTier.LOW: "openai/gpt-oss-20b",
    ModelTier.MEDIUM: "openai/gpt-oss-120b",
    ModelTier.HIGH: "openai/gpt-oss-120b",
}
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_last_model_metadata: ContextVar[dict[str, Any] | None] = ContextVar(
    "last_model_metadata", default=None
)
_request_metadata: ContextVar[dict[str, Any] | None] = ContextVar(
    "request_metadata", default=None
)


class LLMProviderError(RuntimeError):
    """Raised when no configured provider can complete an LLM request."""


class LLMConfigurationError(ValueError):
    """Raised for invalid provider order or a free-only model configuration."""


class LLMAuthenticationError(LLMConfigurationError):
    """Raised when a configured provider rejects its API key."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Authentication failed for {provider}.")


class _StructuredOutputError(ValueError):
    """Raised when a provider returns data that does not match its schema."""


def _normalize_tier(level: str | ModelTier) -> ModelTier:
    if isinstance(level, ModelTier):
        return level
    try:
        return ModelTier(level.lower().strip())
    except (AttributeError, ValueError) as exc:
        valid = [tier.value for tier in ModelTier]
        raise ValueError(f"Invalid tier '{level}'. Supported: {valid}") from exc


def _provider_priority() -> tuple[str, ...]:
    configured = os.getenv("LLM_PROVIDER_PRIORITY")
    if not configured:
        return DEFAULT_PROVIDER_PRIORITY

    priority = tuple(item.strip().lower() for item in configured.split(",") if item.strip())
    unknown = set(priority) - set(DEFAULT_PROVIDER_PRIORITY)
    if not priority or unknown or len(set(priority)) != len(priority):
        raise LLMConfigurationError(
            "LLM_PROVIDER_PRIORITY must contain each selected provider once "
            "from groq, openrouter, gemini."
        )
    return priority


def _provider_key(provider: str) -> str | None:
    if provider == "groq":
        return os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY")
    if provider == "openrouter":
        return os.getenv("OPENROUTER_KEY") or os.getenv("OPENROUTER_API_KEY")
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _model_for(provider: str, tier: ModelTier) -> str:
    tier_name = tier.value.upper()
    if provider == "groq":
        return (
            os.getenv(f"GROQ_MODEL_{tier_name}")
            or os.getenv("GROQ_MODEL")
            or DEFAULT_GROQ_MODELS[tier]
        )
    if provider == "openrouter":
        return (
            os.getenv(f"OPENROUTER_MODEL_{tier_name}")
            or os.getenv("OPENROUTER_MODEL")
            or DEFAULT_OPENROUTER_MODEL
        )
    return os.getenv(f"GEMINI_MODEL_{tier_name}") or MODEL_CONFIG[tier]["model"]


def _free_only() -> bool:
    return os.getenv("LLM_FREE_ONLY", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def _is_configured_free_model(provider: str, model: str) -> bool:
    if provider == "openrouter":
        return model == "openrouter/free" or model.endswith(":free")
    if provider == "groq":
        return _free_only()
    if provider == "gemini":
        return (
            _free_only()
            and os.getenv("GEMINI_FREE_TIER_CONFIRMED", "").strip().lower()
            in {"1", "true", "yes"}
        )
    return False


def get_provider_status() -> list[dict[str, Any]]:
    """Return sanitized provider configuration for diagnostics and the UI."""
    result = []
    priority = _provider_priority()
    all_providers = (*priority, *(p for p in DEFAULT_PROVIDER_PRIORITY if p not in priority))
    for provider in all_providers:
        model = _model_for(provider, ModelTier.MEDIUM)
        free_model = _is_configured_free_model(provider, model)
        result.append(
            {
                "provider": provider,
                "priority_enabled": provider in priority,
                "configured": bool(_provider_key(provider)),
                "model": model,
                "free_tier_configured": free_model,
            }
        )
    return result


def get_last_model_metadata() -> dict[str, Any] | None:
    """Return provider/model metadata for the latest LLM invocation."""
    metadata = _last_model_metadata.get()
    return metadata.copy() if metadata else None


@contextmanager
def capture_llm_metadata():
    """Capture the final selected provider for one application request."""
    metadata: dict[str, Any] = {}
    token = _request_metadata.set(metadata)
    try:
        yield metadata
    finally:
        _request_metadata.reset(token)


def _eligible_providers(tier: ModelTier) -> list[dict[str, str]]:
    configured = []
    has_configured_key = False
    rejected_free_model = False
    for provider in _provider_priority():
        key = _provider_key(provider)
        if not key:
            continue
        has_configured_key = True
        model = _model_for(provider, tier)
        if provider == "openrouter" and _free_only():
            if not _is_configured_free_model(provider, model):
                rejected_free_model = True
                logger.error(
                    "Skipping OpenRouter because free-only mode rejects its configured model."
                )
                continue
        if provider == "gemini" and _free_only():
            if not _is_configured_free_model(provider, model):
                rejected_free_model = True
                logger.info(
                    "Skipping Gemini fallback because free-tier access has not been confirmed."
                )
                continue
        configured.append({"provider": provider, "model": model, "key": key})
    if not configured:
        if has_configured_key and rejected_free_model:
            raise LLMConfigurationError(
                "No configured provider is eligible under free-only settings. "
                "Confirm Gemini free-tier access or use openrouter/free or a verified free model ID."
            )
        raise OSError(
            "No LLM provider is configured. Set GROQ_API_KEY, "
            "OPENROUTER_KEY, or GEMINI_API_KEY/GOOGLE_API_KEY."
        )
    return configured


def _new_provider_model(
    provider: str,
    model: str,
    api_key: str,
    tier: ModelTier = ModelTier.LOW,
):
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            api_key=api_key,
            model=model,
            max_retries=0,
            temperature=0,
        )
    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            model=model,
            max_retries=0,
            temperature=0,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    config = MODEL_CONFIG[tier].copy()
    config["model"] = model
    return ChatGoogleGenerativeAI(
        api_key=api_key,
        max_retries=0,
        **config,
    )


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def _is_auth_error(exc: Exception) -> bool:
    return _status_code(exc) in {401, 403} or type(exc).__name__ in {
        "AuthenticationError",
        "PermissionDenied",
        "GoogleAuthError",
    }


def _is_transient_error(exc: Exception) -> bool:
    status = _status_code(exc)
    name = type(exc).__name__.lower()
    return (
        status in {408, 425, 429}
        or (status is not None and 500 <= status <= 599)
        or isinstance(
            exc,
            (
                GoogleRateLimitError,
                ResourceExhausted,
                TooManyRequests,
                ServiceUnavailable,
                ServerError,
            ),
        )
        or any(
            token in name
            for token in (
                "connection",
                "connect",
                "network",
                "timeout",
                "ratelimit",
                "servererror",
            )
        )
    )


def _is_unavailable_model(exc: Exception) -> bool:
    return _status_code(exc) == 404 or isinstance(
        exc, (GoogleModelNotFoundError, NotFound)
    )


def _is_capability_error(exc: Exception) -> bool:
    if _status_code(exc) != 400:
        return False
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "tool",
            "function calling",
            "json schema",
            "response_format",
            "not supported",
            "does not support",
        )
    )


def _is_fallback_error(exc: Exception) -> bool:
    return (
        _is_transient_error(exc)
        or _is_unavailable_model(exc)
        or _is_capability_error(exc)
        or isinstance(exc, _StructuredOutputError)
    )


def _error_reason(exc: Exception) -> str:
    status = _status_code(exc)
    if status == 429 or "rate" in type(exc).__name__.lower():
        return "rate limited or quota exhausted"
    if _is_capability_error(exc):
        return "required model capability is unavailable"
    if _is_unavailable_model(exc):
        return "model unavailable"
    if status == 400 or isinstance(exc, (TypeError, ValueError)):
        return "invalid provider, model, or request configuration"
    if status is not None:
        return f"HTTP {status}"
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "request timed out"
    if "connection" in name or "connect" in name or "network" in name:
        return "connection failed"
    if "notfound" in name or "modelnotfound" in name:
        return "model unavailable"
    return "temporary provider failure"


def _json_instruction(input_value: Any, schema: Any) -> Any:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=True)
    instruction = (
        "Return only a valid JSON object matching this JSON schema. "
        f"Do not include markdown fences or other text.\n{schema_json}"
    )
    if isinstance(input_value, str):
        return f"{input_value}\n\n{instruction}"
    if isinstance(input_value, BaseMessage):
        return [SystemMessage(content=instruction), input_value]
    if isinstance(input_value, list):
        return [SystemMessage(content=instruction), *input_value]
    return [SystemMessage(content=instruction), HumanMessage(content=str(input_value))]


def _validate_structured_output(response: Any, schema: Any) -> Any:
    if isinstance(response, schema):
        return response
    value = response
    if not isinstance(value, dict):
        text = extract_content(value).strip()
        try:
            value = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _StructuredOutputError("Model returned invalid JSON.") from exc
    try:
        return TypeAdapter(schema).validate_python(value)
    except (ValidationError, TypeError, ValueError) as exc:
        raise _StructuredOutputError("Model output did not match the required schema.") from exc


def _invoke_provider(
    provider_info: dict[str, str],
    tier: ModelTier,
    input_value: Any,
    output_schema: Any | None,
    tools: list[Any] | None,
    stop_after_attempt: int,
) -> Any:
    provider = provider_info["provider"]
    model_name = provider_info["model"]
    model = _new_provider_model(provider, model_name, provider_info["key"], tier)

    structured_native = False
    try:
        if output_schema is not None:
            try:
                model = model.with_structured_output(output_schema)
                structured_native = True
            except (NotImplementedError, TypeError, ValueError):
                pass
        if tools is not None:
            model = model.bind_tools(tools)
    except (NotImplementedError, TypeError, ValueError) as exc:
        raise _StructuredOutputError(
            "Provider does not support the requested model capability."
        ) from exc

    attempts = max(1, stop_after_attempt)
    last_error: Exception | None = None
    for attempt in range(attempts):
        started = time.perf_counter()
        try:
            request = input_value
            if output_schema is not None:
                if structured_native:
                    try:
                        response = model.invoke(request)
                        result = _validate_structured_output(response, output_schema)
                    except _StructuredOutputError:
                        raise
                    except (NotImplementedError, TypeError, ValueError):
                        raw_model = _new_provider_model(
                            provider, model_name, provider_info["key"], tier
                        )
                        if tools is not None:
                            raw_model = raw_model.bind_tools(tools)
                        response = raw_model.invoke(
                            _json_instruction(request, output_schema)
                        )
                        result = _validate_structured_output(response, output_schema)
                else:
                    raw_model = _new_provider_model(
                        provider, model_name, provider_info["key"], tier
                    )
                    if tools is not None:
                        raw_model = raw_model.bind_tools(tools)
                    response = raw_model.invoke(
                        _json_instruction(request, output_schema)
                    )
                    result = _validate_structured_output(response, output_schema)
            else:
                result = model.invoke(request)

            elapsed = time.perf_counter() - started
            metadata = {
                "provider": provider,
                "model": model_name,
                "tier": tier.value,
                "free_tier_configured": _is_configured_free_model(
                    provider, model_name
                ),
            }
            _last_model_metadata.set(metadata)
            request_metadata = _request_metadata.get()
            if request_metadata is not None:
                request_metadata.update(metadata)
            logger.info(
                "LLM request succeeded provider=%s model=%s tier=%s elapsed_seconds=%.3f",
                provider,
                model_name,
                tier.value,
                elapsed,
            )
            return result
        except Exception as exc:
            last_error = exc
            if _is_auth_error(exc):
                logger.error(
                    "LLM authentication failed provider=%s model=%s",
                    provider,
                    model_name,
                )
                raise LLMAuthenticationError(provider) from exc
            if not _is_fallback_error(exc):
                logger.error(
                    "LLM request failed provider=%s model=%s error_type=%s",
                    provider,
                    model_name,
                    type(exc).__name__,
                )
                raise

            if attempt + 1 < attempts and _is_transient_error(exc):
                time.sleep(min(0.5 * (2**attempt) + random.random() * 0.25, 4.0))
                continue

            logger.warning(
                "LLM provider failed provider=%s model=%s elapsed_seconds=%.3f reason=%s",
                provider,
                model_name,
                time.perf_counter() - started,
                "invalid structured output"
                if isinstance(exc, _StructuredOutputError)
                else _error_reason(exc),
            )
            break

    if last_error is None:
        raise LLMProviderError("The LLM provider did not return a response.")
    raise last_error


def _make_runnable(
    level: str | ModelTier,
    stop_after_attempt: int,
    output_schema: Any | None = None,
    tools: list[Any] | None = None,
) -> Runnable:
    tier = _normalize_tier(level)

    def invoke(input_value: Any) -> Any:
        providers = _eligible_providers(tier)
        previous_reason = "primary provider failed"
        for index, provider_info in enumerate(providers):
            try:
                result = _invoke_provider(
                    provider_info,
                    tier,
                    input_value,
                    output_schema,
                    tools,
                    stop_after_attempt,
                )
                if index:
                    logger.info(
                        "LLM provider fallback succeeded provider=%s model=%s reason=%s",
                        provider_info["provider"],
                        provider_info["model"],
                        previous_reason,
                    )
                return result
            except Exception as exc:
                if _is_auth_error(exc):
                    raise LLMAuthenticationError(provider_info["provider"]) from exc
                if not _is_fallback_error(exc):
                    raise
                previous_reason = (
                    "invalid structured output"
                    if isinstance(exc, _StructuredOutputError)
                    else _error_reason(exc)
                )
                if index + 1 < len(providers):
                    logger.warning(
                        "Falling back from provider=%s model=%s reason=%s",
                        provider_info["provider"],
                        provider_info["model"],
                        previous_reason,
                    )
        raise LLMProviderError(
            "All configured LLM providers failed. Check provider availability, "
            "model configuration, and quota, then try again."
        )

    return RunnableLambda(invoke)


def get_base_llm(level: str | ModelTier = ModelTier.LOW) -> Runnable:
    """Create the first configured provider's base chat model for a tier."""
    tier = _normalize_tier(level)
    provider = _eligible_providers(tier)[0]
    return _new_provider_model(
        provider["provider"], provider["model"], provider["key"], tier
    )


def pick_llm(
    level: str | ModelTier = ModelTier.LOW,
    stop_after_attempt: int = 2,
    output_schema: Any | None = None,
) -> Runnable:
    """Create a free-first runnable with bounded transient-error fallback."""
    return _make_runnable(level, stop_after_attempt, output_schema)


def get_tool_llm(
    level: str | ModelTier,
    tools: list[Any],
    stop_after_attempt: int = 2,
) -> Runnable:
    """Create a provider-fallback runnable with the requested tools bound."""
    return _make_runnable(level, stop_after_attempt, tools=tools)


def test_provider(provider: str) -> dict[str, Any]:
    """Perform one explicit minimal health request for a single provider."""
    provider = provider.strip().lower()
    if provider not in DEFAULT_PROVIDER_PRIORITY:
        raise ValueError("Unknown LLM provider.")

    tier = ModelTier.MEDIUM
    key = _provider_key(provider)
    model_name = _model_for(provider, tier)
    result: dict[str, Any] = {
        "provider": provider,
        "model": model_name,
        "configured": bool(key),
        "free_tier_configured": _is_configured_free_model(provider, model_name),
        "healthy": False,
        "latency_ms": None,
        "error": None,
    }
    if not key:
        result["error"] = "API key is not configured."
        return result
    if provider == "openrouter" and _free_only() and not result["free_tier_configured"]:
        result["error"] = "Free-only mode rejects the configured OpenRouter model."
        return result
    if (
        provider == "gemini"
        and _free_only()
        and not result["free_tier_configured"]
    ):
        result["error"] = "Confirm Gemini free-tier access before testing this provider."
        return result

    started = time.perf_counter()
    try:
        model = _new_provider_model(provider, model_name, key, tier)
        model.invoke("Reply only with OK.")
        result["healthy"] = True
    except Exception as exc:
        result["error"] = (
            "Authentication failed."
            if _is_auth_error(exc)
            else _error_reason(exc)
        )
        logger.warning(
            "Provider health check failed provider=%s model=%s error_type=%s reason=%s",
            provider,
            model_name,
            type(exc).__name__,
            result["error"],
        )
    else:
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        logger.info(
            "Provider health check succeeded provider=%s model=%s latency_ms=%d",
            provider,
            model_name,
            result["latency_ms"],
        )
    return result


def extract_content(response: BaseMessage | str | list | Any) -> str:
    """Extract text from common LangChain and provider response formats."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            if isinstance(part, dict)
            else part
            if isinstance(part, str)
            else ""
            for part in content
        )
    return "" if content is None else str(content)
