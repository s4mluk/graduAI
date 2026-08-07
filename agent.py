"""One agent that runs a task with a given strategy and returns a result."""

import time
from dataclasses import dataclass

from strategies import STRATEGIES


@dataclass
class AgentResult:
    task_id: str
    strategy: str
    answer: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    api_calls: int
    latency_ms: int
    cost_eur: float
    model: str


def run_agent(task: dict, strategy: str) -> AgentResult:
    """Run one task with one strategy. Times the call; the strategy reports
    its own token counts, model, and cost (some strategies use two models)."""
    if strategy not in STRATEGIES:
        raise ValueError(
            f"Unknown strategy '{strategy}'. Available: {list(STRATEGIES)}"
        )

    start = time.perf_counter()
    out = STRATEGIES[strategy](task)
    latency_ms = int((time.perf_counter() - start) * 1000)

    return AgentResult(
        task_id=task["task_id"],
        strategy=strategy,
        answer=out["answer"],
        input_tokens=out["input_tokens"],
        output_tokens=out["output_tokens"],
        cache_read_tokens=out["cache_read_tokens"],
        cache_write_tokens=out["cache_write_tokens"],
        api_calls=out["api_calls"],
        latency_ms=latency_ms,
        cost_eur=out["cost_eur"],
        model=out["model"],
    )
