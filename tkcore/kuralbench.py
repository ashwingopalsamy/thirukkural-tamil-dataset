"""KuralBench-lite: can a model quote a kural exactly? Two tasks over all 1,330 kurals, built by fixed templates from
the verified core, and a deterministic scorer. No model writes or judges anything.

  quote_by_number       "Quote Thirukkural N exactly." -> the kural's text
  complete_second_line  the first line -> the second line

The scorer compares letters only (tkcore.signature.compare_key), so spacing, punctuation and how words are joined do
not count, and one wrong letter does. Every row carries the release canary.

  python -m tkcore.kuralbench            data/tasks/kuralbench_lite.jsonl (the kuralbench_lite config)
  python -m tkcore.kuralbench --check    fail if that file differs from what data/core gives

Harness configs that use this scorer: evals/kuralbench_inspect.py (Inspect) and evals/lm_eval/ (lm-evaluation-harness).
"""
import argparse
import difflib
import json
import sys

from . import DATA_CORE, ROOT
from .signature import compare_key

OUT = ROOT / "data" / "tasks" / "kuralbench_lite.jsonl"
TASKS = ("quote_by_number", "complete_second_line")
SYSTEM = "Reply with the Tamil text only, in Tamil script, with no translation, transliteration or commentary."
PROMPTS = {
    "quote_by_number": "Quote Thirukkural {n} exactly.",
    "complete_second_line": "Give the second line of this Thirukkural, exactly as printed:\n{line1}",
}


def _canary() -> str:
    return json.loads((ROOT / "release" / "release.json").read_text(encoding="utf-8"))["canary"]


def items() -> list[dict]:
    core = [json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    canary, rows = _canary(), []
    for task in TASKS:
        for k in sorted(core, key=lambda k: k["number"]):
            line1, line2 = k["lines_ta"]
            rows.append({"task_id": f"{task}:{k['id']}", "task": task, "kural_id": k["id"], "kural_number": k["number"],
                         "prompt": PROMPTS[task].format(n=k["number"], line1=line1),
                         "target_ta": "\n".join(k["lines_ta"]) if task == "quote_by_number" else line2,
                         "canary": canary})
    return rows


def score(answer: str, target: str) -> dict:
    """letters_match: the answer has exactly the target's letters. similarity: letters-only ratio, 0 to 1."""
    a, t = compare_key(answer.strip()), compare_key(target)
    return {"letters_match": a == t, "similarity": round(difflib.SequenceMatcher(None, a, t, autojunk=False).ratio(), 4)}


def render() -> str:
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in items())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"stale: {OUT.relative_to(ROOT)}; run python -m tkcore.kuralbench")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {text.count(chr(10))} items")


if __name__ == "__main__":
    main()
