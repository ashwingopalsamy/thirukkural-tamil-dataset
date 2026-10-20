import json

from tkcore.build import load_tables


def synthetic_line(n_tokens: int) -> str:
    """A placeholder line of n identical tokens built from codepoints (U+0B95 U+0BBE).
    Synthetic, not kural text: tests never contain typed kural text."""
    return " ".join([chr(0x0B95) + chr(0x0BBE)] * n_tokens)


def skeleton_tables() -> dict:
    """The committed core with every text, name and provenance entry removed: structure only."""
    t = load_tables()
    for k in t["kurals"]:
        k.update(lines_ta=None, seer_lines_ta=None, text_status="pending", adjudication_ids=[], provenance=[])
    for name in ("adhikarams", "divisions"):
        for r in t[name]:
            r.update(name_ta=None, name_en=None, provenance=[])
    return t


def dumps_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows)
