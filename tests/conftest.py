import json

import pytest

from tkcore import REGISTRY

from .helpers import dumps_jsonl, skeleton_tables


@pytest.fixture
def tables():
    """Structure-only tables, so fault-injection tests start from a clean skeleton."""
    return skeleton_tables()


@pytest.fixture
def registry_doc():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture
def a_hash(registry_doc):
    """A real retrieval hash from the registry: (source_id, sha256)."""
    for s in registry_doc["sources"]:
        for f in s["files"]:
            if f["sha256"]:
                return s["source_id"], f["sha256"]


@pytest.fixture
def write_core(tmp_path):
    def _write(tables, ledger=()):
        core = tmp_path / "core"
        core.mkdir(exist_ok=True)
        for name, rows in tables.items():
            (core / f"{name}.jsonl").write_text(dumps_jsonl(rows), encoding="utf-8")
        led = tmp_path / "ledger.jsonl"
        led.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ledger), encoding="utf-8")
        return core, led
    return _write
