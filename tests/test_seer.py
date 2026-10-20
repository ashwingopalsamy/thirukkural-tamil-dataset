from tkcore.seer import EXPECTED_SEERS, count_seers, get_checker

from .helpers import synthetic_line


def test_four_plus_three():
    assert EXPECTED_SEERS == (4, 3)
    assert count_seers([synthetic_line(4), synthetic_line(3)]).ok
    assert not count_seers([synthetic_line(3), synthetic_line(4)]).ok
    assert not count_seers([synthetic_line(4), synthetic_line(3), synthetic_line(1)]).ok
    assert count_seers([synthetic_line(5), synthetic_line(3)]).counts == (5, 3)


def test_prosody_hook_is_empty_until_the_scanner_lands():
    assert get_checker() is None
