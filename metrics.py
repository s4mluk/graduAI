"""Cost calculation and answer evaluation (GAIA scoring)."""

import re
import string

from config import EUR_PER_USD, PRICES_USD


def compute_cost_eur(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> float:
    """Cost of one run in euros, from token counts and per-model prices."""
    p = PRICES_USD[model]
    usd = (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_read_tokens * p["cache_read"]
        + cache_write_tokens * p["cache_write"]
    ) / 1_000_000
    return usd * EUR_PER_USD


# --------------------------------------------------------------------------
# GAIA answer scoring
#
# Faithful reimplementation of the official GAIA `question_scorer`: a
# quasi-exact match with dedicated handling for numbers, comma/semicolon lists,
# and plain strings. Source: the gaia-benchmark scorer.
# --------------------------------------------------------------------------


def _is_float(x) -> bool:
    try:
        float(x)
        return True
    except (ValueError, TypeError):
        return False


def _normalize_number(s: str) -> float:
    for ch in ("$", "%", ","):
        s = s.replace(ch, "")
    try:
        return float(s)
    except ValueError:
        return float("inf")


def _normalize_str(s: str, remove_punct: bool = True) -> str:
    s = re.sub(r"\s", "", s).lower()  # drop all whitespace, lowercase
    if remove_punct:
        s = s.translate(str.maketrans("", "", string.punctuation))
    return s


def _split(s: str) -> list[str]:
    return re.split(r"[,;]", s)


def question_scorer(model_answer: str, ground_truth: str) -> bool:
    """GAIA's quasi-exact match. True if model_answer matches ground_truth."""
    gt = str(ground_truth).strip()
    ma = str(model_answer).strip()

    # Ground truth is a number.
    if _is_float(gt):
        return _normalize_number(ma) == float(gt)

    # Ground truth is a list (comma/semicolon separated).
    if any(c in gt for c in (",", ";")):
        gt_elems = _split(gt)
        ma_elems = _split(ma)
        if len(gt_elems) != len(ma_elems):
            return False
        for m, g in zip(ma_elems, gt_elems):
            m, g = m.strip(), g.strip()
            if _is_float(g):
                if _normalize_number(m) != float(g):
                    return False
            elif _normalize_str(m, remove_punct=False) != _normalize_str(
                g, remove_punct=False
            ):
                return False
        return True

    # Ground truth is a plain string.
    return _normalize_str(ma) == _normalize_str(gt)


def extract_final_answer(text: str) -> str:
    """Pull the text after the last 'FINAL ANSWER:' marker; fall back to the
    whole stripped text if the marker is absent."""
    marker = "FINAL ANSWER:"
    idx = text.rfind(marker)
    if idx != -1:
        return text[idx + len(marker):].strip()
    return text.strip()


def evaluate_answer(agent_answer: str, ground_truth: str) -> bool:
    """True if the agent's final answer matches the GAIA ground truth."""
    return question_scorer(extract_final_answer(agent_answer), ground_truth)
