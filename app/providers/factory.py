import os
from typing import Optional
from .base import AIProvider
from .gemini import GeminiProvider
from .claude import ClaudeProvider


class ProviderFactory:
    """Factory class to create AI provider instances based on configuration."""

    @staticmethod
    def create(provider_name: Optional[str] = None) -> AIProvider:
        if provider_name is None:
            provider_name = os.getenv("AI_PROVIDER", "gemini")

        provider_name = provider_name.lower()

        if provider_name == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set")
            return GeminiProvider(api_key=api_key, model=model)

        elif provider_name == "claude":
            api_key = os.getenv("CLAUDE_API_KEY")
            model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            if not api_key:
                raise ValueError("CLAUDE_API_KEY environment variable is not set")
            return ClaudeProvider(api_key=api_key, model=model)

        else:
            raise ValueError(
                f"Unsupported AI provider: {provider_name}. "
                "Supported providers: gemini, claude"
            )
