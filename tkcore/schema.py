"""JSON Schema access and the matching Arrow schemas for the Parquet files.

The JSON Schema in provenance/schema/core.schema.json is the contract; the Arrow schemas here
mirror it column for column (tests/test_schema.py checks they stay in sync).
"""
import json
from functools import lru_cache

import pyarrow as pa
from jsonschema import Draft202012Validator

from . import SCHEMA_DIR

PROVENANCE = pa.struct([
    ("field", pa.string()),
    ("source_id", pa.string()),
    ("locator", pa.string()),
    ("source_sha256", pa.string()),
    ("license", pa.string()),
])

KURAL = pa.schema([
    ("id", pa.string()),
    ("number", pa.int16()),
    ("paal_number", pa.int8()),
    ("adhikaram_number", pa.int16()),
    ("position", pa.int8()),
    ("lines_ta", pa.list_(pa.string())),
    ("seer_lines_ta", pa.list_(pa.string())),
    ("text_status", pa.string()),
    ("adjudication_ids", pa.list_(pa.string())),
    ("provenance", pa.list_(PROVENANCE)),
])

ADHIKARAM = pa.schema([
    ("number", pa.int16()),
    ("paal_number", pa.int8()),
    ("iyal_number", pa.int8()),
    ("first_kural", pa.int16()),
    ("last_kural", pa.int16()),
    ("name_ta", pa.string()),
    ("name_en", pa.string()),
    ("provenance", pa.list_(PROVENANCE)),
])

DIVISION = pa.schema([
    ("level", pa.string()),
    ("scheme", pa.string()),
    ("number", pa.int8()),
    ("paal_number", pa.int8()),
    ("first_adhikaram", pa.int16()),
    ("last_adhikaram", pa.int16()),
    ("name_ta", pa.string()),
    ("name_en", pa.string()),
    ("provenance", pa.list_(PROVENANCE)),
])

LAYER_ROW = pa.schema([
    ("kural_id", pa.string()),
    ("layer_id", pa.string()),
    ("text", pa.string()),
    ("lang", pa.string()),
    ("author", pa.string()),
    ("work_title", pa.string()),
    ("rights_status", pa.string()),
    ("license", pa.string()),
    ("source_id", pa.string()),
    ("locator", pa.string()),
    ("source_sha256", pa.string()),
    ("model_generated", pa.bool_()),
])

# table name -> (JSON Schema $defs key, Arrow schema)
TABLES = {
    "kurals": ("kural", KURAL),
    "adhikarams": ("adhikaram", ADHIKARAM),
    "divisions": ("division", DIVISION),
}


@lru_cache(maxsize=None)
def core_schema() -> dict:
    return json.loads((SCHEMA_DIR / "core.schema.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def validator(defn: str) -> Draft202012Validator:
    root = core_schema()
    return Draft202012Validator({"$schema": root["$schema"], "$defs": root["$defs"], "$ref": f"#/$defs/{defn}"})


def errors(defn: str, obj) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(validator(defn).iter_errors(obj), key=lambda e: list(map(str, e.absolute_path)))]
