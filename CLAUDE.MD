Testbench: LLM Agent Token Optimization Strategies
Goal

Build a testbench that runs the same task set with different optimization strategies
and measures cost per successful task. This is the empirical part of a master's thesis.

Start with the simplest possible version. No over-engineering. Get one task + one
strategy working first, then expand.

Principles
Simple > complete. No abstractions that aren't needed yet.
One thing at a time. Don't try to build everything at once.
Human-readable code. Sami will return to this in 2 months — the code needs to be understandable without notes.
Results visible immediately. After each run, the human sees what happened.
Technical Environment
Python 3.11+
Package management: uv
LLM provider: Anthropic (Claude Sonnet 4.5 primary, Haiku secondary)
No framework needed (LangChain, LlamaIndex, etc.) — keep it thin
Folder Structure
testbench/
├── .env                    # ANTHROPIC_API_KEY (never in Git)
├── .env.example
├── pyproject.toml
├── README.md
├── config.py               # One place for all settings
├── agent.py                # One agent implementation that takes strategy as parameter
├── strategies.py           # All strategies in one file initially
├── tasks.py                # GAIA task loading
├── run.py                  # Run logic
├── metrics.py              # Cost calculation and result aggregation
├── tasks/
│   └── gaia_sample.json    # Sample of 24 tasks
└── results/
    └── {timestamp}/        # Each run in its own folder
        └── run.jsonl       # All runs in one JSONL (easy to read)

Note: No separate agents/, strategies/, runners/ folders. One file per
concern is enough until files exceed 300 lines. Then we can split.

Phase 1: Get Minimal Working

Goal: one GAIA task runs through with the baseline strategy and the result is visible in the terminal.

Build:

config.py — API key, model names, prices in euros per million tokens
agent.py — function run_agent(task, strategy) that takes a task and strategy and returns AgentResult:
task_id, strategy, answer, input_tokens, output_tokens,
cache_read_tokens, cache_write_tokens, api_calls, latency_ms, cost_eur
strategies.py — only the baseline strategy for now:
Anthropic API call, full context included, no optimization
Uses Anthropic's native web_search tool
tasks.py — function load_gaia_sample() that loads tasks/gaia_sample.json
run.py — command-line interface:
   uv run run.py --strategy baseline --limit 1

Runs the first task, prints the result clearly.

Test: When this works with one task and Sami can see the token count and cost,
Phase 1 is done. Do not continue before this.

Phase 2: GAIA Data Loading

Goal: 24 GAIA tasks saved to tasks/gaia_sample.json.

Write a separate script scripts/download_gaia.py (run once):

Load GAIA validation set from HuggingFace (gaia-benchmark/GAIA)
Filter out tasks with attachments — keep only text-based ones
Stratified random sample: 12 Level 1, 8 Level 2, 4 Level 3
random_state=42 to ensure reproducibility
Save as JSON and print a summary

Requires a HuggingFace account and acceptance of GAIA's access terms.

Phase 3: Runs Across Multiple Tasks

Goal: all 24 tasks run with baseline, results in a JSONL file.

Extend run.py:

Arguments: --strategy, --tasks, --repeats (default 1), --limit, --max-cost-eur (default 5)
Writes results to the file immediately after each run (does not wait until the end)
Checkpointing: when starting, check what has already been done, continue from there
Cost tracking: stops gracefully if --max-cost-eur is exceeded
Progress bar (tqdm) and final summary (how many, how much, duration)

Test: uv run run.py --strategy baseline --repeats 1 --max-cost-eur 3 runs all
24 tasks and produces results/{timestamp}/run.jsonl.

Phase 4: Strategies One at a Time

Goal: each strategy added and tested separately.

Add to strategies.py one at a time in this order:

prompt_caching — the easiest, an Anthropic native feature. Mark the
system prompt and tool definitions with the cache_control parameter.
model_routing — Haiku first to assess the task, Sonnet for reasoning.
Simple: if Haiku is confident (e.g. confidence token or heuristic), return it.
Otherwise escalate.
context_compression — use Anthropic's context editing or heuristic
pruning. Start with the simplest: keep the last N messages.
context_isolation — orchestrator agent that divides the task among
subagents. Each subagent receives only its own task description, not the
entire history.

After each one, test with 3 tasks (--limit 3) and compare to the baseline results.

Phase 5: Success Evaluation

Goal: each run gets a success: true/false field.

Add a function evaluate_answer(agent_answer, ground_truth) to metrics.py:

Normalize both (whitespace, capitalization)
GAIA's own logic: quasi-exact string match
Return a boolean

Use GAIA's original scoring function if possible.
A success field is added to the results JSONL.

Phase 6: Aggregation and Pareto Analysis

Goal: analyze.py script that plots the Pareto frontier.

A simple Jupyter notebook or script:

Read all JSONL files
Calculate per strategy: mean(cost_eur), success_rate, cost_per_success
Plot scatter: x-axis cost per task, y-axis success rate
Highlight points on the Pareto frontier
Save as an image and print a table
Cost Calculation

Anthropic prices (per million tokens, USD, verify current):

Claude Sonnet 4.5: input $3, output $15, cache write $3.75, cache read $0.30
Claude Haiku 4.5: input $1, output $5, cache write $1.25, cache read $0.10

Convert to euros with a multiplier (e.g., 0.92, update as needed).

Safety
Always the --max-cost-eur argument. Never run without a cost cap.
.env never in Git. .gitignore right from the start.
Spend limit in the Anthropic console (Settings → Spend Limits, e.g. €30/month).
Working Style
Build one phase at a time. Don't jump ahead.
After each phase, commit to Git: "Phase N: [what was completed]".
Always test with a small --limit before a large run.
If something doesn't work, don't try to fix many things at once. Debug one.
What NOT to Do
No web interface
No database (JSONL is enough)
No Docker container
No CI/CD
No library packaging (pip install .)
No type checking (mypy) unless a bug forces it
No automated tests unless a bug forces it
Sami Returns Here When...

...Phase 1 is done and he has seen one GAIA task run through with the baseline.
Then he comments on what to change and we move to Phase 2.