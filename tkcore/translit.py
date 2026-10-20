"""Deterministic Tamil -> Latin transliteration: ISO 15919 and a plain-ASCII form (ISO with diacritics removed).
Rule-based, letter by letter; no dictionary, no model."""
import unicodedata

VOWELS = {"அ": "a", "ஆ": "ā", "இ": "i", "ஈ": "ī", "உ": "u", "ஊ": "ū", "எ": "e", "ஏ": "ē", "ஐ": "ai", "ஒ": "o",
          "ஓ": "ō", "ஔ": "au"}
SIGNS = {"ா": "ā", "ி": "i", "ீ": "ī", "ு": "u", "ூ": "ū", "ெ": "e", "ே": "ē", "ை": "ai", "ொ": "o", "ோ": "ō",
         "ௌ": "au"}
CONS = {"க": "k", "ங": "ṅ", "ச": "c", "ஞ": "ñ", "ட": "ṭ", "ண": "ṇ", "த": "t", "ந": "n", "ப": "p", "ம": "m",
        "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "ḻ", "ள": "ḷ", "ற": "ṟ", "ன": "ṉ",
        "ஜ": "j", "ஷ": "ṣ", "ஸ": "s", "ஹ": "h", "ஶ": "ś"}
PULLI, AYTHAM = "்", "ஃ"


def iso15919(text: str) -> str:
    t = unicodedata.normalize("NFC", text)
    out, i = [], 0
    while i < len(t):
        c = t[i]
        if c in CONS:
            nxt = t[i + 1] if i + 1 < len(t) else ""
            if nxt == PULLI:
                out.append(CONS[c]); i += 2
            elif nxt in SIGNS:
                out.append(CONS[c] + SIGNS[nxt]); i += 2
            else:
                out.append(CONS[c] + "a"); i += 1
        elif c in VOWELS:
            out.append(VOWELS[c]); i += 1
        elif c == AYTHAM:
            out.append("ḵ"); i += 1
        else:
            out.append(c); i += 1
    return "".join(out)


def plain(text: str) -> str:
    s = unicodedata.normalize("NFD", iso15919(text))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")
