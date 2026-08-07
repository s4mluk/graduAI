"""Optimization strategies.

A strategy is a function that takes a task dict and returns a plain dict with:
    answer, input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, api_calls, model, cost_eur
The agent (agent.py) just wraps timing around it.

Each strategy computes its own cost (via `_cost`), because some strategies
(model_routing) use more than one model in a single run.

All strategies share one agent loop (`_run_loop`); a strategy decides what to
pass into the API call (model, cached system, context editing, ...).
"""

import anthropic

import config
from metrics import compute_cost_eur

# GAIA-style instructions so answers are gradeable (Phase 5).
SYSTEM_PROMPT = (
    "You are a general AI assistant. Answer the question as accurately as "
    "possible. Use the web_search tool when you need up-to-date or factual "
    "information you are unsure about. Finish your reply with a line in the "
    "exact format:\n"
    "FINAL ANSWER: <answer>\n"
    "where <answer> is a number, a short string, or a comma-separated list, "
    "with no extra words, units, or punctuation unless the question asks for them."
)

# For model_routing: ask Haiku to also report its confidence.
ROUTING_SYSTEM = SYSTEM_PROMPT + (
    "\n\nAfter the FINAL ANSWER line, add one more line, exactly "
    "'CONFIDENCE: high' or 'CONFIDENCE: low'. Answer 'high' only if you are "
    "confident your answer is correct and complete. If the task is complex, "
    "needs several steps, or you are unsure, answer 'low'."
)

# Sonnet 4.5 / Haiku 4.5 use the basic web search tool (the dynamic-filtering
# variant needs Sonnet 4.6+). max_uses caps searches per run: production realism
# + budget control, and it must be identical across strategies so they stay
# comparable. See NOTES.md.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Create the Anthropic client lazily so importing this module (e.g. to
    load tasks) doesn't require an API key."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _cost(model: str, r: dict) -> float:
    return compute_cost_eur(
        model,
        r["input_tokens"],
        r["output_tokens"],
        r["cache_read_tokens"],
        r["cache_write_tokens"],
    )


def _run_loop(
    task: dict,
    model: str,
    system,
    extra_kwargs: dict | None = None,
    beta: bool = False,
) -> dict:
    """Shared agent loop: ask the question, let the server-side web search run,
    handle pause_turn, accumulate token usage. Returns tokens + answer (no cost;
    the caller adds cost and model, since one strategy may use two models)."""
    client = _get_client()
    messages = [{"role": "user", "content": task["question"]}]
    extra_kwargs = extra_kwargs or {}
    create = client.beta.messages.create if beta else client.messages.create

    input_tokens = output_tokens = cache_read = cache_write = 0
    api_calls = 0

    while True:
        resp = create(
            model=model,
            max_tokens=config.MAX_TOKENS,
            system=system,
            tools=[WEB_SEARCH_TOOL],
            messages=messages,
            **extra_kwargs,
        )
        api_calls += 1

        u = resp.usage
        input_tokens += u.input_tokens
        output_tokens += u.output_tokens
        cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0

        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break

    answer = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()

    return {
        "answer": answer,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "api_calls": api_calls,
    }


def _parse_confidence(text: str) -> str:
    """Read the 'CONFIDENCE: high/low' line; default to 'low' (escalate) if
    it's missing or unclear."""
    for line in reversed(text.splitlines()):
        if "CONFIDENCE:" in line.upper():
            val = line.upper().split("CONFIDENCE:", 1)[1].strip()
            return "high" if val.startswith("HIGH") else "low"
    return "low"


def _strip_confidence(text: str) -> str:
    """Remove the CONFIDENCE line so it doesn't leak into the scored answer."""
    return "\n".join(
        l for l in text.splitlines() if "CONFIDENCE:" not in l.upper()
    ).strip()


# --- Strategies ------------------------------------------------------------


def run_baseline(task: dict) -> dict:
    """Full context, native web search, no optimization."""
    r = _run_loop(task, config.SONNET, SYSTEM_PROMPT)
    return {**r, "model": config.SONNET, "cost_eur": _cost(config.SONNET, r)}


def run_prompt_caching(task: dict) -> dict:
    """Mark the system prompt (and tools) with cache_control and auto-cache the
    message prefix. See NOTES.md for the single-call caveat."""
    cached_system = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
    ]
    r = _run_loop(
        task,
        config.SONNET,
        cached_system,
        extra_kwargs={"cache_control": {"type": "ephemeral"}},
    )
    return {**r, "model": config.SONNET, "cost_eur": _cost(config.SONNET, r)}


def run_context_compression(task: dict) -> dict:
    """Anthropic native context editing: clear old tool results as context
    grows (keeps the transcript lean without summarizing)."""
    r = _run_loop(
        task,
        config.SONNET,
        SYSTEM_PROMPT,
        beta=True,
        extra_kwargs={
            "betas": ["context-management-2025-06-27"],
            "context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]},
        },
    )
    return {**r, "model": config.SONNET, "cost_eur": _cost(config.SONNET, r)}


def run_model_routing(task: dict) -> dict:
    """Haiku assesses the task first; if it is confident, keep its (cheap)
    answer. Otherwise escalate to Sonnet. Cost is summed across both models."""
    haiku = _run_loop(task, config.HAIKU, ROUTING_SYSTEM)
    haiku_cost = _cost(config.HAIKU, haiku)

    if _parse_confidence(haiku["answer"]) == "high":
        return {
            **haiku,
            "answer": _strip_confidence(haiku["answer"]),
            "model": "haiku",
            "cost_eur": haiku_cost,
        }

    # Not confident -> escalate to Sonnet with a fresh run.
    sonnet = _run_loop(task, config.SONNET, SYSTEM_PROMPT)
    return {
        "answer": sonnet["answer"],
        "input_tokens": haiku["input_tokens"] + sonnet["input_tokens"],
        "output_tokens": haiku["output_tokens"] + sonnet["output_tokens"],
        "cache_read_tokens": haiku["cache_read_tokens"] + sonnet["cache_read_tokens"],
        "cache_write_tokens": haiku["cache_write_tokens"] + sonnet["cache_write_tokens"],
        "api_calls": haiku["api_calls"] + sonnet["api_calls"],
        "model": "haiku+sonnet",
        "cost_eur": haiku_cost + _cost(config.SONNET, sonnet),
    }


STRATEGIES = {
    "baseline": run_baseline,
    "prompt_caching": run_prompt_caching,
    "model_routing": run_model_routing,
    "context_compression": run_context_compression,
}
