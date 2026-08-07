"""GAIA task loading."""

import json
from pathlib import Path

TASKS_FILE = Path(__file__).parent / "tasks" / "gaia_sample.json"


def load_gaia_sample() -> list[dict]:
    """Load the sample of GAIA tasks from tasks/gaia_sample.json.

    Each task is a dict with keys: task_id, question, level, answer.
    """
    with open(TASKS_FILE, encoding="utf-8") as f:
        return json.load(f)
