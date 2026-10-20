"""Thirukkural core dataset: schema, structure, validators, release metadata.

Nothing in this package holds kural text. Tamil text is read from data/core, where each field carries its
provenance entry.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_CORE = ROOT / "data" / "core"
PROVENANCE = ROOT / "provenance"
SCHEMA_DIR = PROVENANCE / "schema"
REGISTRY = PROVENANCE / "registry" / "sources.json"
LEDGER = PROVENANCE / "ledger" / "adjudications.jsonl"
LAYERS = PROVENANCE / "layers.json"
REPORTS = PROVENANCE / "reports"

DATASET_VERSION = json.loads((ROOT / "release" / "release.json").read_text(encoding="utf-8"))["version"]
