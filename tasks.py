"""GAIA task loading.

The task list (tasks/gaia_sample.json) holds no answers: GAIA asks that
ground-truth answers are not published in crawlable form. They are fetched at
runtime from the gated HF dataset `gaia-benchmark/GAIA` (accept its terms and
run `hf auth login` once) and matched by task_id.
"""

import json
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

TASKS_FILE = Path(__file__).parent / "tasks" / "gaia_sample.json"


def _load_answers() -> dict[str, str]:
    """task_id -> ground-truth answer, from the 2023 validation split."""
    path = hf_hub_download(
        repo_id="gaia-benchmark/GAIA",
        repo_type="dataset",
        filename="2023/validation/metadata.parquet",
    )
    df = pd.read_parquet(path)
    return dict(zip(df["task_id"], df["Final answer"]))


def load_gaia_sample() -> list[dict]:
    """Load the task sample, with ground-truth answers attached at runtime.

    Each task is a dict with keys: task_id, question, level, answer.
    """
    with open(TASKS_FILE, encoding="utf-8") as f:
        tasks = json.load(f)
    answers = _load_answers()
    missing = [t["task_id"] for t in tasks if t["task_id"] not in answers]
    if missing:
        raise KeyError(f"task_ids not in GAIA validation split: {missing}")
    return [{**t, "answer": answers[t["task_id"]]} for t in tasks]
