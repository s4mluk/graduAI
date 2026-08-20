# Testbench: LLM Agent Token Optimization Strategies

Empirical part of a master's thesis. Runs the same GAIA task set under different
token-optimization strategies and measures cost per successful task.

## Setup

```bash
uv sync
cp .env.example .env   # then paste your ANTHROPIC_API_KEY into .env
```

## Run

```bash
uv run run.py --strategy baseline --limit 1              # smoke test, one task
uv run run.py --strategy baseline --max-cost-eur 3       # all 24 tasks
uv run run.py --strategy baseline --repeats 3 --max-cost-eur 10
uv run run.py --strategy baseline --resume results/20260819_150522
```

| Argument | Default | Meaning |
|---|---|---|
| `--strategy` | `baseline` | Which strategy to run (see below) |
| `--tasks` | all | Comma-separated `task_id`s to run a subset |
| `--repeats` | 1 | Runs per task — needed, web search is nondeterministic |
| `--limit` | all | Cap the number of tasks |
| `--max-cost-eur` | 5 | Stop before exceeding this (checked before each task) |
| `--resume` | new dir | Continue an existing results dir instead of starting fresh |

Always smoke-test with `--limit 1` before a large run.

## Analyze

```bash
uv run analyze.py    # reads every results/*/run.jsonl → table + results/pareto.png
```

## Strategies

| Name | Mechanism |
|---|---|
| `baseline` | Full context, native web search, no optimization |
| `prompt_caching` | Top-level `cache_control` auto-caches the message prefix |
| `model_routing` | Haiku answers first; escalate to Sonnet unless it is confident |
| `context_compression` | Native context editing clears old tool results |
| `context_isolation` | Orchestrator splits the question; subagents see only their own subtask |

## Documentation

- **`ARCHITECTURE.md`** — how it works and why: data flow, the shared agent
  loop, each strategy's logic, what is held constant, known limitations.
- **`NOTES.md`** — dated findings and methodological decisions with reasoning.
- **`CLAUDE.md`** — project goals and phasing.

## Models under test

Claude Sonnet 4.5 (primary), Claude Haiku 4.5 (`model_routing` only). Prices in
`config.py` are USD list prices converted to EUR at a fixed rate — verify both
before a real run.

## Safety

Never commit `.env`. Always pass `--max-cost-eur`. Also set a spend limit in the
Anthropic console.
