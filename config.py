"""One place for all settings: API key, model names, prices."""

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Models under test (see CLAUDE.md). Sonnet is primary, Haiku secondary.
SONNET = "claude-sonnet-4-5"
HAIKU = "claude-haiku-4-5"

# Anthropic list prices in USD per million tokens. Verify against current
# pricing at https://www.anthropic.com/pricing before a real run.
PRICES_USD = {
    SONNET: {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    HAIKU: {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
}

# USD -> EUR multiplier. Update as the exchange rate moves.
EUR_PER_USD = 0.92

# Output token cap per API call. GAIA answers are short but the model reasons
# before answering, so leave some room.
MAX_TOKENS = 4096
