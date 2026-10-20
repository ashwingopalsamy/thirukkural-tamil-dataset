"""Rule-based kural venba check (own implementation, written from the standard rules of Tamil yaappu).

Letters -> asai -> seer -> thalai, applied to the word-split lines (each word taken as a seer):
  asai   ner   = one kuril or nedil, plus any following ottu (pulli consonant, aytham)
         nirai = kuril followed directly by kuril or nedil, plus any following ottu
  seer   2 asai: thema (ner ner), pulima (nirai ner), koovilam (ner nirai), karuvilam (nirai nirai)
         3 asai ending ner: kaai (allowed); ending nirai: kani (not allowed in venba); 4 asai: not allowed
         last seer only: naal (ner), malar (nirai), kaasu / pirappu (ner / nirai + a final consonant-u, see final_u)
  thalai ma (2 asai ending ner) -> next seer starts nirai; vilam (2 asai ending nirai) -> next starts ner;
         kaai -> next starts ner. Checked across the line break too.
  shape  2 lines, 4 + 3 seers.
Junctions: puṇarchi as scansion reads it (join()): final kutriyalukaram + vowel drops the u, final consonant + vowel
joins the vowel. Limits (reported as such, not hidden): the word-split form is not the seer-divided form (vakaiyuli), so a kural can
fail here and still scan in its metrical division; no kurukkam (shortened ai/au) or alapedai rules beyond the
naive letter reading. Output is an annotation, never a reason to change text.

scan() (v0.3, below) keeps these letters and adds the regrouping traditional scansion uses; check() is kept unchanged
so both verdicts can be shown side by side.
"""
import difflib
import itertools
import json
import re
import unicodedata
from dataclasses import dataclass, field

CONS = {0x0B95, 0x0B99, 0x0B9A, 0x0B9C, 0x0B9E, 0x0B9F, 0x0BA3, 0x0BA4, 0x0BA8, 0x0BA9, 0x0BAA, *range(0x0BAE, 0x0BBA)}
KURIL_VOWELS = {"அ", "இ", "உ", "எ", "ஒ"}
NEDIL_VOWELS = {"ஆ", "ஈ", "ஊ", "ஏ", "ஐ", "ஓ", "ஔ"}
KURIL_SIGNS = {"ி", "ு", "ெ", "ொ"}
NEDIL_SIGNS = {"ா", "ீ", "ூ", "ே", "ை", "ோ", "ௌ"}
PULLI = "்"
AYTHAM = "ஃ"
HARD = {"க", "ச", "ட", "த", "ப", "ற"}
SEER_NAMES = {("ner", "ner"): "thema", ("nirai", "ner"): "pulima", ("ner", "nirai"): "koovilam",
              ("nirai", "nirai"): "karuvilam"}


def units(word):
    """[(kind, text)] with kind in kuril / nedil / ottu."""
    w = unicodedata.normalize("NFC", word)
    out, i = [], 0
    while i < len(w):
        c = w[i]
        if ord(c) in CONS:
            nxt = w[i + 1] if i + 1 < len(w) else ""
            if nxt == PULLI:
                out.append(("ottu", c + nxt)); i += 2
            elif nxt in KURIL_SIGNS:
                out.append(("kuril", c + nxt)); i += 2
            elif nxt in NEDIL_SIGNS:
                out.append(("nedil", c + nxt)); i += 2
            else:
                out.append(("kuril", c)); i += 1
        elif c in KURIL_VOWELS:
            out.append(("kuril", c)); i += 1
        elif c in NEDIL_VOWELS:
            out.append(("nedil", c)); i += 1
        elif c == AYTHAM:
            out.append(("ottu", c)); i += 1
        else:
            i += 1  # punctuation and anything else is not a letter
    return out


def asai(word):
    """[(kind, text)] with kind ner / nirai."""
    u, out, p = units(word), [], 0
    while p < len(u):
        if u[p][0] == "ottu":  # stray leading ottu: attach to previous asai
            if out:
                out[-1] = (out[-1][0], out[-1][1] + u[p][1])
            p += 1
            continue
        if u[p][0] == "kuril" and p + 1 < len(u) and u[p + 1][0] != "ottu":
            kind, text, p = "nirai", u[p][1] + u[p + 1][1], p + 2
        else:
            kind, text, p = "ner", u[p][1], p + 1
        while p < len(u) and u[p][0] == "ottu":
            text, p = text + u[p][1], p + 1
        out.append((kind, text))
    return out


def final_u(text):
    """A final asai that is a lone consonant + short u. Kaasu/pirappu are named for the kutriyalukaram on a hard
    consonant (கு சு டு து பு று); the kurals also end in u on other consonants (தாழ்வு), so any consonant is accepted."""
    return len(text) == 2 and ord(text[0]) in CONS and text[1] == "ு"


@dataclass
class Seer:
    word: str
    asai: list
    name: str
    ok: bool
    final: bool = False


@dataclass
class Result:
    ok: bool
    shape_ok: bool
    seers: list = field(default_factory=list)
    problems: list = field(default_factory=list)


def classify(word, final):
    a = asai(word)
    kinds = tuple(k for k, _ in a)
    if final:
        if len(a) == 1:
            return Seer(word, a, "naal" if kinds[0] == "ner" else "malar", True, True)
        if len(a) == 2 and kinds[1] == "ner" and final_u(a[1][1]):
            return Seer(word, a, "kaasu" if kinds[0] == "ner" else "pirappu", True, True)
        return Seer(word, a, f"final seer of {len(a)} asai {kinds}", False, True)
    if len(a) == 2:
        return Seer(word, a, SEER_NAMES[kinds], True)
    if len(a) == 3:
        return Seer(word, a, "kaai" if kinds[2] == "ner" else "kani", kinds[2] == "ner")
    return Seer(word, a, f"{len(a)}-asai seer", False)


VOWEL_SIGN_OF = {"அ": "", "ஆ": "ா", "இ": "ி", "ஈ": "ீ", "உ": "ு", "ஊ": "ூ", "எ": "ெ", "ஏ": "ே", "ஐ": "ை",
                 "ஒ": "ொ", "ஓ": "ோ", "ஔ": "ௌ"}


def join(words):
    """Puṇarchi at word junctions, as scansion reads them (the words keep their places as seers):
    a final kutriyalukaram before a vowel loses its u, and a final consonant (pulli) before a vowel moves onto it
    (uyir eRal); a vowel after a vowel takes a glide, which changes no asai."""
    w = [unicodedata.normalize("NFC", x) for x in words]
    for i in range(len(w) - 1):
        nxt = w[i + 1]
        if not nxt or nxt[0] not in VOWEL_SIGN_OF:
            continue
        cur = w[i]
        if len(cur) >= 2 and cur[-1] == "ு" and cur[-2] in HARD:
            cons, cur = cur[-2], cur[:-2]
        elif len(cur) >= 2 and cur[-1] == PULLI and ord(cur[-2]) in CONS:
            cons, cur = cur[-2], cur[:-2]
        else:
            continue
        if not cur:
            continue
        w[i], w[i + 1] = cur, cons + VOWEL_SIGN_OF[nxt[0]] + nxt[1:]
    return w


def check(lines):
    """Venba check of a kural given as two word-split lines."""
    words = join([w for ln in lines for w in ln.replace(".", " ").split()])
    shape_ok = len(lines) == 2 and [len(ln.replace(".", " ").split()) for ln in lines] == [4, 3]
    seers = [classify(w, i == len(words) - 1) for i, w in enumerate(words)]
    problems = [] if shape_ok else [f"shape {[len(ln.split()) for ln in lines]}, expected [4, 3]"]
    problems += [f"seer {i + 1} '{s.word}': {s.name} not allowed" for i, s in enumerate(seers) if not s.ok]
    for i in range(len(seers) - 1):
        prev, nxt = seers[i], seers[i + 1]
        if not prev.ok or not nxt.asai:
            continue
        last, first = prev.asai[-1][0], nxt.asai[0][0]
        need = "nirai" if (len(prev.asai) == 2 and last == "ner") else "ner"
        if first != need:
            problems.append(f"thalai {i + 1}->{i + 2} '{prev.word}' ({prev.name}) + '{nxt.word}' starts {first}, venba needs {need}")
    return Result(not problems, shape_ok, seers, problems)


class VenbaChecker:
    name = "tkcore.prosody"
    version = "0.1"

    def scan(self, seer_lines):
        from .seer import ScanResult
        r = check(seer_lines)
        return ScanResult(meter_ok_strict=r.ok, meter_ok=r.ok, licences=(), detail="; ".join(r.problems))


# ----------------------------------------------------------------------------- v0.2/v0.3: scansion with regrouping
# check() above (v0.1) stays as it is: it reads each printed word as a seer and its verdict is kept beside this one.
# scan() reads the same letters the way traditional scansion does, in three steps, and says which step made it scan:
#   1. phonology on the printed words: கெள read as கௌ (ெ + ள, rule C13); kutriyalukaram/ottu elision inside a token
#      written without a space (படிறுஇலவாம் -> படிறிலவாம்); a lone short syllable + ottu doubles before a vowel
#      (கொல் + எனும் -> கொல்லெனும்); kutriyalikaram: a word-final hard consonant + u before ய (எனப்படுவது யாதெனின்), or a
#      word the source already wrote as Cி + யா (அருளல்ல தியாதெனிற்), is a half-vowel that may count as a short letter or
#      not (yaappu allows both; both are tried and the licence is reported). muttriyalukaram (அது, விடு) keeps its u.
#   2. rules that move a seer boundary off a word boundary: a line-internal word that opens with a short syllable +
#      ஆய்தம் gives that syllable to the seer before it (துன்பம் அஃதுண்டேல் -> துன்பமஃ துண்டேல்); a line with
#      fewer printed words than feet may divide a word into two feet (துவ்வாதவர்க்கும் -> துவ்வா தவர்க்கு).
#   3. vakaiyuli: a seer division attested in a seer-divided edition, projected onto our letters: Tamil Wikisource's
#      Parimelazhagar text (L3), then (v0.3) the foot breaks of the three printed editions
#      (provenance/reports/print_divisions.json). Only boundary positions are taken from them; the letters scanned are ours.
# A free search over every possible division is deliberately not done: it finds a scanning division for text with a
# missing word (262) or a missing pulli (784), so it would hide exactly the defects the check exists to show.
# ஆய்தம் always counts as an ottu. Counting it as a short letter would make 226, 363, 414, 943 and 1166 scan, but
# it would also make 262 scan with a word missing and its printed reading fail, so it is not offered.
# form_ok is separate from the metre: more printed words on a line than feet (4, 3) means the text is written split
# where the print joins (60 மற்று அதன், print மற்றதன்), even when the letters scan.
SCAN_VERSION = "0.3"
_NON_TAMIL = re.compile(r"[^\u0B80-\u0BFF\s]")
_SIGNS = KURIL_SIGNS | NEDIL_SIGNS
_TA_NAMES = {"thema": "தேமா", "pulima": "புளிமா", "koovilam": "கூவிளம்", "karuvilam": "கருவிளம்", "naal": "நாள்",
             "malar": "மலர்", "kaasu": "காசு", "pirappu": "பிறப்பு"}


@dataclass
class Scan:
    ok: bool
    form_ok: bool
    method: str            # "word" | "rules" | "attested division" | "none"
    licences: list
    seers: list            # [(text, [(kind, text)], name, ok)]
    problems: list

    @property
    def seer_names_ta(self):
        out = []
        for _, a, name, _ in self.seers:
            if name == "kaai":
                k = tuple(x for x, _ in a[:2])
                out.append({("ner", "ner"): "தேமாங்காய்", ("nirai", "ner"): "புளிமாங்காய்", ("ner", "nirai"): "கூவிளங்காய்",
                            ("nirai", "nirai"): "கருவிளங்காய்"}[k])
            else:
                out.append(_TA_NAMES.get(name, name))
        return out


def _au(tok):
    out = []
    for i, c in enumerate(tok):
        if c == "ள" and i >= 2 and tok[i - 1] == "ெ" and ord(tok[i - 2]) in CONS and (i + 1 == len(tok) or tok[i + 1] not in _SIGNS | {PULLI}):
            out[-1] = "ௌ"
            continue
        out.append(c)
    return "".join(out)


def _kutriyal(word):
    """Final u on a hard consonant is kutriyalukaram unless the word is one short syllable + that u (அது, விடு:
    muttriyalukaram, which keeps its vowel)."""
    u = units(word)
    return len(word) >= 2 and word[-1] == "ு" and word[-2] in HARD and not (len(u) == 2 and u[0][0] == "kuril")


def _join2(words):
    """join() with two corrections: a muttriyalukaram keeps its u (அது ஈனும்), and a word of one short syllable + ottu
    keeps its consonant and doubles it onto a following vowel (கொல் + எனும் -> கொல் லெனும்)."""
    w = list(words)
    for i in range(len(w) - 1):
        nxt, cur = w[i + 1], w[i]
        if not nxt or nxt[0] not in VOWEL_SIGN_OF or len(cur) < 2:
            continue
        u = units(cur)
        if cur[-1] == PULLI and ord(cur[-2]) in CONS:
            if len(u) == 2 and u[0][0] == "kuril":
                w[i + 1] = cur[-2] + VOWEL_SIGN_OF[nxt[0]] + nxt[1:]
            elif len(cur) > 2:
                w[i], w[i + 1] = cur[:-2], cur[-2] + VOWEL_SIGN_OF[nxt[0]] + nxt[1:]
        elif _kutriyal(cur):
            w[i], w[i + 1] = cur[:-2], cur[-2] + VOWEL_SIGN_OF[nxt[0]] + nxt[1:]
    return w


def _intoken(tok):
    parts, cur = [], ""
    for i, c in enumerate(tok):
        if i > 0 and c in VOWEL_SIGN_OF and cur:
            parts.append(cur)
            cur = c
        else:
            cur += c
    parts.append(cur)
    return "".join(_join2(parts)) if len(parts) > 1 else tok


IKARAM = "ikaram"  # a kutriyalikaram unit: may count as a short letter or not (licence), see _variants


def _phonology(lines, lic):
    """[[unit lists per printed word] per line], applying step 1. Kutriyalikaram units carry kind IKARAM."""
    toks = []
    for li, ln in enumerate(lines):
        for t in _NON_TAMIL.sub(" ", unicodedata.normalize("NFC", ln)).split():
            a = _au(t)
            if a != t:
                lic.add("au read as one letter (கெள = கௌ)")
            b = _intoken(a)
            if b != a:
                lic.add("elision inside a written word")
            toks.append([li, b, ""])  # third field: a kutriyalikaram moved onto this word
    for i in range(len(toks) - 1):
        w, nxt = toks[i][1], toks[i + 1][1]
        if nxt.startswith("ய") and _kutriyal(w) and len(w) > 2:
            toks[i][1], toks[i + 1][2] = w[:-2], w[-2] + "ி"
    words = _join2([t[1] for t in toks])
    out = [[], []]
    for i, ((li, _, pre), w) in enumerate(zip(toks, words)):
        u = units(w)
        if pre:
            u = [(IKARAM, pre)] + u
        for j in range(len(u) - 1):
            # the source already wrote the kutriyalikaram: Cி + யா at the start of a word after a vowel-final word,
            # or after an ottu inside a word (பண்பியார்க்கு)
            x, y = u[j], u[j + 1]
            if x[0] == "kuril" and len(x[1]) == 2 and x[1][0] in HARD and x[1][1] == "ி" and y[1] == "யா":
                if (j == 0 and i and words[i - 1][-1:] != PULLI) or (j > 0 and u[j - 1][0] == "ottu"):
                    u[j] = (IKARAM, x[1])
        out[min(li, 1)].append(u)
    return out


def _variants(lw):
    """Each kutriyalikaram either counts as a short letter or forms no asai (yaappu allows both)."""
    sites = [(li, wi, ui) for li in (0, 1) for wi, w in enumerate(lw[li]) for ui, x in enumerate(w) if x[0] == IKARAM]
    for mask in itertools.product((True, False), repeat=len(sites)):
        drop = {s for s, counted in zip(sites, mask) if not counted}
        tags = {"kutriyalikaram " + ("not counted" if drop else "counted")} if sites else set()
        yield [[[("kuril", x[1]) if x[0] == IKARAM else x for ui, x in enumerate(w) if (li, wi, ui) not in drop]
                for wi, w in enumerate(lw[li])] for li in (0, 1)], tags


def _asai_u(u):
    out, p = [], 0
    while p < len(u):
        if u[p][0] == "ottu":
            if out:
                out[-1] = (out[-1][0], out[-1][1] + u[p][1])
            p += 1
            continue
        if u[p][0] == "kuril" and p + 1 < len(u) and u[p + 1][0] != "ottu":
            kind, text, p = "nirai", u[p][1] + u[p + 1][1], p + 2
        else:
            kind, text, p = "ner", u[p][1], p + 1
        while p < len(u) and u[p][0] == "ottu":
            text, p = text + u[p][1], p + 1
        out.append((kind, text))
    return out


def _foot(a, final):
    kinds = tuple(k for k, _ in a)
    if not a:
        return "empty", False
    if final:
        if len(a) == 1:
            return ("naal" if kinds[0] == "ner" else "malar"), True
        if len(a) == 2 and kinds[1] == "ner" and final_u(a[1][1]):
            return ("kaasu" if kinds[0] == "ner" else "pirappu"), True
        return f"final seer of {len(a)} asai {kinds}", False
    if len(a) == 2:
        return SEER_NAMES[kinds], True
    if len(a) == 3:
        return ("kaai" if kinds[2] == "ner" else "kani"), kinds[2] == "ner"
    return f"{len(a)}-asai seer", False


def _evaluate(feet):
    """feet: [[units] x 7] -> (ok, seers, problems)."""
    seers, problems = [], []
    for i, u in enumerate(feet):
        a = _asai_u(u)
        name, ok = _foot(a, i == len(feet) - 1)
        text = "".join(t for _, t in u)
        seers.append((text, a, name, ok))
        if not ok:
            problems.append(f"seer {i + 1} '{text}': {name} not allowed")
    for i in range(len(seers) - 1):
        (pt, pa, pn, pok), (nt, na, _, _) = seers[i], seers[i + 1]
        if not pok or not na:
            continue
        need = "nirai" if (len(pa) == 2 and pa[-1][0] == "ner") else "ner"
        if na[0][0] != need:
            problems.append(f"thalai {i + 1}->{i + 2} '{pt}' ({pn}) + '{nt}' starts {na[0][0]}, venba needs {need}")
    return not problems, seers, problems


def _cuts(u):
    return [i for i in range(1, len(u)) if u[i][0] != "ottu"]


def _rule_variants(lw):
    """Step 2: per line, the word lists after optional ஆய்தம் moves, then splits up to the needed number of feet."""
    per_line = []
    for li, words, need in ((0, lw[0], 4), (1, lw[1], 3)):
        sites = [j for j in range(1, len(words)) if len(words[j]) >= 2 and words[j][0][0] == "kuril" and words[j][1] == ("ottu", AYTHAM)]
        opts = []
        for mask in itertools.product((False, True), repeat=len(sites)):
            ws = [list(w) for w in words]
            for on, j in zip(mask, sites):
                if on:
                    ws[j - 1] += ws[j][:2]
                    ws[j] = ws[j][2:]
            ws = [w for w in ws if w]
            tags = {"ஆய்தம் syllable joins the seer before it"} if any(mask) else set()
            if len(ws) == need:
                opts.append((ws, tags))
            elif len(ws) == need - 1:
                for j, w in enumerate(ws):
                    for c in _cuts(w):
                        opts.append((ws[:j] + [w[:c], w[c:]] + ws[j + 1:], tags | {"a word divided into two feet"}))
        per_line.append(opts)
    for (w1, t1), (w2, t2) in itertools.product(*per_line):
        yield w1 + w2, t1 | t2


def _key(u):
    kind, text = u
    if kind == "ottu":
        return "o"
    if text in VOWEL_SIGN_OF:
        return kind + VOWEL_SIGN_OF[text]
    return kind + (text[-1] if text[-1] in _SIGNS else "")


def _division_lines(division):
    if not division:
        return None
    t = re.sub(r"''.*?''", " ", division)
    t = re.sub(r"&[a-z]+;", " ", t)
    lines = [ln for ln in re.split(r"\n|<br\s*/?>", t) if ln.strip()]
    if len(lines) != 2:
        return None
    feet = [[units(w) for w in _NON_TAMIL.sub(" ", unicodedata.normalize("NFC", ln)).split()] for ln in lines]
    return feet if [len(f) for f in feet] == [4, 3] else None


def _project(core_units, div_feet):
    """Seer boundaries of an attested division, mapped onto our units by aligning vowel/length keys."""
    d = [u for f in div_feet for u in f]
    bounds, acc = [], 0
    for f in div_feet[:-1]:
        acc += len(f)
        bounds.append(acc)
    sm = difflib.SequenceMatcher(None, [_key(u) for u in d], [_key(u) for u in core_units], autojunk=False)
    m = [0] * (len(d) + 1)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for i in range(i1, i2):
            m[i] = j1 + (i - i1 if tag == "equal" else min(i - i1, j2 - j1))
    m[len(d)] = len(core_units)
    cuts = []
    for b in bounds:
        c = m[b]
        while c < len(core_units) and core_units[c][0] == "ottu":
            c += 1
        if not 0 < c < len(core_units) or (cuts and c <= cuts[-1]):
            return None
        cuts.append(c)
    edges = [0] + cuts + [len(core_units)]
    return [core_units[edges[i]:edges[i + 1]] for i in range(len(edges) - 1)]


def scan(lines, division=None):
    """Venba scansion of a kural (v0.3). `division`: attested seer-divided texts of the same kural (two lines, 4 + 3
    seers), as one text or a list of (label, text) in order of preference; used only for where the seer boundaries
    fall. Output is an annotation, never a reason to change text."""
    lic = set()
    printed = [len(_NON_TAMIL.sub(" ", ln).split()) for ln in lines]
    form_ok = len(lines) == 2 and printed[0] <= 4 and printed[1] <= 3
    base = _phonology(lines, lic)
    attested = [("L3", division)] if isinstance(division, str) else list(division or [])
    divs = [(label, d) for label, d in ((lb, _division_lines(x)) for lb, x in attested) if d]
    variants = list(_variants(base))
    first = None

    def attempts(lw):
        if [len(lw[0]), len(lw[1])] == [4, 3]:
            yield "word", lw[0] + lw[1], set()
        for feet, tags in _rule_variants(lw):
            yield "rules", feet, tags
        for label, div in divs:
            p1 = _project([u for w in lw[0] for u in w], div[0])
            p2 = _project([u for w in lw[1] for u in w], div[1])
            if p1 and p2:
                yield "attested division", p1 + p2, {DIVISION_LICENCE.get(label, f"vakaiyuli (division in {label})")}

    for method in ("word", "rules", "attested division"):
        for lw, vtags in variants:
            for m, feet, tags in attempts(lw):
                if m != method:
                    continue
                r = _evaluate(feet)
                if m == "word" or (m == "attested division" and first is None):
                    first = first or r
                if r[0]:
                    return Scan(True, form_ok, m, sorted(lic | vtags | tags), r[1], [])
    lw = base
    probs = (first[2] if first else [f"shape {[len(lw[0]), len(lw[1])]}, expected [4, 3]"])
    probs = probs + (["no attested seer division to try"] if not divs else
                     [f"the attested seer division{'s' if len(divs) > 1 else ''} ({', '.join(lb for lb, _ in divs)}) do"
                      f"{'' if len(divs) > 1 else 'es'} not scan on these letters either"])
    return Scan(False, form_ok, "none", sorted(lic), first[1] if first else [], probs)



DIVISION_LICENCE = {"L3": "vakaiyuli (division attested in L3)",
                    "lazarus1885": "vakaiyuli (division printed in Lazarus 1885)",
                    "navalar": "vakaiyuli (division printed in Navalar)",
                    "pope1886": "vakaiyuli (division printed in Pope 1886)"}
PRINT_ORDER = ("lazarus1885", "navalar", "pope1886")


def attested_divisions(atlas, prints=None):
    """{kural number: [(label, seer-divided text), ...]}: Tamil Wikisource's Parimelazhagar text from the variants atlas
    (`atlas`: its .jsonl path, or its rows), then the printed editions' divisions from `prints`
    (provenance/reports/print_divisions.json) where the kural was located reliably as 4 + 3 words."""
    out = {}
    rows = atlas if isinstance(atlas, list) else (json.loads(line) for line in open(atlas, encoding="utf-8"))
    for r in rows:
        if r["status"].startswith("metrical") and any("parimelazhagar_wikisource" in s["locator"] for s in r["sources"]):
            out.setdefault(int(r["kural_id"][3:]), []).append(("L3", r["text"]))
    if prints is not None:
        data = prints if isinstance(prints, dict) else json.loads(open(prints, encoding="utf-8").read())
        for n, by_scan in data["kurals"].items():
            for k in PRINT_ORDER:
                x = by_scan.get(k)
                if x and x["reliable"] and x["lines"] and [len(x["lines"][0]), len(x["lines"][1])] == [4, 3]:
                    out.setdefault(int(n), []).append((k, " ".join(x["lines"][0]) + "\n" + " ".join(x["lines"][1])))
    return out


_AYTHAM_NOTE = ("The prints divide this line so that the foot opening with the ஆய்தம் syllable has to count as two short "
                "letters. This checker always counts ஆய்தம் as a consonant: counting it as a letter is allowed in some "
                "places by tradition, but done everywhere it would also let a kural with a missing word scan (262), so "
                "it is not modelled.")


def plain_reason(r):
    """One or two sentences a reader can follow, for a kural that does not scan or is written split. None otherwise."""
    if r.ok and r.form_ok:
        return None
    if r.ok:
        return ("The letters scan, but a line has more written words than feet: the text writes apart words that the "
                "print joins.")
    if any(p.startswith("thalai") and "ஃ" in p.split("+")[-1] for p in r.problems):
        return _AYTHAM_NOTE
    if any("no attested seer division" in p for p in r.problems):
        return ("The words as written do not fall into the seven feet the metre needs, and no edition's foot division "
                "could be read for this kural, so the checker cannot try the traditional division.")
    return ("The words as written do not scan, and neither does any attested foot division applied to these letters. "
            "Either the text differs from what the metre needs, or the verse uses a licence this checker does not "
            "model; a scan check decides which.")
