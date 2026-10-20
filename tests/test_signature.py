"""Invariants of the signature layers (data/signature/*.jsonl) against the committed core."""
import hashlib
import json

import pytest

from tkcore import DATA_CORE, ROOT
from tkcore.signature import compare_key

SIG = ROOT / "data" / "signature"


def _rows(name):
    p = SIG / f"{name}.jsonl"
    if not p.exists():
        pytest.skip(f"{p} not built")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def core():
    return {json.loads(l)["id"]: json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()}


def test_atlas_lists_exactly_one_canonical_reading_per_kural(core):
    rows = _rows("variants_atlas")
    canon = [r for r in rows if r["status"] == "canonical"]
    assert sorted(r["kural_id"] for r in canon) == sorted(core)
    for r in canon:
        assert r["text"] == "\n".join(core[r["kural_id"]]["lines_ta"])
        assert r["text_sha256"] == hashlib.sha256(r["text"].encode()).hexdigest()
    assert all(r["sources"] for r in rows)


def test_quote_keys_match_core(core):
    rows = _rows("quote_keys")
    assert len(rows) == 1330
    for r in rows:
        lines = core[r["kural_id"]]["lines_ta"]
        assert r["text_sha256"] == hashlib.sha256("\n".join(lines).encode()).hexdigest()
        assert r["compare_key"] == compare_key(" ".join(lines))
        assert (r["line1_key"], r["line2_key"]) == (compare_key(lines[0]), compare_key(lines[1]))


def test_compare_key_ignores_spacing_punctuation_and_joining():
    assert compare_key("அடக்கம் உடைமை") == compare_key("அடக்கமுடைமை")
    assert compare_key("கெளவை") == compare_key("கௌவை")
    assert compare_key("உலகு.") == compare_key("உலகு")


def test_echo_edges_cite_words_present_in_both(core):
    keys = {kid: {compare_key(w) for ln in k["lines_ta"] for w in ln.replace(".", " ").split()} for kid, k in core.items()}
    for r in _rows("echo_graph"):
        if r["kind"] == "shared rare word":
            assert r["shared_keys"] and all(t in keys[r["source"]] and t in keys[r["target"]] for t in r["shared_keys"])


def test_task_answers_come_from_the_core(core):
    for t in _rows("tasks"):
        lines = core[t["kural_id"]]["lines_ta"]
        if t["type"] == "complete_second_line":
            assert t["prompt_ta"] == lines[0] and t["answer"] == lines[1]
        if t["type"] == "verify_quote" and t["answer"] == "exact":
            assert t["prompt_ta"] == "\n".join(lines)
        if t["type"] == "verify_quote" and t["answer"] == "altered":
            assert compare_key(t["prompt_ta"]) != compare_key(" ".join(lines))
        if t["type"] == "identify_chapter":
            assert t["answer"] in t["choices"] and len(set(t["choices"])) == 4


def test_agent_cards_are_valid_json_with_core_text(core):
    rows = _rows("agent_card")
    assert len(rows) == 1330
    for r in rows:
        c = json.loads(r["card"])
        assert c["text"] == "\n".join(core[r["kural_id"]]["lines_ta"]) and c["license"] == "CC0-1.0"
