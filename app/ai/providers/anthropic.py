import os
import anthropic

from app.ai.providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model

    def complete(self, system_prompt: str, user_query: str) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_query}],
        )
        return message.content[0].text.strip()

    def chat(self, system_prompt: str, messages: list[dict]) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return message.content[0].text.strip()
