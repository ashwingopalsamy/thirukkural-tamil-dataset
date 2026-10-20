"""Scoring for the KuralBench-lite lm-eval tasks: tkcore.kuralbench.score, letters only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tkcore.kuralbench import score  # noqa: E402


def only_quote(dataset):
    return dataset.filter(lambda d: d["task"] == "quote_by_number")


def only_complete(dataset):
    return dataset.filter(lambda d: d["task"] == "complete_second_line")


def process_results(doc, results):
    s = score(results[0], doc["target_ta"])
    return {"letters_match": float(s["letters_match"]), "letter_similarity": s["similarity"]}
