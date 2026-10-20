"""Letter-sequence checks inside a word (mei mayakkam and vowel placement), written from the standard rules of
Tamil grammar. A hit is a pointer for review: it never changes text.

  cluster   a pulli consonant followed by a consonant that may not follow it inside a word
            (e.g. a hard stop followed by a different consonant: ற்ய, த்ர, க்ல)
  vowel     an independent vowel letter right after a short vowel of the same quality, or after another vowel letter,
            unless it is an alapedai (a long vowel stretched by its short form: தொழாஅர், தரூஉம், ஓஒதல்)
Words containing grantha letters (ஜ ஷ ஸ ஹ ஶ) are skipped.
"""
import unicodedata

PULLI = "்"
CONS = set("கஙசஞடணதநபமயரலவழளறன")
GRANTHA = set("ஜஷஸஹஶ")
VOWELS = set("அஆஇஈஉஊஎஏஐஒஓஔ")
# consonant (with pulli) -> consonants that may follow it inside a word. Only the stops and வ are checked: the
# witnesses write many compounds joined without sandhi (வான்நின்று, தம்தம்), so nasal and liquid clusters vary by
# convention and are not evidence of an error.
FOLLOW = {"க": "க", "ச": "ச", "த": "த", "ப": "ப", "ட": "டகசப", "ற": "றகசப", "வ": "யவ"}
# alapedai: long vowel (as letter or sign) -> its short stretching vowel
STRETCH = {"ஆ": "அ", "ா": "அ", "ஈ": "இ", "ீ": "இ", "ஊ": "உ", "ூ": "உ", "ஏ": "எ", "ே": "எ", "ஐ": "இ", "ை": "இ",
           "ஓ": "ஒ", "ோ": "ஒ", "ஔ": "உ", "ௌ": "உ"}


SHORT_OF = {"ு": "உ", "ி": "இ", "ெ": "எ", "ொ": "ஒ", "அ": "அ", "இ": "இ", "உ": "உ", "எ": "எ", "ஒ": "ஒ"}


def broken_stretch(before, vowel):
    """A vowel letter after a short vowel of the same quality (ருஉ, ஒஓ) or after another vowel letter: an alapedai
    stretches a long vowel, so either pattern is not a well-formed spelling."""
    if before in VOWELS:
        return STRETCH.get(before) != vowel
    return SHORT_OF.get(before) == vowel


def check_word(word):
    w = unicodedata.normalize("NFC", "".join(c for c in word if 0x0B80 <= ord(c) <= 0x0BFF))
    if any(c in GRANTHA for c in w):
        return []
    hits = []
    for i, c in enumerate(w):
        if c == PULLI and i >= 1 and i + 1 < len(w) and w[i + 1] in CONS:
            prev = w[i - 1]
            if prev in FOLLOW and w[i + 1] not in FOLLOW[prev]:
                hits.append(("cluster", i, w[i - 1:i + 2]))
        if c in VOWELS and i > 0 and broken_stretch(w[i - 1], c):
            hits.append(("vowel", i, w[max(0, i - 2):i + 1]))
    return hits


def check_lines(lines):
    out = []
    for li, line in enumerate(lines, 1):
        for word in line.split():
            for kind, i, ctx in check_word(word):
                out.append({"line": li, "word": word, "kind": kind, "context": ctx})
    return out
