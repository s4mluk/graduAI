# Testbench: LLM Agent Token Optimization Strategies

Empirical part of a master's thesis. Runs the same GAIA task set under different
token-optimization strategies and measures cost per successful task.

## Setup

```bash
uv sync
cp .env.example .env   # then paste your ANTHROPIC_API_KEY into .env
```

## Run (Phase 1)

```bash
uv run run.py --strategy baseline --limit 1
```

Runs the first GAIA task with the baseline strategy and prints the answer,
token counts, and cost.

## Files

- `config.py` — API key, model names, prices.
- `agent.py` — `run_agent(task, strategy)` → `AgentResult`.
- `strategies.py` — strategies (Phase 1: `baseline`).
- `tasks.py` — loads `tasks/gaia_sample.json`.
- `metrics.py` — cost calculation.
- `run.py` — command-line runner.

## Models under test

Claude Sonnet 4.5 (primary), Claude Haiku 4.5 (secondary). Prices in
`config.py` are USD list prices converted to EUR — verify before a real run.

## Safety

Never commit `.env`. Later phases add a `--max-cost-eur` cap; also set a spend
limit in the Anthropic console.
