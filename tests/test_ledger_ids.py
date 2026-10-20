"""Ledger ids are permanent (tkcore/ledger_ids.py): no entry's id may change and no id may be reused."""
import hashlib
import json

from tkcore import LEDGER
from tkcore.ledger_ids import IDS, key

# Ids adj:00001 to adj:00071, fingerprinted: they never change.
FROZEN_UPTO, FROZEN_SHA = 71, "d4ddc3cfe3b8042b902d247470d2e9f404d0a640577a469a788bb0d596715279"


def _ids():
    return json.loads(IDS.read_text(encoding="utf-8"))


def test_frozen_ids_never_change():
    items = sorted((k, v) for k, v in _ids().items() if int(v.split(":")[1]) <= FROZEN_UPTO)
    assert len(items) == FROZEN_UPTO
    assert hashlib.sha256(json.dumps(items, ensure_ascii=False).encode()).hexdigest() == FROZEN_SHA


def test_ids_are_unique_and_every_entry_has_its_frozen_id():
    ids = _ids()
    assert len(set(ids.values())) == len(ids)
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        assert ids.get(key(e["subject"], e["field"], e["decided_at"])) == e["ledger_id"], e["ledger_id"]
