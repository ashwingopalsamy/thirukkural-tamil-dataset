"""Unicode hygiene for Tamil kural text.

Pinned to explicit codepoint lists so results do not drift with the Python
Unicode database version. The checks never modify text; they report.
"""
import unicodedata
from dataclasses import dataclass

TAMIL_BLOCK = range(0x0B80, 0x0C00)

AYTHAM = {0x0B83}
VOWELS = {*range(0x0B85, 0x0B8B), *range(0x0B8E, 0x0B91), *range(0x0B92, 0x0B95)}
CONSONANTS = {0x0B95, 0x0B99, 0x0B9A, 0x0B9C, 0x0B9E, 0x0B9F, 0x0BA3, 0x0BA4, 0x0BA8, 0x0BA9, 0x0BAA,
              *range(0x0BAE, 0x0BBA)}
VOWEL_SIGNS = {*range(0x0BBE, 0x0BC3), *range(0x0BC6, 0x0BC9), *range(0x0BCA, 0x0BCD)}
VIRAMA = 0x0BCD
AU_LENGTH_MARK = 0x0BD7  # only valid inside a decomposed AU, which NFC composes away
MARKS = VOWEL_SIGNS | {VIRAMA, AU_LENGTH_MARK}
LETTERS = AYTHAM | VOWELS | CONSONANTS
ALLOWED_IN_KURAL = LETTERS | MARKS | {0x0020, 0x002E}

# Named because they occur in witness kural text, or because they are forbidden outright.
FORBIDDEN_NAMED = {
    0x0BA6: "unassigned U+0BA6 (found in aitamilnadu/Chandrasekar/Selvakumar kural text)",
    0x0BA7: "unassigned U+0BA7 (found in aitamilnadu/Chandrasekar/Selvakumar kural text)",
    0x200C: "ZWNJ",
    0x200D: "ZWJ",
    0x00A0: "NBSP",
    0x200B: "zero width space",
    0x00AD: "soft hyphen",
    0xFEFF: "BOM / zero width no-break space",
}


@dataclass(frozen=True)
class Issue:
    code: str
    index: int  # codepoint offset in the string, -1 for whole-string issues
    detail: str

    def __str__(self):
        where = "" if self.index < 0 else f" at {self.index}"
        return f"{self.code}{where}: {self.detail}"


def _cp(ch: str) -> str:
    return f"U+{ord(ch):04X} {unicodedata.name(ch, '<unassigned>')}"


def check_line(s: str) -> list[Issue]:
    """All hygiene issues in one line of kural text (one line = no newline)."""
    issues = []
    if s != unicodedata.normalize("NFC", s):
        issues.append(Issue("not_nfc", -1, "string differs from its NFC form"))
    if not s:
        issues.append(Issue("empty", -1, "empty line"))
        return issues
    if s != s.strip(" "):
        issues.append(Issue("edge_space", -1, "leading or trailing space"))
    if "  " in s:
        issues.append(Issue("double_space", s.index("  "), "two consecutive spaces"))
    prev = None
    for i, ch in enumerate(s):
        o = ord(ch)
        cat = unicodedata.category(ch)
        if o in FORBIDDEN_NAMED:
            issues.append(Issue("forbidden_codepoint", i, FORBIDDEN_NAMED[o]))
        elif cat == "Co":
            issues.append(Issue("forbidden_codepoint", i, f"private use {_cp(ch)}"))
        elif o in TAMIL_BLOCK and o not in LETTERS | MARKS:
            issues.append(Issue("forbidden_codepoint", i, f"Tamil-block codepoint not allowed in kural text: {_cp(ch)}"))
        elif o not in ALLOWED_IN_KURAL:
            issues.append(Issue("disallowed_char", i, _cp(ch)))
        if o in MARKS and (prev is None or ord(prev) not in CONSONANTS):
            issues.append(Issue("orphan_mark", i, f"{_cp(ch)} not after a consonant"))
        if o == 0x002E and i != len(s) - 1:
            issues.append(Issue("inner_full_stop", i, "full stop allowed only at end of line"))
        prev = ch
    return issues


def check_lines(lines) -> list[Issue]:
    if lines is None:
        return []
    out = []
    for li, line in enumerate(lines, start=1):
        out += [Issue(x.code, x.index, f"line {li}: {x.detail}") for x in check_line(line)]
    return out


def check_name(s: str) -> list[Issue]:
    """Lighter checks for Tamil names of divisions: NFC, forbidden codepoints, orphan marks."""
    return [x for x in check_line(s) if x.code in {"not_nfc", "forbidden_codepoint", "orphan_mark", "edge_space", "double_space", "empty"}]
