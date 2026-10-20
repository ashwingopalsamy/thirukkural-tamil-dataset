"""Stable ledger ids. provenance/ledger/ids.json maps 'subject|field|decided_at' to a ledger id. No id is ever
renumbered or reused."""
from . import PROVENANCE

IDS = PROVENANCE / "ledger" / "ids.json"


def key(subject, field, decided_at):
    return f"{subject}|{field}|{decided_at}"
