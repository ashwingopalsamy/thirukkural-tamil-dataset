"""Source registry: every source_id a provenance entry may cite, read from provenance/registry/sources.json."""
import json

from . import REGISTRY


def load(path=REGISTRY) -> dict:
    return {s["source_id"]: s for s in json.loads(path.read_text(encoding="utf-8"))["sources"]}


def file_hashes(registry: dict) -> dict:
    """source_id -> set of retrieval hashes a provenance entry may cite."""
    return {sid: {f["sha256"] for f in s["files"] if f["sha256"]} for sid, s in registry.items()}
