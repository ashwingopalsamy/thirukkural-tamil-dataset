"""Token counts in the card: the texts they cover, a hash per text, and the text chart.

provenance/reports/tokenizer_cost.json holds the counts for seven tokenizers and the hash of each text it counted.
tkcore.release refuses the counts once any of those texts changes. Everything here is computed from the report and the
release tables, so two builds give the same bytes.
"""
import hashlib
import json

# The texts the token counts cover: field in tokenizer_cost.json -> (release config, column).
TOKEN_FIELDS = {"kural_ta": ("kurals", "text_ta"), "pope_en": ("pope1886_en", "text"),
                "drew_en": ("drew_lazarus_en", "text"), "parimel_ta": ("parimelazhagar_ta", "text")}
BARS = " ▏▎▍▌▋▊▉█"


def token_texts(tables: dict) -> dict:
    """{field: [text or None, in kural order]}; a withheld layer row is None and is not counted."""
    ids = [k["id"] for k in tables["kurals"]]
    out = {}
    for field, (config, column) in TOKEN_FIELDS.items():
        by = {r.get("kural_id", r.get("id")): r[column] for r in tables[config]}
        out[field] = [by[i] for i in ids]
    return out


def texts_sha256(texts: dict) -> dict:
    """One hash per counted text, so the build can refuse token counts measured on other text."""
    return {f: hashlib.sha256(json.dumps(xs, ensure_ascii=False).encode()).hexdigest() for f, xs in texts.items()}


def _bar(value: float, scale: float) -> str:
    eighths = round(value / scale * 8)
    return BARS[8] * (eighths // 8) + (BARS[eighths % 8] if eighths % 8 else "")


def token_chart_text(doc: dict, width: int = 40) -> str:
    """Tokens for all 1,330 kurals in Tamil and in Pope's English, per tokenizer, as text bars in a code block, so the
    chart shows the same on Hugging Face, GitHub and in a terminal."""
    rows = doc["tokenizers"]
    scale = max(max(r["tokens_total"]["kural_ta"], r["tokens_total"]["pope_en"]) for r in rows) / width
    name_w = max(len(r["tokenizer"]) for r in rows) + 2
    lines = []
    for r in rows:
        name = r["tokenizer"] + ("" if r["first_party"] else " *")
        for i, (label, field) in enumerate((("Tamil  ", "kural_ta"), ("English", "pope_en"))):
            v = r["tokens_total"][field]
            lines.append(f"{(name if i == 0 else ''):<{name_w}}{label} {_bar(v, scale):<{width}} {v:>9,}")
        lines.append("")
    return "```text\n" + "\n".join(lines[:-1]) + "\n```"


def values(tc: dict) -> dict:
    """Placeholders for the card's token section."""
    rows = tc["tokenizers"]
    more = [r for r in rows if r["tokens_total"]["kural_ta"] > r["tokens_total"]["pope_en"]]
    return {
        "TOKEN_CHART": token_chart_text(tc),
        "TOK_TA_MORE": f"{len(more)}", "TOK_N": f"{len(rows)}",
        "TOK_TA_MIN": f"{min(r['tokens_total']['kural_ta'] for r in rows):,}",
        "TOK_TA_MAX": f"{max(r['tokens_total']['kural_ta'] for r in rows):,}",
    }
