"""Parimelazhagar's commentary read as structured data, by rule (the parimelazhagar_struct release config).

  python -m tkcore.parimel_struct     data/signature/parimelazhagar_struct.jsonl; prints its counts

Input: data/layers/parimelazhagar-ta.jsonl (the commentary as its carrier gives it), data/core/kurals.jsonl (to check
the word-by-word heads against the verse) and provenance/reports/layer_quarantine.json (rows the release withholds).
Every value is a span copied from the commentary, or a count; nothing is paraphrased, no model is involved, and the
same input gives the same bytes. The carrier's printed edition is unidentified, so this layer inherits that caveat.
"""
import collections
import difflib
import hashlib
import json
import re
import unicodedata

from . import REPORTS, ROOT

QUARANTINE = REPORTS / "layer_quarantine.json"
OUT = ROOT / "data" / "signature" / "parimelazhagar_struct.jsonl"
RULE = "tkcore.parimel_struct 1.0"
RELEASE_FIELDS = ["kural_id", "coverage", "pada_urai", "turai", "turai_resolved", "turai_same_as", "group_end", "summary",
                  "other_commentators", "reported_readings", "figures", "grammar_notes", "cites_works",
                  "head_letter_coverage", "flags", "source_id", "locator", "source_sha256", "commentary_sha256", "method",
                  "model_generated"]

ROLES = ["தலைமகன்", "தலைவன்", "தலைமகள்", "தலைவி", "தோழி", "பாங்கன்", "பரத்தை", "காமக்கிழத்தி", "செவிலி"]
SPEECH = r"(சொல்லியது|கூறியது|உரைத்தது|மொழிந்தது|அறிந்தது|உணர்த்தியது|மறுத்தது|வினாயது|வினவியது|நினைந்தது)"
# Terms Parimelazhagar uses for figures of speech, for grammar and for other works; each hit keeps its sentence.
# term -> (English label, pattern). A pattern must match a whole word of the sentence (quotes and punctuation
# stripped), so ordinary words that contain a term do not count: முற்றும் 'wholly' is not முற்று 'finite verb', and
# வேற்றுமையின்றி 'without difference' is not வேற்றுமை 'case'. A pattern starting with '~' is searched in the sentence.
FIGURES = {"உவமை": ("simile (uvamai)", r"\S*உவமை(?!யளவை)\S*"),   # உவமையளவை: inference by analogy, not a figure
           "உருவக": ("metaphor (uruvakam)", r"\S*உருவக\S*"), "உபசார": ("figurative usage (upacaram)", r"\S*உபசார\S*"),
           "தற்குறிப்பேற்ற": ("poetic fancy (tarkurippetram)", r"\S*தற்குறிப்பேற்ற\S*"),
           "எடுத்துக்காட்டு": ("illustration", r"\S*எடுத்துக்காட்டு\S*"), "சிலேடை": ("pun (cletai)", r"\S*சிலேடை\S*"),
           "வேற்றுமையணி": ("contrast figure", r"\S*வேற்றுமையணி\S*"), "இறைச்சி": ("suggested meaning (iraicci)", r"\S*இறைச்சி\S*")}
GRAMMAR = {"அசைநிலை": ("expletive particle", r"\S*அசைநிலை\S*"), "ஆகுபெயர்": ("metonymy (akupeyar)", r"\S*ஆகுபெயர்\S*"),
           "இசைநிறை": ("metrical filler", r"\S*இசைநிறை\S*"), "உம்மை": ("um-particle", r"\S*உம்மை\S*"),
           "தொகை": ("compound (tokai)", r"\S*தொகை(?:கள்|யோடு|யான்|ப்|த்)?"),
           "எச்சம்": ("ellipsis/participle (eccam)", r"\S*எச்சம்\S*"),
           "வேற்றுமை": ("case", r"\S*வேற்றுமை(?:த்|த்தொகை|ப்பொருள்|யுருபு|உருபு|மயக்கம்|க்கண்|யான்)?"),
           "முற்று": ("finite verb", r"\S*வினைமுற்று\S*|முற்று(?:ச்சொல்|த்தொடர)\S*|\S*(?:கால|மறை)முற்று\S*"),   # not முற்று உம்மை
           "திரிந்து": ("sandhi/form change", r"~என\S*\s*திரிந்து|திரிந்து\s*(?:நின்ற|வந்த)"),
           "விகாரம்": ("metrical alteration", r"\S*விகாரம்\S*")}
WORKS = {"தொல்காப்பிய": ("Tolkappiyam", r"தொல்காப்பிய\S*|தொல்"), "வடநூல்": ("Sanskrit treatises (vadanul)", r"\S*வடநூல்\S*"),
         "மனு": ("Manu", r"மனு(?:நூல்|வும்|வின்|முதலிய)?\S*"), "புறநானூ": ("Purananuru", r"புறநானூ\S*"),
         "கலித்தொகை": ("Kalittokai", r"கலித்தொகை\S*"), "நாலடி": ("Naladiyar", r"நாலடி\S*"),
         "சிலப்பதிகார": ("Cilappatikaram", r"சிலப்பதிகார\S*")}
NUMS = {"இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10}

def nfc(s): return unicodedata.normalize("NFC", s)

def balanced(s, i):
    """Index just past the ')' that closes s[i]=='(' (or len(s) if unclosed)."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(": depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0: return j + 1
    return len(s)

def sentences(s):
    return [x.strip() for x in re.split(r"(?<=[.?])\s+|(?<=\.)(?=[^\s.'\d])", s) if x.strip()]

def strip(w): return re.sub(r"[\s.,;:?!'\"‘’“”()\-]", "", w)

def parse(text, kural_lines):
    flags = []
    t = text.strip()
    turai = None
    m0 = re.match(r"^([^()\-=]{4,300}?)\)\s*", t)   # the carrier sometimes drops the opening bracket
    if m0 and re.search(SPEECH + r"|இதுவும் அது", m0.group(1)):
        flags.append("turai_missing_open_paren")
        turai, t = m0.group(1).strip(), t[m0.end():].strip()
    if turai is None and t.startswith("("):
        end = balanced(t, 0)
        inner = t[1:end - 1].strip() if end <= len(t) else t[1:]
        if " - " in inner:          # a stray '(' before the word gloss, not a situation note
            flags.append("leading_paren_not_turai")
            t = t[1:].strip()
        else:
            turai, t = inner, t[end:].strip()
    m_vi = re.search(r"[.?;]\s*\(", t)   # the explanation opens after a sentence end
    vi = (m_vi.end() - 1) if m_vi else t.find("(")
    pada, rest = (t[:vi].strip(), t[vi:]) if vi >= 0 else (t, "")
    vil, trailer = "", ""
    if rest:
        end = balanced(rest, 0)
        vil, trailer = rest[1:end - 1 if end <= len(rest) and rest[end - 1:end] == ")" else end].strip(), rest[end:].strip()
        if end >= len(rest) and not rest.rstrip().endswith(")"): flags.append("vilakkam_unclosed")
    pairs = []
    marks = list(re.finditer(r"\s*(?<!\d)[-–=](?!\d)\s*", pada))
    starts = []
    prev_end = 0
    kstr = "".join(strip(w) for line in kural_lines for w in line.split())
    def verse_word(w):   # starts like some stretch of the kural, allowing for a sandhi change of its first letter
        w = strip(w)
        n = max(3, len(w) - 4)
        return bool(w) and (w[:n] in kstr or (len(w) > 4 and w[1:n] in kstr))
    def verse_like(chunk):
        ws = chunk.split()
        return bool(ws) and all(verse_word(w) for w in ws)
    for i, m in enumerate(marks):
        seg = pada[prev_end:m.start()].rstrip(" .;:?")   # 'கெடும்.- ' : punctuation before the dash ends the head, not starts it
        cut = max(seg.rfind(c) for c in ";?.:")         # 'gloss: head -' as well as 'gloss; head -'
        hs = prev_end + cut + 1 if cut >= 0 else prev_end
        # a comma ends the previous gloss unless the words before it are themselves kural words
        pieces = pada[hs:prev_end + len(seg)].split(",")
        keep = 1
        while keep < len(pieces) and verse_like(pieces[-keep - 1]): keep += 1
        he = prev_end + len(seg)
        hs = he - len(",".join(pieces[-keep:]))
        if i and hs == prev_end:
            # no separator at all: the previous gloss runs straight into this head. The head is the longest run of
            # kural words at the end, leaving at least one word to the gloss.
            ws = list(re.finditer(r"\S+", pada[hs:he]))
            j = len(ws)
            while j > 1 and verse_word(ws[j - 1].group()): j -= 1
            if j < len(ws):
                hs += ws[j].start()
                flags.append("head_found_by_verse_words")
            else:
                flags.append("head_boundary_unclear")
        starts.append((hs, he, m.end()))
        prev_end = m.end()
    for i, (hs, he, ge) in enumerate(starts):
        gend = starts[i + 1][0] if i + 1 < len(starts) else len(pada)
        pairs.append({"head": pada[hs:he].strip(), "gloss": pada[ge:gend].strip().rstrip(";,").strip()})
    if not marks and pada: flags.append("no_word_gloss_marker")
    # check the heads against the kural's printed words
    heads = "".join(strip(p["head"]) for p in pairs)
    words = [strip(w) for line in kural_lines for w in line.split() if strip(w)]
    # share of the kural's letters that the heads reproduce in order (sandhi splits cost little)
    kural = "".join(words)
    sm = difflib.SequenceMatcher(None, kural, heads, autojunk=False)
    covered = sum(b.size for b in sm.get_matching_blocks())
    ck, ch = collections.Counter(kural), collections.Counter(heads)
    bag = sum(min(ck[c], ch[c]) for c in ck)   # order-free: Parimelazhagar glosses in prose order
    if kural and sum(max(0, ch[c] - ck[c]) for c in ch) / len(kural) > 0.3:
        flags.append("heads_carry_extra_words")   # the carrier repeats a phrase, or a gloss word sits in a head
    words = kural
    sents = sentences(vil) + sentences(trailer)   # split apart: the closing paren between them is not in either span
    def find(table):
        out = []
        for key, (label, pat) in table.items():
            for s in sents:
                toks = re.findall(r"[\u0b80-\u0bff]+", s)   # Tamil words; quotes, brackets and punctuation split them
                hit = re.search(pat[1:], s) if pat.startswith("~") else any(re.fullmatch(pat, t) for t in toks)
                if hit:
                    out.append({"term": key, "label_en": label, "sentence": s})
                    break
        return out
    paadam = [s for s in sents if "பாடம்" in s]
    dissent = [s for s in sents if re.search(r"(என்பாரும்|உரைப்பாரும்|ஓதுவாரும்|கூறுவாரும்|கொள்வாரும்)\s*(உளர்|உண்டு)", s)]
    summary = [s for s in sents if re.search(r"(இதனான்|இதனால்)", s) and re.search(r"(கூறப்பட்ட|சொல்லப்பட்ட)", s)]
    group = None
    for s in sents:
        m = re.search(r"இவை\s+(" + "|".join(NUMS) + r")\s+பாட்டா", s)
        if m: group = {"n_kurals": NUMS[m.group(1)], "sentence": s}
    return {"turai": turai, "pada_urai": pairs, "vilakkam": vil or None, "trailer": trailer or None,
            "head_letter_coverage": round(bag / len(words), 3) if words else None,
            "head_letter_coverage_in_verse_order": round(covered / len(words), 3) if words else None,
            "figures": find(FIGURES), "grammar_notes": find(GRAMMAR), "cites_works": find(WORKS),
            "reading_notes": paadam, "reported_readings": reported_readings(paadam, kural_lines), "other_commentators": dissent,
            "summary": summary, "group_end": group, "flags": flags}

PAADAM = r"(?:என்று|என்ற|என்பதூஉம்|என்பது|எனவும்|எனப்|என)\s*பாடம்"

def reported_readings(sentences, kural_lines):
    """Readings Parimelazhagar reports, with his stance, read off the sentence's own grammar:
    'X' என்று பாடம் ஓதி 'Y' என்று உரைப்பாரும் உளர் -> reading X, others' gloss Y."""
    words = [strip(w) for line in kural_lines for w in line.split() if strip(w)]
    out = []
    for s in sentences:
        found = (re.findall(r"'([^']+)'\s*" + PAADAM, s)
                 or re.findall(r"'([^']+)'\s*என்றும்", s)                    # 'X' என்றும் 'Y' என்றும் பாடம்
                 or re.findall(r"'([^']+?)\s+" + PAADAM, s)                   # closing quote lost in the carrier
                 or re.findall(r"(?:^|\s)(?:இனி\s*,?\s*)?([^\s',]+)\s+" + PAADAM, s))
        found = [re.sub(r"^இதனை(?=\S{3})", "", r) for r in found]           # 'இதனை' glued on by the carrier
        glosses = re.findall(r"'([^']+)'\s*(?:என்று|என)\s*(?:உரைப்பாரும்|உரைத்து|விரித்துரைப்பாரும்)", s)
        if re.search(r"பாடம் அன்மை|பாடமன்மை|அறிந்திலர்|பாடம் திரித்து|நோக்காது", s): stance = "rejected"
        elif re.search(r"(?:என்பதூஉம்|எனவும்)\s*பாடம்", s): stance = "also_a_reading"
        elif re.search(r"பாடம்\s*ஆயின்", s): stance = "conditional"
        else: stance = "reported"
        for r in found:
            key = strip(r.split()[0]) if r.split() else ""
            best = max(words, key=lambda w: difflib.SequenceMatcher(None, w, key).ratio()) if words else None
            out.append({"reading": r.strip(), "stance": stance, "others_gloss": glosses[0] if glosses else None,
                        "nearest_kural_word": best, "sentence": s})
    return out

def speaker_addressee(turai):
    """Speaker and addressee of a situation note. Not used for any released field: right on 15 of 20 checked rows."""
    if not turai: return None, None
    addr = None
    m = re.search(r"(\S+?)(க்குச்|க்குத்|க்கு|ற்குத்|ற்கு|ட்குச்|ட்கு)\s+(\S+\s+)?" + SPEECH, turai)
    if m: addr = m.group(1) + {"க்குச்": "", "க்குத்": "", "க்கு": "", "ற்குத்": "ன்", "ற்கு": "ன்", "ட்குச்": "ள்", "ட்கு": "ள்"}[m.group(2)]
    if re.search(r"நெஞ்ச(ொ|ோ)டு", turai): addr = "நெஞ்சு"
    if "தன்னுள்ளே" in turai: addr = "தன்னுள்ளே (to self)"
    spk = None
    toks = re.findall(r"\S+", re.sub(r"[.,'?]", " ", turai))
    for i, tok in enumerate(toks):
        if tok in ROLES and i + 1 < len(toks) and re.match(SPEECH, toks[-1]):
            spk = tok
    if spk is None:
        m = re.search(r"(\S+)(ான்|ாள்)\s+(\S+\s+)?" + SPEECH, turai)
        if m: spk = "male (" + m.group(0).split()[0] + ")" if m.group(2) == "ான்" else "female (" + m.group(0).split()[0] + ")"
    return spk, addr

def build() -> list[dict]:
    """Every row of the commentary layer, parsed. Rows the release withholds (provenance/reports/layer_quarantine.json) keep
    nothing, and a situation note that only says 'same as above' after a withheld row stays unresolved."""
    core = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "data/core/kurals.jsonl").read_text(encoding="utf-8").splitlines()}
    rows = [json.loads(l) for l in (ROOT / "data/layers/parimelazhagar-ta.jsonl").read_text(encoding="utf-8").splitlines()]
    held = {e["kural_id"]: e for e in json.loads(QUARANTINE.read_text(encoding="utf-8"))["rows"]
            if e["layer_id"] == "parimelazhagar-ta"}
    out, last_turai = [], None
    for r in rows:
        k, e = core[r["kural_id"]], held.get(r["kural_id"], {})
        withheld = e.get("coverage") == "missing"
        p = parse(nfc(r["text"]), k["lines_ta"])
        if withheld:   # keep nothing from a row that is not this kural's commentary
            p = {**{f: ([] if isinstance(v, list) else None) for f, v in p.items()},
                 "flags": ["withheld"] + (["commentary_of_" + e["same_text_as"]] if e.get("same_text_as") else [])}
        inherited = None
        if p["turai"] and p["turai"].rstrip(".").strip() == "இதுவும் அது":
            inherited = last_turai
            if inherited == "withheld":
                p["flags"].append("turai_refers_to_withheld_row")
                inherited = None
        elif p["turai"]:
            last_turai = (r["kural_id"], p["turai"])
        if withheld:
            last_turai = "withheld"
        if k["number"] in (1081,):  # Kamattuppal starts: forget the previous turai
            last_turai = None
        same = p["turai"] and p["turai"].rstrip(".").strip() == "இதுவும் அது"
        resolved = inherited[1] if inherited else (None if same else p["turai"])
        out.append({"kural_id": r["kural_id"], "number": k["number"], "coverage": e.get("coverage", "complete"), **p,
                    "turai_same_as": inherited[0] if inherited else None, "turai_resolved": resolved,
                    "source_id": r["source_id"], "locator": r["locator"], "source_sha256": r["source_sha256"],
                    "commentary_sha256": None if withheld else hashlib.sha256(r["text"].encode("utf-8")).hexdigest(),
                    "method": RULE, "model_generated": False})
    return out


def main():
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps({k: o[k] for k in RELEASE_FIELDS}, ensure_ascii=False, sort_keys=True) + "\n"
                           for o in out), encoding="utf-8")
    inbam = [o for o in out if o["number"] >= 1081]
    cov = [o["head_letter_coverage"] for o in out if o["head_letter_coverage"] is not None]
    st = {
        "rows": len(out),
        "rows_with_word_gloss_pairs": sum(1 for o in out if o["pada_urai"]),
        "word_gloss_pairs": sum(len(o["pada_urai"]) for o in out),
        "mean_head_letter_coverage": round(sum(cov) / len(cov), 3),
        "rows_coverage_ge_90pct": sum(1 for c in cov if c >= 0.9),
        "rows_coverage_lt_60pct": sum(1 for c in cov if c < 0.6),
        "rows_with_vilakkam": sum(1 for o in out if o["vilakkam"]),
        "inbam_rows": len(inbam),
        "inbam_with_turai": sum(1 for o in inbam if o["turai_resolved"]),
        "inbam_turai_inherited": sum(1 for o in inbam if o["turai_same_as"]),
        "rows_with_figure": sum(1 for o in out if o["figures"]),
        "figure_terms": collections.Counter(f["term"] for o in out for f in o["figures"]),
        "rows_with_grammar_note": sum(1 for o in out if o["grammar_notes"]),
        "grammar_terms": collections.Counter(f["term"] for o in out for f in o["grammar_notes"]),
        "rows_with_reading_note": sum(1 for o in out if o["reading_notes"]),
        "reported_readings": sum(len(o["reported_readings"]) for o in out),
        "reported_reading_stances": collections.Counter(r["stance"] for o in out for r in o["reported_readings"]),
        "rows_citing_other_commentators": sum(1 for o in out if o["other_commentators"]),
        "rows_with_summary": sum(1 for o in out if o["summary"]),
        "group_ends": sum(1 for o in out if o["group_end"]),
        "kurals_in_groups": sum(o["group_end"]["n_kurals"] for o in out if o["group_end"]),
        "rows_citing_works": sum(1 for o in out if o["cites_works"]),
        "rows_with_trailer": sum(1 for o in out if o["trailer"]),
        "flags": collections.Counter(f for o in out for f in o["flags"]),
    }
    print(json.dumps(st, ensure_ascii=False, indent=1, default=dict))

if __name__ == "__main__":
    main()
