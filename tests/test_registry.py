import json

from tkcore import REGISTRY
from tkcore.schema import errors


def test_registry_entries_valid_and_unique():
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = [s["source_id"] for s in doc["sources"]]
    assert len(ids) == len(set(ids))
    for s in doc["sources"]:
        assert errors("source", s) == [], s["source_id"]


def test_witness_kinds_and_lineage_present():
    doc = {s["source_id"]: s for s in json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]}
    assert doc["yuvaraj"]["lineage_group"] == "L2"
    assert {doc[k]["kind"] for k in ("scan:pope1886", "scan:lazarus1885", "scan:navalar")} == {"scan_witness"}
