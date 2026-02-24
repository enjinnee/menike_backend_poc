import time
import google.genai as genai
from .base import AIProvider, AIProviderError

_RETRY_DELAYS = [5, 15]  # seconds between retries on 429


class GeminiProvider(AIProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate_content(self, prompt: str) -> str:
        last_error = None
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                print(f"Gemini 429 rate limit — retrying in {delay}s (attempt {attempt + 1})")
                time.sleep(delay)
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "429" not in err_str and "RESOURCE_EXHAUSTED" not in err_str:
                    # Not a rate-limit error — no point retrying
                    break
        raise AIProviderError(f"Error communicating with Gemini API: {str(last_error)}")
