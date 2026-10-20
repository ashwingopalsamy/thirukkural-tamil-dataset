"""Hygiene checks on codepoint sequences built with chr(); no kural text is typed here."""
import unicodedata

import pytest

from tkcore.tamil import (ALLOWED_IN_KURAL, CONSONANTS, LETTERS, MARKS, VOWELS, check_line, check_lines,
                          check_name)

from .helpers import synthetic_line

KA, AA, VIRAMA, E_SIGN, O_SIGN = chr(0x0B95), chr(0x0BBE), chr(0x0BCD), chr(0x0BC6), chr(0x0BCA)


def codes(issues):
    return {i.code for i in issues}


def test_pinned_sets_are_tamil_letters_and_marks():
    for cp in LETTERS | MARKS:
        name = unicodedata.name(chr(cp))
        assert name.startswith("TAMIL"), hex(cp)
        assert unicodedata.category(chr(cp)) in {"Lo", "Mn", "Mc"}, hex(cp)
    assert len(VOWELS) == 12 and len(CONSONANTS) == 23


def test_clean_synthetic_line_passes():
    assert check_line(synthetic_line(4)) == []
    assert check_line(synthetic_line(3) + ".") == []


def test_not_nfc_detected():
    decomposed = KA + E_SIGN + AA  # U+0B95 U+0BC6 U+0BBE; NFC composes to U+0B95 U+0BCA
    assert unicodedata.normalize("NFC", decomposed) == KA + O_SIGN
    assert "not_nfc" in codes(check_line(decomposed))
    assert "not_nfc" not in codes(check_line(KA + O_SIGN))


@pytest.mark.parametrize("cp", [0x0BA6, 0x0BA7, 0x200C, 0x200D, 0x00A0, 0xFEFF, 0x200B, 0x00AD, 0xE000, 0x0B80, 0x0BE6])
def test_forbidden_codepoints(cp):
    assert "forbidden_codepoint" in codes(check_line(KA + AA + chr(cp) + KA))


@pytest.mark.parametrize("ch", ["a", "1", "\t", ",", "’"])
def test_disallowed_chars(ch):
    assert "disallowed_char" in codes(check_line(KA + ch + KA))


def test_orphan_marks():
    assert "orphan_mark" in codes(check_line(AA + KA))  # vowel sign at start
    assert "orphan_mark" in codes(check_line(KA + AA + VIRAMA))  # virama after vowel sign
    assert "orphan_mark" in codes(check_line(chr(0x0B85) + AA))  # vowel sign after independent vowel
    assert "orphan_mark" in codes(check_line(KA + " " + VIRAMA))


def test_spacing_and_full_stop():
    assert "double_space" in codes(check_line(KA + "  " + KA))
    assert "edge_space" in codes(check_line(" " + KA))
    assert "inner_full_stop" in codes(check_line(KA + "." + KA))
    assert "empty" in codes(check_line(""))


def test_newline_inside_a_line_is_rejected():
    assert "disallowed_char" in codes(check_lines([KA + "\n" + KA, KA]))


def test_name_check_ignores_punctuation_rules_only():
    assert check_name(KA + AA + " " + KA) == []
    assert "forbidden_codepoint" in codes(check_name(KA + chr(0x200C)))


def test_allowed_set_is_letters_marks_space_stop():
    assert ALLOWED_IN_KURAL == LETTERS | MARKS | {0x20, 0x2E}
