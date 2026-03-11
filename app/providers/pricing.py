"""
Njörðr — LLM Cost Calculation

Pricing per 1M tokens (USD). Prices as of March 2026.
Civic tech must count every token — for the budget AND the planet.
"""

# {model_name: {"input": price_per_1M, "output": price_per_1M}}
PRICING: dict[str, dict[str, float]] = {
    # Mistral
    "mistral-small-latest": {"input": 0.20, "output": 0.60},
    "mistral-medium-latest": {"input": 0.40, "output": 1.50},
    "mistral-large-latest": {"input": 2.00, "output": 6.00},
    # OpenAI
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    # Claude
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    # Gemini
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Ollama (local = free, electricity only)
    "ollama": {"input": 0.00, "output": 0.00},
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """
    Compute cost in USD for a single LLM call.

    Returns None if model not found in pricing table.
    """
    prices = PRICING.get(model)
    if not prices:
        # Try prefix match for ollama models (e.g. "qwen2.5:7b")
        if any(model.startswith(prefix) for prefix in ("qwen", "llama", "mistral:", "gemma", "phi")):
            prices = PRICING["ollama"]
    if not prices:
        return None
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


def normalize_usage(usage: dict) -> tuple[int, int]:
    """
    Normalize provider-specific usage dicts to (input_tokens, output_tokens).

    Handles: OpenAI/Mistral (prompt_tokens), Claude (input_tokens), Ollama (prompt_eval_count).
    """
    input_t = usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("prompt_eval_count") or 0
    output_t = usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("eval_count") or 0
    return int(input_t), int(output_t)
