from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Custom exception for AI provider errors."""
    pass


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def generate_content(self, prompt: str) -> str:
        """Generate content from a prompt and return the text response."""
        pass
