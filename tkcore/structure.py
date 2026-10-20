"""Numeric structure of the Kural: 3 paals, 133 adhikarams of 10 kurals each.

Only numbers live here. Every Tamil or English *name* of a paal, iyal or adhikaram
comes from a witness file and carries provenance in data/core; none is typed in this
repository.

Citations for the numbers:
- 133 x 10 and paal sizes 38 / 70 / 25 adhikarams: every held digital witness covers
  1..1330 once each.
- Iyal ranges are commentator-dependent metadata, not text. Each scheme below names
  its citation; CANONICAL_IYAL_SCHEME sets adhikarams.iyal_number.
"""
from dataclasses import dataclass

from .ids import N_KURALS, kural_id

N_ADHIKARAMS = 133
KURALS_PER_ADHIKARAM = 10

# paal number -> (first adhikaram, last adhikaram)
PAAL_RANGES = {1: (1, 38), 2: (39, 108), 3: (109, 133)}
PAAL_SIZES = {1: 38, 2: 70, 3: 25}

# scheme id -> {"citation": str, "ranges": [(first_adhikaram, last_adhikaram), ...]}
# Iyal numbers are 1-based positions in the ranges list. Names are never stored here.
IYAL_SCHEMES = {
    "parimelazhagar-9": {
        "citation": (
            "Parimelazhagar's grouping as printed in the Lazarus / Mrugesa Mudaliyar 1885 edition with Parimelazhagar urai "
            "(archive.org kuraloftiruvallu00tirurich; leaf = JP2 index): iyal headings and 'முற்றிற்று' end lines "
            "at leaf 40 (இல்லறவியல் begins, adhikaram 5), 125 (இல்லறவியல் ends; 25 begins), "
            "189-190 (துறவறவியல் ends; 38 begins), 195 (அரசியல் begins, 39; its preface names three porul iyals: "
            "அரசியல், அங்கவியல், ஒழிபியல்), 312 (அங்கவியல் begins, 64), 520-521 (ஒழிபியல் and பொருட்பால் end; "
            "களவியல் begins, 109), 555 (களவியல் ends; கற்பியல் begins, 116). The start of ஒழிபியல் at 96 is "
            "corroborated by Tamil Wikisource மூலம் (பக்கம்:திருக்குறள், மூலம்.pdf/104)."
        ),
        "ranges": [(1, 4), (5, 24), (25, 37), (38, 38), (39, 63), (64, 95), (96, 108), (109, 115), (116, 133)],
    },
}
# The held digital witnesses (tk120404 lineage) number iyals differently (e.g. yuvaraj iyal_en=10 for adhikaram
# 79 and 87); that scheme ships as alternate division rows in data/core/divisions.jsonl, not here.
# Parimelazhagar's grouping is canonical, matching the commentary edition used.
CANONICAL_IYAL_SCHEME = "parimelazhagar-9"


@dataclass(frozen=True)
class KuralPos:
    number: int
    id: str
    paal: int
    adhikaram: int
    position: int  # 1..10 within the adhikaram


def adhikaram_of(n: int) -> int:
    return (n - 1) // KURALS_PER_ADHIKARAM + 1


def paal_of_adhikaram(a: int) -> int:
    for p, (lo, hi) in PAAL_RANGES.items():
        if lo <= a <= hi:
            return p
    raise ValueError(f"adhikaram out of range: {a}")


def kural_range(a: int) -> tuple[int, int]:
    if not 1 <= a <= N_ADHIKARAMS:
        raise ValueError(f"adhikaram out of range: {a}")
    lo = (a - 1) * KURALS_PER_ADHIKARAM + 1
    return lo, lo + KURALS_PER_ADHIKARAM - 1


def iyal_of(a: int, scheme: str) -> int:
    for i, (lo, hi) in enumerate(IYAL_SCHEMES[scheme]["ranges"], start=1):
        if lo <= a <= hi:
            return i
    raise ValueError(f"adhikaram {a} not covered by iyal scheme {scheme}")


def positions():
    for n in range(1, N_KURALS + 1):
        a = adhikaram_of(n)
        yield KuralPos(n, kural_id(n), paal_of_adhikaram(a), a, (n - 1) % KURALS_PER_ADHIKARAM + 1)
