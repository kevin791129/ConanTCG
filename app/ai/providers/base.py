from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_query: str) -> str:
        """Single-turn: send a prompt and return the model's text response."""
        ...

    @abstractmethod
    def chat(self, system_prompt: str, messages: list[dict]) -> str:
        """Multi-turn: send a conversation history and return the next response."""
        ...
