"""Merkle proofs, the agent tools and their interfaces, KuralBench-lite and the token-cost evidence."""
import asyncio
import json
import re
import sqlite3
import threading
import urllib.request

import pytest
from jsonschema import Draft202012Validator

from tkcore import REPORTS, agent_tools as at, kuralbench, merkle
from tkcore.release import META, build_release, build_tables, kurals_root, merkle_roots
from tkcore.signature import compare_key


@pytest.fixture(scope="module")
def tables():
    return build_tables()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build_release(tmp_path_factory.mktemp("hf"))


def _proof_ok(k, p, roots, text=None, number=None, letters=False):
    leaf = merkle.leaf_bytes(k["id"], number or k["number"], k["text_ta"] if text is None else text, letters)
    path = p["letters_path" if letters else "exact_path"]
    return merkle.verify(p["leaf_index"], p["tree_size"], leaf, [bytes.fromhex(h) for h in path],
                         bytes.fromhex(roots["letters" if letters else "exact"]))


# ---------------------------------------------------------------- Merkle

def test_proofs_file_is_current():
    assert merkle.PROOFS.read_text(encoding="utf-8") == merkle.render()


def test_card_and_manifest_state_the_same_roots(built, tables):
    r, m, card = merkle_roots(tables), built["manifest"], built["card"]
    assert m["merkle_exact_root_sha256"] == r["exact"] and m["merkle_letters_root_sha256"] == r["letters"]
    assert f"its root is `{r['exact']}`" in card and f"its root is `{r['letters']}`" in card
    assert merkle.roots(merkle.load_core()) == r  # data/core and the kurals config give the same tree


def test_every_proof_verifies_and_tampering_fails(tables):
    r = merkle.roots(tables["kurals"])
    ks, ps = tables["kurals"], {p["kural_id"]: p for p in tables["merkle_proofs"]}
    assert all(_proof_ok(k, ps[k["id"]], r) and _proof_ok(k, ps[k["id"]], r, letters=True) for k in ks)
    k, p, other = ks[390], ps[ks[390]["id"]], ps[ks[391]["id"]]
    text = k["text_ta"]
    assert not _proof_ok(k, p, r, text=text[:-2] + text[-1])        # one letter dropped
    assert not _proof_ok(k, p, r, text=text + " ")                  # exact tree: a trailing space counts
    assert not _proof_ok(k, p, r, number=k["number"] + 1)           # the wrong number
    assert not _proof_ok(k, other, r)                               # another kural's proof
    loose = text.replace("\n", "  ").rstrip(".")
    assert _proof_ok(k, p, r, text=loose, letters=True)             # letters tree: spacing and punctuation do not
    assert not _proof_ok(k, p, r, text=loose[:-2] + loose[-1], letters=True)
    assert max(len(p["exact_path"]) for p in ps.values()) <= 11


def test_card_verifier_snippet_runs(built, tables):
    """The verifier printed in the card works as printed."""
    code = re.search(r"### Prove a quote offline.*?```python\n(.*?)```", built["card"], re.S).group(1)
    ns = {}
    exec(code, ns)
    root, ps = merkle_roots(tables)["exact"], {p["kural_id"]: p for p in tables["merkle_proofs"]}
    assert all(ns["verify"](k["number"], k["text_ta"], ps[k["id"]], root) for k in tables["kurals"])
    k = tables["kurals"][665]
    assert not ns["verify"](k["number"], k["text_ta"].replace("எய்துவர்", "எய்து"), ps[k["id"]], root)


# ---------------------------------------------------------------- the tools

def _schemas():
    return {n: Draft202012Validator(o) for n, (_, o, _) in at.schemas().items()}


def _cases(tables):
    """Inputs from the data itself: canonical texts, re-spaced texts, attested rejected readings, one dropped letter."""
    cs = []
    for k in [tables["kurals"][i] for i in (0, 390, 665, 1329)]:
        t = k["text_ta"]
        cs += [("get_kural", {"number": k["number"]}, lambda r, k=k: r["id"] == k["id"] and r["proof"]["verified"]),
               ("verify_quote", {"quote": t}, lambda r: r["verdict"] == "exact" and r["kural"]["proof"]["verified"]),
               ("verify_quote", {"quote": t.replace("\n", "  ").rstrip(".")},
                lambda r: r["verdict"] == "same_letters" and r["kural"]["proof"]["tree"] == "letters" and r["kural"]["proof"]["verified"]),
               ("verify_quote", {"quote": t[:5] + t[6:], "number": k["number"]}, lambda r: r["verdict"] == "misquote" and r["diff"]),
               ("find_kural", {"quote": t.split("\n")[0]}, lambda r, k=k: r["candidates"][0]["id"] == k["id"])]
    for a in [a for a in tables["variants_atlas"] if a["status"].startswith("rejected")][:10]:
        cs.append(("verify_quote", {"quote": a["text"]},
                   lambda r, a=a: r["verdict"] == "known_reading" and r["kural"]["id"] == a["kural_id"]))
    cs += [("verify_quote", {"quote": "This is not a kural at all"}, lambda r: r["verdict"] == "not_found"),
           ("search_english", {"query": "rain"}, lambda r: any(11 <= c["number"] <= 20 for c in r["candidates"])),
           ("get_kural", {"number": 1, "layers": ["parimelazhagar_ta"]},
            lambda r: [t["config"] for t in r["translations"]] == ["parimelazhagar_ta"])]
    return cs


def test_tools_direct(tables):
    v = _schemas()
    for name, args, ok in _cases(tables):
        res = at.call(name, args)
        v[name].validate(res)
        assert ok(res), (name, args, res.get("verdict"))


def test_verify_quote_never_names_the_wrong_kural(tables):
    """Every reading any witness carries resolves to its own kural, with no number given."""
    wrong, verdicts = [], set()
    for a in tables["variants_atlas"] + tables["variants_atlas_sa"]:
        r = at.verify_quote(a["text"])
        verdicts.add(r.verdict)
        if r.kural and r.kural.id != a["kural_id"]:
            wrong.append(a["reading_id"])
        if a["status"] == "canonical":
            assert r.verdict == "exact", a["reading_id"]
    assert not wrong and {"exact", "same_letters", "known_reading"} <= verdicts


def test_withheld_layer_rows_are_not_served(tables):
    gone = [(n, r["kural_id"]) for n in at.LAYERS for r in tables[n] if r["text"] is None]
    assert gone
    rows = sqlite3.connect(at.DB_PATH).execute("SELECT config, kural_id FROM translations").fetchall()
    assert not set(gone) & set(rows)


def test_interfaces_are_current_and_valid():
    assert at.stale() == []
    from openapi_spec_validator import validate
    validate(json.loads((at.AGENTS / "openapi.json").read_text(encoding="utf-8")))
    for p in (at.AGENTS / "schemas").glob("*.json"):
        Draft202012Validator.check_schema(json.loads(p.read_text(encoding="utf-8")))

    def closed(o):  # OpenAI strict mode: every object closed, every property required
        if isinstance(o, dict):
            if o.get("type") == "object" and "properties" in o:
                assert o["additionalProperties"] is False and set(o["required"]) == set(o["properties"])
            [closed(x) for x in o.values()]
        elif isinstance(o, list):
            [closed(x) for x in o]
    for t in json.loads((at.AGENTS / "tools.openai.json").read_text(encoding="utf-8")):
        closed(t["parameters"])
    names = {t["name"] for t in json.loads((at.AGENTS / "tools.json").read_text(encoding="utf-8"))}
    assert names == set(at.TOOLS)


def test_mcp_server(tables):
    from mcp import Client
    from tkcore.mcp_server import server
    v = _schemas()

    async def go():
        async with Client(server) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert set(tools) == set(at.TOOLS) and all(t.output_schema for t in tools.values())
            assert "எண்ணிய" in (await c.read_resource("kural://666")).contents[0].text
            for name, args, ok in _cases(tables):
                r = await c.call_tool(name, args)
                assert not r.is_error, (name, args, r.content)
                v[name].validate(r.structured_content)
                assert ok(r.structured_content), (name, args)
    asyncio.run(go())


def test_http_server(tables):
    srv = at.server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        v = _schemas()
        for name, args, ok in _cases(tables):
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/v1/{name}", json.dumps(args).encode(),
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                res = json.load(resp)
            v[name].validate(res)
            assert ok(res), (name, args)
    finally:
        srv.shutdown()


# ---------------------------------------------------------------- KuralBench-lite and token cost

def test_kuralbench_items(tables):
    assert kuralbench.OUT.read_text(encoding="utf-8") == kuralbench.render()
    rows = tables["kuralbench_lite"]
    assert len(rows) == 2660 and all(r["canary"] == META["canary"] for r in rows)
    text = {k["id"]: k for k in tables["kurals"]}
    for r in rows:
        want = text[r["kural_id"]]["text_ta"] if r["task"] == "quote_by_number" else text[r["kural_id"]]["lines_ta"][1]
        assert r["target_ta"] == want


def test_kuralbench_scorer(tables):
    rows = tables["kuralbench_lite"]
    assert all(kuralbench.score(" " + r["target_ta"].replace("\n", " ").rstrip(".") + " ", r["target_ta"])["letters_match"]
               for r in rows)
    # another item's answer fails, except where two kurals share a second line (21 pairs do, e.g. 311 and 312)
    shifted = [kuralbench.score(rows[i - 1]["target_ta"], r["target_ta"])["letters_match"] for i, r in enumerate(rows)]
    same = [compare_key(rows[i - 1]["target_ta"]) == compare_key(r["target_ta"]) for i, r in enumerate(rows)]
    assert shifted == same and sum(same) == 8
    t = rows[0]["target_ta"]
    assert not kuralbench.score(t[:4] + t[5:], t)["letters_match"]
    assert compare_key(t) == compare_key(t.replace(" ", ""))


def test_token_cost_is_measured_on_this_text(built, tables):
    doc = json.loads((REPORTS / "tokenizer_cost.json").read_text(encoding="utf-8"))
    assert doc["measured_on"]["kurals_root_sha256"] == kurals_root(tables)
    assert len(doc["tokenizers"]) == 7
    for r in doc["tokenizers"]:
        assert f"| {r['kural_ta_tokens_mean']} | {r['kural_ta_tokens_max']} |" in built["card"]
