from app.ai.providers.base import LLMProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.anthropic import AnthropicProvider
 
 
PROVIDERS: dict[str, tuple[str, callable]] = {
    "claude-haiku-4-5-20251001":  ("Claude Haiku 4.5 (Anthropic)",  lambda: AnthropicProvider("claude-haiku-4-5-20251001")),
    "claude-sonnet-4-6":          ("Claude Sonnet 4.6 (Anthropic)",  lambda: AnthropicProvider("claude-sonnet-4-6")),
    "gemini-2.0-flash":           ("Gemini 2.0 Flash (Google)",      lambda: GeminiProvider("gemini-2.0-flash")),
    "gemini-2.0-flash-lite":      ("Gemini 2.0 Flash Lite (Google)", lambda: GeminiProvider("gemini-2.0-flash-lite")),
    "gemini-2.5-flash":           ("Gemini 2.5 Flash (Google)",      lambda: GeminiProvider("gemini-2.5-flash")),
    "gemini-2.5-pro":             ("Gemini 2.5 Pro (Google)",        lambda: GeminiProvider("gemini-2.5-pro")),
}
 
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def get_provider(model: str) -> LLMProvider:
    entry = PROVIDERS.get(model)
    if entry is None:
        raise ValueError(f"Unsupported model: {model}")
    _, factory = entry
    return factory()


def get_model_choices() -> list[dict]:
    """Return model list for use in UI dropdowns."""
    return [
        {"id": model_id, "label": label}
        for model_id, (label, _) in PROVIDERS.items()
    ]
