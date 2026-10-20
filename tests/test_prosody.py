"""tkcore.prosody v0.2 (scan) against v0.1 (check).

The guard cases pair a defective form of the text ("as written") with the reading all three prints show
(Lazarus 1885, Pope 1886, Navalar). A checker that let the written form of these scan would hide the defect it exists
to show, so they are pinned here as literals, independent of the core.
"""
import json

import pytest

from tkcore import DATA_CORE, REPORTS, ROOT
from tkcore.prosody import attested_divisions, check, plain_reason, scan

ATLAS = ROOT / "data" / "signature" / "variants_atlas.jsonl"
PRINTS = REPORTS / "print_divisions.json"
GUARDS = {
    143: (["விளிந்தாரின் வேறல்லர் மன்ற தெளிந்தாரில்", "தீமை புரிந்துதொழுகு வார்."], ["விளிந்தாரின் வேறல்லர் மன்ற தெளிந்தாரில்", "தீமை புரிந்தொழுகு வார்."]),
    262: (["தவமும் தவமுடையார்க்கு ஆகும் அதனை", "அஃதிலார் மேற்கொள் வது."], ["தவமும் தவமுடையார்க்கு ஆகும் அவமதனை", "அஃதிலார் மேற்கொள் வது."]),
    784: (["நகுதற் பொருட்டன்று நட்டல் மிகுதிக்கண்", "மேற்செனறு இடித்தற் பொருட்டு."], ["நகுதற் பொருட்டன்று நட்டல் மிகுதிக்கண்", "மேற்சென்று இடித்தற் பொருட்டு."]),
}
SPLIT_60 = (["மங்கலம் என்ப மனைமாட்சி மற்று அதன்", "நன்கலம் நன்மக்கட் பேறு."], ["மங்கலம் என்ப மனைமாட்சி மற்றதன்", "நன்கலம் நன்மக்கட் பேறு."])


@pytest.fixture(scope="module")
def divisions():
    if not ATLAS.exists():
        pytest.skip("variants atlas not built")
    return attested_divisions(ATLAS, PRINTS if PRINTS.exists() else None)


@pytest.mark.parametrize("n", sorted(GUARDS))
def test_text_defects_still_fail_and_the_print_reading_scans(n, divisions):
    written, printed = GUARDS[n]
    assert not check(written).ok and not scan(written, divisions.get(n)).ok
    assert scan(printed, divisions.get(n)).ok


def test_split_form_fails_form_not_metre(divisions):
    written, printed = SPLIT_60
    w, p = scan(written, divisions.get(60)), scan(printed, divisions.get(60))
    assert not w.form_ok and not check(written).ok
    assert p.ok and p.form_ok


def test_aytham_is_not_counted_as_a_letter():
    """Counting ஆய்தம் as a short letter would make 262 scan with a word missing and fail its printed reading."""
    written, printed = GUARDS[262]
    assert not scan(written).ok and scan(printed).ok
    assert scan([x.replace("ஃ", "க") for x in written]).ok


@pytest.mark.parametrize("n,method,licence", [
    (291, "word", "kutriyalikaram not counted"),
    (91, "word", "elision inside a written word"),
    (1143, "word", "au read as one letter (கெள = கௌ)"),
    (368, "rules", "ஆய்தம் syllable joins the seer before it"),
    (42, "rules", "a word divided into two feet"),
    (4, "attested division", "vakaiyuli (division attested in L3)"),
])
def test_each_rule_on_a_kural_that_needs_it(n, method, licence, divisions):
    core = {json.loads(l)["number"]: json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()}
    r = scan(core[n]["lines_ta"], divisions.get(n))
    assert r.ok and r.method == method and licence in r.licences and not check(core[n]["lines_ta"]).ok


def test_no_kural_that_scanned_under_v01_fails_under_v02(divisions):
    core = [json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()]
    worse = [k["number"] for k in core if k["lines_ta"] and check(k["lines_ta"]).ok
             and not scan(k["lines_ta"], divisions.get(k["number"])).ok]
    assert worse == []


def test_muttriyalukaram_and_doubling():
    assert scan(["அன்புஈனும் ஆர்வம் உடைமை அதுஈனும்", "நண்பென்னும் நாடாச் சிறப்பு."]).ok  # 74: அது keeps its u
    assert scan(["மகன்தந்தைக்கு ஆற்றும் உதவி இவன்தந்தை", "என்நோற்றான் கொல்எனும் சொல்."]).ok  # 70: கொல்எனும் -> கொல்லெனும்


@pytest.mark.parametrize("n", [278, 988])
def test_print_division_makes_a_matching_kural_scan(n, divisions):
    """v0.3: the foot breaks printed in the editions (provenance/reports/print_divisions.json) scan these, whose letters match all
    three prints and which no rule or L3 division scans."""
    if not PRINTS.exists():
        pytest.skip("print divisions not built")
    core = {json.loads(l)["number"]: json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()}
    lines = core[n]["lines_ta"]
    assert not scan(lines, [d for d in divisions.get(n, []) if d[0] == "L3"]).ok
    r = scan(lines, divisions.get(n))
    assert r.ok and r.method == "attested division" and any("printed in" in x for x in r.licences)


def test_every_failure_has_a_plain_reason(divisions):
    core = [json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines()]
    for k in core:
        r = scan(k["lines_ta"], divisions.get(k["number"]))
        assert (plain_reason(r) is None) == (r.ok and r.form_ok), k["number"]
