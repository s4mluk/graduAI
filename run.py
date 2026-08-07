"""Command-line runner.

Runs many tasks with a strategy, writes each result to a JSONL file immediately
(with a GAIA success:true/false field), resumes interrupted runs, and stops
gracefully at a cost cap.

Examples:
    uv run run.py --strategy baseline --limit 1
    uv run run.py --strategy baseline --repeats 1 --max-cost-eur 3
    uv run run.py --strategy baseline --resume results/20260731_120000

Results are written to results/{timestamp}/run.jsonl, one JSON object per line.
"""

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from agent import run_agent
from metrics import evaluate_answer, extract_final_answer
from tasks import load_gaia_sample

RESULTS_DIR = Path(__file__).parent / "results"


def load_progress(run_file: Path) -> tuple[set, float]:
    """Read an existing run.jsonl: which (task, strategy, repeat) are done and
    how much has already been spent. Used for checkpointing and the cost cap."""
    done: set = set()
    spent = 0.0
    if run_file.exists():
        with open(run_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                done.add((r["task_id"], r["strategy"], r["repeat"]))
                spent += r.get("cost_eur", 0.0)
    return done, spent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GAIA tasks with a strategy.")
    parser.add_argument("--strategy", default="baseline", help="strategy name")
    parser.add_argument(
        "--tasks",
        default=None,
        help="comma-separated task_ids to run a subset (default: all)",
    )
    parser.add_argument("--repeats", type=int, default=1, help="runs per task")
    parser.add_argument("--limit", type=int, default=None, help="cap number of tasks")
    parser.add_argument(
        "--max-cost-eur",
        type=float,
        default=5.0,
        help="stop before total cost exceeds this (safety cap)",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="existing results dir to continue instead of starting fresh",
    )
    args = parser.parse_args()

    # Select tasks.
    tasks = load_gaia_sample()
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",")}
        tasks = [t for t in tasks if t["task_id"] in wanted]
    if args.limit is not None:
        tasks = tasks[: args.limit]

    # Where to write results.
    if args.resume:
        out_dir = Path(args.resume)
    else:
        out_dir = RESULTS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    run_file = out_dir / "run.jsonl"

    # Checkpointing: skip work already recorded in this file.
    done, total_cost = load_progress(run_file)

    work = [
        (task, rep)
        for rep in range(args.repeats)
        for task in tasks
        if (task["task_id"], args.strategy, rep) not in done
    ]

    planned = len(tasks) * args.repeats
    print(f"Results -> {run_file}")
    print(
        f"Tasks: {len(tasks)} x {args.repeats} repeats = {planned} runs; "
        f"{len(done)} already done, {len(work)} to run."
    )
    print(f"Cost so far: €{total_cost:.4f} | cost cap: €{args.max_cost_eur}\n")

    if not work:
        print("Nothing to run.")
        return

    start = time.perf_counter()
    ran = 0
    correct = 0
    stopped_for_cost = False

    with open(run_file, "a", encoding="utf-8") as f:
        for task, rep in tqdm(work, desc="Running", unit="task"):
            if total_cost >= args.max_cost_eur:
                stopped_for_cost = True
                break

            try:
                result = run_agent(task, args.strategy)
            except Exception as e:  # keep going on a single-task failure
                tqdm.write(f"  ERROR {task['task_id'][:8]}: {e}")
                continue

            success = evaluate_answer(result.answer, task["answer"])

            row = asdict(result)
            row["repeat"] = rep
            row["success"] = success
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()  # write immediately, don't wait until the end

            total_cost += result.cost_eur
            ran += 1
            correct += int(success)
            mark = "OK " if success else "  X"
            tqdm.write(
                f"  {mark} [taso {task['level']}] {task['task_id'][:8]} "
                f"€{result.cost_eur:.4f}  "
                f"got={extract_final_answer(result.answer)!r} "
                f"want={task['answer']!r}"
            )

    duration = time.perf_counter() - start
    rate = f"{correct}/{ran}" if ran else "0/0"
    print(
        f"\nDone. Ran {ran} tasks in {duration:.0f}s. "
        f"Correct: {rate}. Total cost €{total_cost:.4f}."
    )
    if stopped_for_cost:
        print(f"Stopped early: cost cap €{args.max_cost_eur} reached.")
    print(f"Results: {run_file}")


if __name__ == "__main__":
    main()
