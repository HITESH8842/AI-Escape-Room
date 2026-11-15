"""
Small wrapper around the Google Gemini API (google-genai SDK).

If no API key is configured, `available` is False and the game still works:
the engine's factual messages are shown directly (useful for testing and demos).
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.client = None
        self.last_error = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as exc:  # missing package, bad key format, ...
                self.last_error = str(exc)

    @property
    def available(self) -> bool:
        return self.client is not None

    def generate(self, system: str, prompt: str, json_mode: bool = False, temperature: float = 0.7) -> str | None:
        """Return the model's text, or None if the call fails."""
        if not self.available:
            return None
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=prompt, config=config)
            return response.text
        except Exception as exc:  # network error, quota (429), invalid model ...
            self.last_error = str(exc)
            return None
