from collections import Counter

import pytest

from tkcore.ids import kural_id, kural_number
from tkcore.structure import (IYAL_SCHEMES, N_ADHIKARAMS, PAAL_RANGES, PAAL_SIZES, adhikaram_of, iyal_of,
                              kural_range, paal_of_adhikaram, positions)


def test_ids_roundtrip_and_bounds():
    assert kural_id(1) == "tk:0001" and kural_id(1330) == "tk:1330"
    assert all(kural_number(kural_id(n)) == n for n in range(1, 1331))
    for bad in (0, 1331):
        with pytest.raises(ValueError):
            kural_id(bad)
    for bad in ("tk:0000", "tk:1331", "tk:1", "TK:0001", "tk:00010"):
        with pytest.raises(ValueError):
            kural_number(bad)


def test_133_by_10():
    pos = list(positions())
    assert len(pos) == 1330
    assert Counter(p.adhikaram for p in pos) == {a: 10 for a in range(1, N_ADHIKARAMS + 1)}
    assert [p.position for p in pos[:11]] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1]
    assert kural_range(1) == (1, 10) and kural_range(133) == (1321, 1330)
    assert adhikaram_of(10) == 1 and adhikaram_of(11) == 2 and adhikaram_of(1330) == 133


def test_paal_38_70_25():
    assert PAAL_SIZES == {1: 38, 2: 70, 3: 25}
    assert {p: hi - lo + 1 for p, (lo, hi) in PAAL_RANGES.items()} == PAAL_SIZES
    assert Counter(paal_of_adhikaram(a) for a in range(1, 134)) == PAAL_SIZES
    assert Counter(p.paal for p in positions()) == {1: 380, 2: 700, 3: 250}


@pytest.mark.parametrize("scheme", sorted(IYAL_SCHEMES))
def test_iyal_schemes_partition_and_respect_paals(scheme):
    ranges = IYAL_SCHEMES[scheme]["ranges"]
    assert ranges[0][0] == 1 and ranges[-1][1] == 133
    for (lo, hi), (nlo, _) in zip(ranges, ranges[1:]):
        assert nlo == hi + 1
    for lo, hi in ranges:
        assert paal_of_adhikaram(lo) == paal_of_adhikaram(hi)
    assert IYAL_SCHEMES[scheme]["citation"]
    assert [iyal_of(a, scheme) for a in (1, 133)] == [1, len(ranges)]
