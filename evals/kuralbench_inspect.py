"""KuralBench-lite for Inspect AI. Scoring is tkcore.kuralbench.score: letters only, against the canonical text, so no
model judges an answer.

  inspect eval evals/kuralbench_inspect.py@kural_quote --model <provider/model>
  inspect eval evals/kuralbench_inspect.py@kural_complete --model <provider/model>

Items come from data/tasks/kuralbench_lite.jsonl in this repository, or from the Hugging Face config with
-T source=hf once the dataset is public.
"""
import json
import sys
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate, system_message

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tkcore.kuralbench import OUT, SYSTEM, score  # noqa: E402

HF_REPO = json.loads((ROOT / "release" / "release.json").read_text(encoding="utf-8"))["hf_repo"]


def _rows(source: str) -> list[dict]:
    if source == "hf":
        from datasets import load_dataset
        return list(load_dataset(HF_REPO, "kuralbench_lite", split="train"))
    return [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]


def _dataset(kind: str, source: str, numbers: list[int] | None) -> MemoryDataset:
    rows = [r for r in _rows(source) if r["task"] == kind and (numbers is None or r["kural_number"] in numbers)]
    return MemoryDataset([Sample(id=r["task_id"], input=r["prompt"], target=r["target_ta"],
                                 metadata={"kural_number": r["kural_number"], "canary": r["canary"]}) for r in rows],
                         name=f"kuralbench_lite_{kind}")


@scorer(metrics=[accuracy(), stderr()])
def letters_match():
    """CORRECT when the answer has exactly the target's letters."""
    async def run(state: TaskState, target: Target) -> Score:
        out = state.output.completion
        return Score(value=CORRECT if score(out, target.text)["letters_match"] else INCORRECT, answer=out.strip())
    return run


@scorer(metrics=[mean()])
def letter_similarity():
    """Letters-only similarity to the target, 0 to 1, so near misses show as near misses."""
    async def run(state: TaskState, target: Target) -> Score:
        return Score(value=score(state.output.completion, target.text)["similarity"])
    return run


def _task(kind: str, source: str, numbers):
    return Task(dataset=_dataset(kind, source, numbers), solver=[system_message(SYSTEM), generate()],
                scorer=[letters_match(), letter_similarity()])


@task
def kural_quote(source: str = "local", numbers: list[int] | None = None):
    """Quote a kural from its number."""
    return _task("quote_by_number", source, numbers)


@task
def kural_complete(source: str = "local", numbers: list[int] | None = None):
    """Give a kural's second line from its first."""
    return _task("complete_second_line", source, numbers)
