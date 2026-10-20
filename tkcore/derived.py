"""Deterministic derived layer: a search form of each kural's text, kept out of the canonical lines_ta.

text_search = lines_ta with one mapping (rule C13): the sourced sequence U+0BC6 VOWEL SIGN E + U+0BB3 LETTER
LLA with no mark after the LLA, which the witnesses use for the au syllable கௌ (1143, 1147, 1148, 1150), becomes
U+0BCC VOWEL SIGN AU, the Unicode encoding, so Tamil search, sorting and lookups find it. The canonical text keeps
the majority-source form by a ledger ruling. Output: data/derived/kurals_search.jsonl (layer:
deterministic-derived). Run: python -m tkcore.derived
"""
import json
import re

from . import DATA_CORE, REPORTS, ROOT

OUT = ROOT / "data" / "derived" / "kurals_search.jsonl"
META = ROOT / "data" / "derived" / "kurals_meta.jsonl"
AU_SEQ = re.compile("ெள(?![ா-்ௗ])")


def search_form(line: str) -> str:
    return AU_SEQ.sub("ௌ", line)


def build():
    rows = []
    for line in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines():
        k = json.loads(line)
        lines = k["lines_ta"]
        search = [search_form(x) for x in lines] if lines else None
        rows.append({"id": k["id"], "text_search": search, "layer": "deterministic-derived",
                     "rule": "C13" if lines and search != lines else None})
    return rows


def letters(line):
    """Tamil letters (aksharas): a consonant with its sign or pulli, an independent vowel, or aytham."""
    from .translit import CONS, PULLI, SIGNS, VOWELS, AYTHAM
    n, i = 0, 0
    while i < len(line):
        c = line[i]
        if c in CONS:
            n += 1
            i += 2 if i + 1 < len(line) and (line[i + 1] == PULLI or line[i + 1] in SIGNS) else 1
        else:
            n += c in VOWELS or c == AYTHAM
            i += 1
    return n


def build_meta():
    """Per-kural metadata from the core (structure, names, iyal) plus deterministic derivations: transliteration of the
    search form (ISO 15919 and plain), letter/word counts, and the venba check (tkcore.prosody: v0.1 check() on the
    word-split text and v0.3 scan() with regrouping, side by side). layer:
    deterministic-derived; no text column is edited."""
    from .prosody import attested_divisions, check, plain_reason, scan
    from .structure import CANONICAL_IYAL_SCHEME, iyal_of
    from .translit import iso15919, plain
    core = [json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()]
    adh = {json.loads(l)["number"]: json.loads(l) for l in (DATA_CORE / "adhikarams.jsonl").read_text(encoding="utf-8").splitlines()}
    div = [json.loads(l) for l in (DATA_CORE / "divisions.jsonl").read_text(encoding="utf-8").splitlines()]
    paal = {d["number"]: d["name_ta"] for d in div if d["level"] == "paal"}
    iyal = {d["number"]: d["name_ta"] for d in div if d["level"] == "iyal" and d["scheme"] == CANONICAL_IYAL_SCHEME}
    atlas = ROOT / "data" / "signature" / "variants_atlas.jsonl"
    prints = REPORTS / "print_divisions.json"
    attested = attested_divisions(atlas, prints if prints.exists() else None) if atlas.exists() else {}
    rows = []
    for k in core:
        a, lines = adh[k["adhikaram_number"]], k["lines_ta"]
        i = iyal_of(k["adhikaram_number"], CANONICAL_IYAL_SCHEME)
        row = {"id": k["id"], "number": k["number"], "paal_number": k["paal_number"], "paal_name_ta": paal.get(k["paal_number"]),
               "iyal_scheme": CANONICAL_IYAL_SCHEME, "iyal_number": i, "iyal_name_ta": iyal.get(i),
               "adhikaram_number": k["adhikaram_number"], "adhikaram_name_ta": a["name_ta"], "adhikaram_name_en": a["name_en"],
               "position": k["position"], "text_status": k["text_status"], "layer": "deterministic-derived"}
        if lines:
            search = [search_form(x) for x in lines]
            r = check(lines)
            row.update({"translit_iso15919": [iso15919(x) for x in search], "translit_plain": [plain(x) for x in search],
                        "words_per_line": [len(x.replace(".", " ").split()) for x in lines],
                        "letters_per_line": [letters(x) for x in lines],
                        "venba_ok_word_split": r.ok, "venba_seers": [s.name for s in r.seers], "venba_problems": r.problems})
            sc = scan(lines, attested.get(k["number"]))
            row.update({"scansion_ok": sc.ok, "scansion_method": sc.method, "scansion_licences": sc.licences,
                        "scansion_seers": [s[0] for s in sc.seers], "scansion_feet_ta": sc.seer_names_ta,
                        "scansion_problems": sc.problems, "scansion_note": plain_reason(sc), "form_ok": sc.form_ok})
        rows.append(row)
    return rows


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    meta = build_meta()
    META.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in meta), encoding="utf-8")
    rows = build()
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")
    print(sum(1 for r in rows if r["rule"]), "kurals differ from lines_ta")


if __name__ == "__main__":
    main()
