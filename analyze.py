"""Aggregate results and plot the cost/quality Pareto frontier.

Reads every results/*/run.jsonl, groups by strategy, and reports per strategy:
mean cost, success rate, and cost per successful task. Plots success rate vs.
cost per task and highlights the Pareto frontier (cheap + accurate).

    uv run analyze.py

No API calls — works on whatever results already exist.
"""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # write a file, no interactive window
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).parent / "results"
OUT_IMG = RESULTS_DIR / "pareto.png"


def load_all_runs() -> list[dict]:
    """Read every results/*/run.jsonl into one list of run dicts."""
    runs = []
    for run_file in sorted(RESULTS_DIR.glob("*/run.jsonl")):
        with open(run_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))
    return runs


def summarize(runs: list[dict]) -> dict[str, dict]:
    """Per strategy: n runs, mean cost, success rate, cost per success."""
    by_strategy = defaultdict(list)
    for r in runs:
        by_strategy[r["strategy"]].append(r)

    summary = {}
    for strat, rs in by_strategy.items():
        n = len(rs)
        total_cost = sum(r["cost_eur"] for r in rs)
        n_success = sum(1 for r in rs if r.get("success"))
        summary[strat] = {
            "n": n,
            "mean_cost": total_cost / n,
            "success_rate": n_success / n,
            "n_success": n_success,
            # cost per successful task; inf if nothing succeeded
            "cost_per_success": (total_cost / n_success) if n_success else float("inf"),
        }
    return summary


def pareto_frontier(summary: dict[str, dict]) -> set[str]:
    """Strategies not dominated by another: no other strategy is both at least
    as cheap AND at least as accurate (and strictly better on one)."""
    frontier = set()
    for a, sa in summary.items():
        dominated = False
        for b, sb in summary.items():
            if a == b:
                continue
            not_worse = (
                sb["mean_cost"] <= sa["mean_cost"]
                and sb["success_rate"] >= sa["success_rate"]
            )
            strictly_better = (
                sb["mean_cost"] < sa["mean_cost"]
                or sb["success_rate"] > sa["success_rate"]
            )
            if not_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.add(a)
    return frontier


def print_table(summary: dict[str, dict], frontier: set[str]) -> None:
    print(f"\n{'strategy':<22}{'n':>4}{'mean €':>10}{'success':>10}"
          f"{'€/success':>12}  pareto")
    print("-" * 70)
    for strat in sorted(summary, key=lambda s: summary[s]["mean_cost"]):
        s = summary[strat]
        cps = "inf" if s["cost_per_success"] == float("inf") else f"{s['cost_per_success']:.4f}"
        star = " *" if strat in frontier else ""
        print(
            f"{strat:<22}{s['n']:>4}{s['mean_cost']:>10.4f}"
            f"{s['success_rate']:>9.0%}{cps:>12}{star}"
        )
    print("\n* = on the Pareto frontier (not dominated on cost AND success)")


def plot(summary: dict[str, dict], frontier: set[str]) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    for strat, s in summary.items():
        on_front = strat in frontier
        ax.scatter(
            s["mean_cost"],
            s["success_rate"],
            s=140,
            color="tab:green" if on_front else "tab:gray",
            edgecolors="black",
            zorder=3,
        )
        ax.annotate(
            f"{strat}\n(n={s['n']})",
            (s["mean_cost"], s["success_rate"]),
            textcoords="offset points",
            xytext=(8, 6),
            fontsize=9,
        )

    # Connect frontier points (sorted by cost) to draw the frontier line.
    front_pts = sorted(
        (summary[s]["mean_cost"], summary[s]["success_rate"]) for s in frontier
    )
    if len(front_pts) > 1:
        xs, ys = zip(*front_pts)
        ax.plot(xs, ys, "--", color="tab:green", zorder=2, label="Pareto frontier")
        ax.legend()

    ax.set_xlabel("Mean cost per task (€)")
    ax.set_ylabel("Success rate")
    ax.set_title("Cost vs. quality by strategy (GAIA testbench)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_IMG, dpi=120)
    print(f"\nSaved plot -> {OUT_IMG}")


def main() -> None:
    runs = load_all_runs()
    if not runs:
        print("No results found under results/*/run.jsonl. Run some tasks first.")
        return
    print(f"Loaded {len(runs)} runs from results/*/run.jsonl")
    summary = summarize(runs)
    frontier = pareto_frontier(summary)
    print_table(summary, frontier)
    plot(summary, frontier)


if __name__ == "__main__":
    main()
