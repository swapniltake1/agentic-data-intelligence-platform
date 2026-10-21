"""Sanitized user-facing messages for agent failures."""

from utils.llm_pick import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
)


def safe_agent_error_message(exception: Exception) -> str:
    """Map known provider failures to safe, actionable chat messages."""
    if isinstance(exception, LLMAuthenticationError):
        return (
            f"The {exception.provider.title()} API key was rejected. "
            "Check that provider's credential settings."
        )
    if isinstance(exception, LLMConfigurationError):
        return (
            "The AI provider configuration is invalid. "
            "Check provider priority and free-model settings."
        )
    if isinstance(exception, LLMProviderError):
        return (
            "All configured AI providers are currently unavailable. "
            "Please try again later."
        )
    if isinstance(exception, OSError):
        return "No AI provider is configured. Add a supported provider API key."
    return "I couldn't complete your request right now. Please try again."
