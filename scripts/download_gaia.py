"""Run once: download a stratified sample of text-only GAIA validation tasks.

Requires a HuggingFace account, acceptance of GAIA's terms, and a local login
(`hf auth login`, or huggingface_hub.login(token=...)).

Loads the validation split (the one with answers), keeps only text-based tasks
(no attachments), takes a stratified random sample of 12 level-1, 8 level-2 and
4 level-3 tasks (random_state=42 for reproducibility), and writes
tasks/gaia_sample.json in the format tasks.py expects.

    uv run scripts/download_gaia.py
"""

import json
from collections import Counter
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

SAMPLE_PER_LEVEL = {1: 12, 2: 8, 3: 4}
RANDOM_STATE = 42
OUT = Path(__file__).resolve().parent.parent / "tasks" / "gaia_sample.json"


def main() -> None:
    # Download only the validation metadata (not the ~100 attachment files).
    path = hf_hub_download(
        repo_id="gaia-benchmark/GAIA",
        repo_type="dataset",
        filename="2023/validation/metadata.parquet",
    )
    df = pd.read_parquet(path)
    df["Level"] = df["Level"].astype(int)
    print(f"Loaded {len(df)} validation tasks.")

    # Keep only text-based tasks (those without an attached file).
    text_only = df[df["file_name"].fillna("") == ""].copy()
    print(f"Text-only tasks (no attachments): {len(text_only)}")

    tasks: list[dict] = []
    for level, n in SAMPLE_PER_LEVEL.items():
        pool = text_only[text_only["Level"] == level]
        take = min(n, len(pool))
        if take < n:
            print(f"  WARNING: level {level} has only {len(pool)} tasks, wanted {n}")
        chosen = pool.sample(n=take, random_state=RANDOM_STATE)
        for _, row in chosen.iterrows():
            tasks.append(
                {
                    "task_id": row["task_id"],
                    "question": row["Question"],
                    "level": int(row["Level"]),
                    "answer": row["Final answer"],
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

    by_level = Counter(t["level"] for t in tasks)
    print(f"\nSaved {len(tasks)} tasks -> {OUT}")
    for lvl in sorted(by_level):
        print(f"  level {lvl}: {by_level[lvl]}")


if __name__ == "__main__":
    main()
