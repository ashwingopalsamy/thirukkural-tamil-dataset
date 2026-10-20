# KuralBench-lite

Two tasks over all 1,330 kurals, from the `kuralbench_lite` config: quote a kural from its number, and give its second line from its first. `tkcore.kuralbench.score` marks an answer right when it has exactly the target's letters. Spacing, punctuation and how words are joined are ignored, and one wrong letter fails. No model judges.

```sh
pip install -r requirements.txt -r evals/requirements.txt
inspect eval evals/kuralbench_inspect.py@kural_quote --model <provider/model>
inspect eval evals/kuralbench_inspect.py@kural_complete --model <provider/model>
lm_eval --include_path evals/lm_eval --tasks kuralbench_lite --model <...>
```

Run from the repository root. Every item carries the canary string from `release/release.json`. Keep it with any copy, and do not train on these items.
