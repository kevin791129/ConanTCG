import os
from google import genai
from google.genai import types

from app.ai.providers.base import LLMProvider


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model

    def _config(self, system_prompt: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=1024,
            temperature=0,
        )

    def complete(self, system_prompt: str, user_query: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            config=self._config(system_prompt),
            contents=user_query,
        )
        return response.text.strip()

    def chat(self, system_prompt: str, messages: list[dict]) -> str:
        # Convert OpenAI-style messages to Gemini contents format
        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        response = self.client.models.generate_content(
            model=self.model,
            config=self._config(system_prompt),
            contents=contents,
        )
        return response.text.strip()
