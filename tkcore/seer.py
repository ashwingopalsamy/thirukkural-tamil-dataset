"""Seer-count check (2 lines, 4 + 3 seers) and the hook for full venba scansion.

The count check is a cheap structural gate on the seer-divided form. It is not
scansion: a line can have 4 + 3 tokens and still fail the meter. Full scansion
(asai, seer, thalai, final foot) plugs in through ProsodyChecker and
reports meter_ok_strict and meter_ok (with licences) separately.
"""
from dataclasses import dataclass
from typing import Protocol

EXPECTED_SEERS = (4, 3)


@dataclass(frozen=True)
class SeerCount:
    counts: tuple[int, ...]

    @property
    def ok(self) -> bool:
        return self.counts == EXPECTED_SEERS


def count_seers(lines) -> SeerCount:
    """Whitespace-delimited units per line. Feed it the seer-divided form, not the
    word-split form: the two differ (kural 254)."""
    return SeerCount(tuple(len(line.split()) for line in lines))


@dataclass(frozen=True)
class ScanResult:
    meter_ok_strict: bool
    meter_ok: bool
    licences: tuple[str, ...] = ()
    detail: str = ""


class ProsodyChecker(Protocol):
    name: str
    version: str

    def scan(self, seer_lines: list[str]) -> ScanResult: ...


_CHECKER: ProsodyChecker | None = None


def register_checker(checker: ProsodyChecker) -> None:
    global _CHECKER
    _CHECKER = checker


def get_checker() -> ProsodyChecker | None:
    """None until the rule-based scanner (port of yaappu logic, MIT) lands."""
    return _CHECKER
