from __future__ import annotations

import logging
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from models.schema import JudgeSchema, RouterSchema
from utils import llm_pick
from utils.ui_errors import safe_agent_error_message


PROVIDER_ENV = (
    "GROQ_API_KEY",
    "GROQ_KEY",
    "OPENROUTER_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "LLM_PROVIDER_PRIORITY",
    "LLM_FREE_ONLY",
    "GEMINI_FREE_TIER_CONFIRMED",
    "OPENROUTER_MODEL",
    "OPENROUTER_MODEL_LOW",
    "OPENROUTER_MODEL_MEDIUM",
    "OPENROUTER_MODEL_HIGH",
    "GROQ_MODEL",
    "GROQ_MODEL_LOW",
    "GROQ_MODEL_MEDIUM",
    "GROQ_MODEL_HIGH",
)


@pytest.fixture(autouse=True)
def clear_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


class APIError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeModel:
    def __init__(
        self,
        provider: str,
        invoke_result: Any = AIMessage(content="OK"),
        *,
        bind_error: Exception | None = None,
    ) -> None:
        self.provider = provider
        self.invoke_result = invoke_result
        self.bind_error = bind_error
        self.bound_tools: list[Any] | None = None
        self.schema: type[BaseModel] | None = None

    def with_structured_output(self, schema: type[BaseModel]) -> FakeModel:
        self.schema = schema
        return self

    def bind_tools(self, tools: list[Any]) -> FakeModel:
        if self.bind_error:
            raise self.bind_error
        self.bound_tools = tools
        return self

    def invoke(self, _input: Any) -> Any:
        if isinstance(self.invoke_result, Exception):
            raise self.invoke_result
        return self.invoke_result


def test_provider_priority_and_tier_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER_PRIORITY", "openrouter,groq")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("GROQ_MODEL_HIGH", "configured-high-model")

    assert llm_pick._provider_priority() == ("openrouter", "groq")
    assert llm_pick._eligible_providers(llm_pick.ModelTier.LOW)[0]["provider"] == "openrouter"
    assert llm_pick._model_for("groq", llm_pick.ModelTier.HIGH) == "configured-high-model"
    assert llm_pick._model_for("groq", llm_pick.ModelTier.LOW) == "openai/gpt-oss-20b"
    assert llm_pick._model_for("groq", llm_pick.ModelTier.MEDIUM) == "openai/gpt-oss-120b"


def test_invalid_provider_priority_is_reported_as_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER_PRIORITY", "groq,unknown")

    with pytest.raises(llm_pick.LLMConfigurationError, match="LLM_PROVIDER_PRIORITY"):
        llm_pick._provider_priority()


def test_missing_provider_keys_raise_clear_configuration_error() -> None:
    with pytest.raises(OSError, match="No LLM provider is configured"):
        llm_pick.pick_llm().invoke("hello")


def test_groq_is_selected_first_and_metadata_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    created: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        created.append(provider)
        return FakeModel(provider, AIMessage(content="Groq response"))

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)
    with llm_pick.capture_llm_metadata() as metadata:
        result = llm_pick.pick_llm("medium").invoke("hello")

    assert result.content == "Groq response"
    assert created == ["groq"]
    assert metadata["provider"] == "groq"
    assert metadata["tier"] == "medium"


def test_openrouter_fallback_after_groq_quota_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    calls: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        calls.append(provider)
        outcome = APIError(429) if provider == "groq" else AIMessage(content="fallback")
        return FakeModel(provider, outcome)

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)
    monkeypatch.setattr(llm_pick.time, "sleep", lambda _delay: None)

    result = llm_pick.pick_llm().invoke("hello")

    assert result.content == "fallback"
    assert calls == ["groq", "openrouter"]


def test_unavailable_model_falls_back_without_retrying_same_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    calls: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        calls.append(provider)
        outcome = APIError(404) if provider == "groq" else AIMessage(content="fallback")
        return FakeModel(provider, outcome)

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)

    result = llm_pick.pick_llm().invoke("hello")

    assert result.content == "fallback"
    assert calls == ["groq", "openrouter"]


def test_gemini_fallback_after_groq_and_openrouter_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    calls: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        calls.append(provider)
        outcome = (
            APIError(503)
            if provider in {"groq", "openrouter"}
            else AIMessage(content="Gemini fallback")
        )
        return FakeModel(provider, outcome)

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)
    monkeypatch.setattr(llm_pick.time, "sleep", lambda _delay: None)

    result = llm_pick.pick_llm().invoke("hello")

    assert result.content == "Gemini fallback"
    assert calls == ["groq", "openrouter", "gemini"]


def test_authentication_failure_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    calls: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        calls.append(provider)
        return FakeModel(provider, APIError(401))

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)

    with pytest.raises(llm_pick.LLMAuthenticationError, match="groq"):
        llm_pick.pick_llm().invoke("hello")
    assert calls == ["groq"]


def test_free_only_blocks_paid_openrouter_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    monkeypatch.setenv("OPENROUTER_MODEL_MEDIUM", "vendor/paid-model")

    status = next(
        item for item in llm_pick.get_provider_status()
        if item["provider"] == "openrouter"
    )
    assert status["free_tier_configured"] is False
    with pytest.raises(llm_pick.LLMConfigurationError, match="eligible under free-only"):
        llm_pick.pick_llm("medium").invoke("hello")


def test_free_only_requires_gemini_free_tier_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    with pytest.raises(llm_pick.LLMConfigurationError, match="Confirm Gemini"):
        llm_pick.pick_llm().invoke("hello")


def test_explicit_provider_health_check_invokes_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    called: list[str] = []

    class HealthyModel:
        def invoke(self, prompt: str) -> AIMessage:
            called.append(prompt)
            return AIMessage(content="OK")

    monkeypatch.setattr(
        llm_pick,
        "_new_provider_model",
        lambda *_args, **_kwargs: HealthyModel(),
    )

    result = llm_pick.test_provider("groq")

    assert result["healthy"] is True
    assert result["latency_ms"] is not None
    assert called == ["Reply only with OK."]


def test_structured_router_output_is_validated_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    calls: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        calls.append(provider)
        value = (
            {"answer": "invalid", "comments": ""}
            if provider == "groq"
            else {"answer": "rag", "comments": "document question"}
        )
        return FakeModel(provider, value)

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)

    result = llm_pick.pick_llm(
        "medium", output_schema=RouterSchema
    ).invoke("question")

    assert isinstance(result, RouterSchema)
    assert result.answer == "rag"
    assert calls == ["groq", "openrouter"]


def test_sql_judge_schema_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        return FakeModel(provider, {"answer": "maybe", "comments": "unclear"})

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)

    with pytest.raises(llm_pick.LLMProviderError):
        llm_pick.pick_llm(
            "low", output_schema=JudgeSchema
        ).invoke("Review this query.")


def test_sql_judge_failure_blocks_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agents import sql_analyst
    from models.schema import AgentSchema

    class FailedJudge:
        def invoke(self, _prompt: str) -> Any:
            raise ValueError("structured response parsing failed")

    monkeypatch.setattr(sql_analyst, "pick_llm", lambda *_args, **_kwargs: FailedJudge())
    state = AgentSchema(
        messages=[],
        user_question="How many rows?",
        curated_ques="How many rows?",
        prompt_query_context="",
        is_safe="No",
        comments="",
        generated_sql_query="SELECT 1",
        sql_query_execution_result="",
        final_answer="",
    )

    result = sql_analyst.is_safe_sql(state)

    assert result.is_safe == "No"
    assert result.comments == "SQL safety judge failed. Execution blocked."


def test_etl_tool_binding_falls_back_when_provider_lacks_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENROUTER_KEY", "openrouter-test-key")
    tool = object()
    calls: list[str] = []

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        calls.append(provider)
        unsupported = NotImplementedError("tools unsupported") if provider == "groq" else None
        return FakeModel(provider, AIMessage(content="done"), bind_error=unsupported)

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)

    result = llm_pick.get_tool_llm("medium", [tool]).invoke("run task")

    assert result.content == "done"
    assert calls == ["groq", "openrouter"]


def test_rag_embeddings_remain_gemini_based(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rag import vector_store

    captured: dict[str, Any] = {}

    def fake_embeddings(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return kwargs

    monkeypatch.setenv("GOOGLE_API_KEY", "embedding-test-key")
    monkeypatch.setenv("GOOGLE_EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setattr(vector_store, "GoogleGenerativeAIEmbeddings", fake_embeddings)
    vector_store.get_embeddings.cache_clear()

    try:
        vector_store.get_embeddings()
    finally:
        vector_store.get_embeddings.cache_clear()

    assert captured["model"] == "gemini-embedding-001"
    assert captured["google_api_key"] == "embedding-test-key"


def test_provider_failure_logs_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")

    def build(provider: str, _model: str, _key: str, _tier: Any) -> FakeModel:
        return FakeModel(provider, ValueError("sensitive prompt text"))

    monkeypatch.setattr(llm_pick, "_new_provider_model", build)
    caplog.set_level(logging.ERROR, logger="utils.llm_pick")

    with pytest.raises(ValueError):
        llm_pick.pick_llm().invoke("sensitive prompt text")

    assert "sensitive prompt text" not in caplog.text


def test_frontend_error_messages_are_actionable_and_sanitized() -> None:
    auth_error = llm_pick.LLMAuthenticationError("groq")
    generic_error = RuntimeError("private prompt and provider response")

    assert "Groq API key was rejected" in safe_agent_error_message(auth_error)
    assert "private prompt" not in safe_agent_error_message(generic_error)
