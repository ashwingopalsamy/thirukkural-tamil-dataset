"""Signature layers v0.1: deterministic, sourced, rule-based tables built on the verified core. No model output and
no new Tamil: every string is either copied from a cited witness or computed by a stated rule.

  variants_atlas  every attested reading of each kural, with its sources, status and the ledger ruling
  quote_keys      hashes, spacing/punctuation/joining-insensitive comparison keys, citations, permalinks
  sound_index     letters, asai and seer patterns, monai, edukai, end rhyme (rule-based)
  echo_graph      kural-to-kural edges from shared rare words, each listing its shared words
  tasks           evaluation items with answer keys (line completion, chapter, quote verification, cloze)
  agent_card      one compact JSON string per kural for agent tool use

  python -m tkcore.signature     rebuilds quote_keys, echo_graph, tasks and agent_card from data/core, the ledger and
                                 the committed atlas; run it after a change of PERMALINK_BASE or of the canary
"""
import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict

from . import DATA_CORE, LAYERS, LEDGER, REPORTS, ROOT
from .ids import kural_id
from .prosody import attested_divisions, plain_reason, scan

OUT = ROOT / "data" / "signature"
# Base of the permalinks stored in quote_keys and agent_card: the site, which has one page per kural at kural/<n>/.
PERMALINK_BASE = "https://ashwingopalsamy.github.io/thirukkural-tamil-dataset"
# BIG-bench-style canary on every task row, so a model trained on this file can be detected (release/release.json)
CANARY = json.loads((ROOT / "release" / "release.json").read_text(encoding="utf-8")).get("canary")
SIGN = {"அ": "", "ஆ": "ா", "இ": "ி", "ஈ": "ீ", "உ": "ு", "ஊ": "ூ", "எ": "ெ", "ஏ": "ே", "ஐ": "ை", "ஒ": "ொ", "ஓ": "ோ", "ஔ": "ௌ"}
AU_SEQ = re.compile("ெள(?![ா-்ௗ])")


# ----------------------------------------------------------------------------- shared helpers
def nfc(s):
    return unicodedata.normalize("NFC", s)


def text_sha256(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def compare_key(text):
    """Spacing-, punctuation- and joining-insensitive key: NFC, கௌ written as U+0BCC, Tamil letters only, and a pulli
    consonant followed by a vowel letter written as consonant + vowel sign (how the prints join words)."""
    t = AU_SEQ.sub("ௌ", nfc(text))
    t = "".join(c for c in t if 0x0B80 <= ord(c) <= 0x0BFF)
    return re.sub("்([அஆஇஈஉஊஎஏஐஒஓஔ])", lambda m: SIGN[m.group(1)], t)


def words(lines):
    return [w for ln in lines for w in re.sub(r"[^஀-௿ ]", " ", ln).split()]


def load_core():
    rows = [json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()]
    adh = {json.loads(l)["number"]: json.loads(l) for l in (DATA_CORE / "adhikarams.jsonl").read_text(encoding="utf-8").splitlines()}
    div = [json.loads(l) for l in (DATA_CORE / "divisions.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows, adh, div


def ledger_by_subject():
    out = defaultdict(list)
    if LEDGER.exists():
        for l in LEDGER.read_text(encoding="utf-8").splitlines():
            e = json.loads(l)
            out[e["subject"]].append(e)
    return out


# ----------------------------------------------------------------------------- 2. quote_keys
def build_quote_keys(core, adh):
    base = PERMALINK_BASE
    rows = []
    for k in core:
        a, lines = adh[k["adhikaram_number"]], k["lines_ta"]
        first = words(lines[:1])
        rows.append({
            "kural_id": k["id"], "number": k["number"], "text_sha256": text_sha256(lines),
            "compare_key": compare_key(" ".join(lines)),
            "compare_key_sha256": hashlib.sha256(compare_key(" ".join(lines)).encode()).hexdigest(),
            "line1_key": compare_key(lines[0]), "line2_key": compare_key(lines[1]),
            "opening_key": compare_key(" ".join(first[:2])),
            "citation_ta": f"திருக்குறள் {k['number']} (அதிகாரம் {a['number']}: {a['name_ta']}, குறள் {k['position']})",
            "citation_en": f"Tirukkural {k['number']} (chapter {a['number']}"
                           + (f", {a['name_en']}" if a["name_en"] else "") + f", verse {k['position']})",
            "permalink": f"{base}/kural/{k['number']}/", "permalink_ta": f"{base}/kural/{k['number']}/",
            "permalink_en": f"{base}/kural/{k['number']}/", "base_url_is_placeholder": "example" in base})
    return rows


# ----------------------------------------------------------------------------- 4. echo_graph
def build_echo_graph(core, max_df=6, top_k=8):
    toks = {k["number"]: set(compare_key(w) for w in words(k["lines_ta"]) if len(compare_key(w)) >= 4) for k in core}
    df = Counter(t for s in toks.values() for t in s)
    idx = defaultdict(set)
    for n, s in toks.items():
        for t in s:
            if df[t] <= max_df:
                idx[t].add(n)
    rows = []
    for n, s in toks.items():
        score, shared = Counter(), defaultdict(list)
        for t in s:
            if df[t] > max_df:
                continue
            for m in idx[t] - {n}:
                score[m] += math.log(1330 / df[t])
                shared[m].append(t)
        for m, sc in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]:
            rows.append({"source": kural_id(n), "target": kural_id(m), "kind": "shared rare word", "weight": round(sc, 4),
                         "shared_keys": sorted(shared[m]),
                         "doc_freq": {t: df[t] for t in sorted(shared[m])}})
        a = (n - 1) // 10
        for m in range(a * 10 + 1, a * 10 + 11):
            if m != n:
                rows.append({"source": kural_id(n), "target": kural_id(m), "kind": "same chapter", "weight": None,
                             "shared_keys": [], "doc_freq": {}})
    return rows


# ----------------------------------------------------------------------------- 6. tasks
def build_tasks(core, adh, atlas):
    rng = random.Random(0)
    bad = defaultdict(list)
    for r in atlas:
        if r["status"].startswith(("corrupt", "rejected")):
            bad[r["kural_id"]].append(r)
    toks = {k["number"]: [w for w in words(k["lines_ta"])] for k in core}
    df = Counter(compare_key(w) for ws in toks.values() for w in set(ws))
    rows = []
    for k in core:
        n, lines, kid = k["number"], k["lines_ta"], k["id"]
        rows.append({"task_id": f"{kid}:complete", "kural_id": kid, "type": "complete_second_line",
                     "prompt_ta": lines[0], "choices": None, "answer": lines[1]})
        others = rng.sample([a for a in range(1, 134) if a != k["adhikaram_number"]], 3)
        choices = sorted([k["adhikaram_number"]] + others)
        rows.append({"task_id": f"{kid}:chapter", "kural_id": kid, "type": "identify_chapter",
                     "prompt_ta": "\n".join(lines), "choices": [f"{a}. {adh[a]['name_ta']}" for a in choices],
                     "answer": f"{k['adhikaram_number']}. {adh[k['adhikaram_number']]['name_ta']}"})
        rows.append({"task_id": f"{kid}:verify:true", "kural_id": kid, "type": "verify_quote",
                     "prompt_ta": "\n".join(lines), "choices": ["exact", "altered"], "answer": "exact"})
        for j, b in enumerate(sorted(bad[kid], key=lambda r: r["reading_id"])[:2]):
            rows.append({"task_id": f"{kid}:verify:attested{j}", "kural_id": kid, "type": "verify_quote",
                         "prompt_ta": b["text"], "choices": ["exact", "altered"], "answer": "altered",
                         "note": f"real attested reading: {b['status']} ({b['reading_id']})"})
        ws = toks[n]
        target = max(range(len(ws)), key=lambda i: (math.log(1330 / df[compare_key(ws[i])]), -i))
        masked = list(ws)
        masked[target] = "____"
        cut = len(words(lines[:1]))
        rows.append({"task_id": f"{kid}:cloze", "kural_id": kid, "type": "cloze",
                     "prompt_ta": " ".join(masked[:cut]) + "\n" + " ".join(masked[cut:]), "choices": None,
                     "answer": ws[target]})
    for r in rows:
        r["canary"] = CANARY
    return rows


# ----------------------------------------------------------------------------- 7. agent_card
def build_agent_cards(core, adh, quote, atlas, ledger, layers):
    q = {r["kural_id"]: r for r in quote}
    nvar = Counter(r["kural_id"] for r in atlas if not r["same_letters_as_canonical"])
    prints = REPORTS / "print_divisions.json"
    div = attested_divisions(atlas, prints if prints.exists() else None)
    status_note = {"verified_digital_only": "all digital witnesses carry the same letters (they share an upstream)",
                   "verified_scan": "checked against the printed editions (print comparison or the page image)",
                   "adjudicated": "decided by a ruling recorded in the ledger"}
    rows = []
    for k in core:
        kid = k["id"]
        notes = []
        if AU_SEQ.search("".join(k["lines_ta"])):
            notes.append("கௌ is written as ெ + ள (U+0BC6 U+0BB3) as in most sources; search form uses U+0BCC")
        if nvar[kid]:
            notes.append(f"{nvar[kid]} other attested reading(s) differ in letters: see variants_atlas")
        metre = scan(k["lines_ta"], div.get(k["number"]))  # checker v0.3, as derived.scansion_ok
        if not metre.ok:
            notes.append("does not scan as kural venba under the rule-based metre checker v0.3: an annotation, "
                         "never a reason to change the text. " + plain_reason(metre))
        elif metre.method == "attested division":
            notes.append("scans as kural venba only with an attested seer division: "
                         + next(x for x in metre.licences if x.startswith("vakaiyuli")).split("(", 1)[1].rstrip(")"))
        live = [e for e in ledger.get(kid, []) if e["field"] == "lines_ta"]
        card = {"id": kid, "n": k["number"], "text": "\n".join(k["lines_ta"]), "sha256": q[kid]["text_sha256"],
                "cite_ta": q[kid]["citation_ta"], "cite_en": q[kid]["citation_en"], "url": q[kid]["permalink"],
                "chapter": {"n": k["adhikaram_number"], "ta": adh[k["adhikaram_number"]]["name_ta"],
                            "en": adh[k["adhikaram_number"]]["name_en"]},
                "status": k["text_status"], "status_means": status_note[k["text_status"]],
                "ruling": live[-1]["ledger_id"] if live else None, "metre_ok": metre.ok,
                "layers": layers, "caveats": notes, "license": "CC0-1.0"}
        rows.append({"kural_id": kid, "card": json.dumps(card, ensure_ascii=False, separators=(",", ":"))})
    return rows


# ----------------------------------------------------------------------------- main
def released_layers():
    return [l["layer_id"] for l in json.loads(LAYERS.read_text(encoding="utf-8"))["layers"]
            if l["release_status"] in ("built", "gate_passed") and l["rights_status"] == "public-domain"]


def write_table(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows),
                                       encoding="utf-8")


def main():
    core, adh, _ = load_core()
    atlas = [json.loads(l) for l in (OUT / "variants_atlas.jsonl").read_text(encoding="utf-8").splitlines()]
    quote = build_quote_keys(core, adh)
    tables = {"quote_keys": quote, "echo_graph": build_echo_graph(core), "tasks": build_tasks(core, adh, atlas),
              "agent_card": build_agent_cards(core, adh, quote, atlas, ledger_by_subject(), released_layers())}
    for name, rows in tables.items():
        write_table(name, rows)
    print(", ".join(f"{name} {len(rows)}" for name, rows in tables.items()) + f"; permalink base {PERMALINK_BASE}")


if __name__ == "__main__":
    main()
