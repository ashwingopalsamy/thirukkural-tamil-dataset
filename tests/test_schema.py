import pyarrow as pa

from tkcore.schema import LAYER_ROW, TABLES, core_schema, errors


def test_arrow_and_json_schema_have_the_same_columns():
    defs = core_schema()["$defs"]
    for name, (defn, arrow) in TABLES.items():
        assert arrow.names == list(defs[defn]["properties"]), name
        assert set(defs[defn]["required"]) == set(arrow.names), name
    assert LAYER_ROW.names == list(defs["layer_row"]["properties"])


def test_provenance_struct_matches_json_schema():
    prov = core_schema()["$defs"]["provenance"]
    struct = TABLES["kurals"][1].field("provenance").type.value_type
    assert [f.name for f in struct] == list(prov["properties"])


def test_text_columns_are_strings_lists():
    k = TABLES["kurals"][1]
    for col in ("lines_ta", "seer_lines_ta"):
        assert k.field(col).type == pa.list_(pa.string())


def test_kural_id_pattern_bounds():
    ok = {"field": "lines_ta", "source_id": "x", "locator": "x", "source_sha256": "a" * 64, "license": "CC0-1.0"}
    assert errors("provenance", ok) == []
    assert errors("provenance", {**ok, "source_sha256": "A" * 64})
    assert errors("provenance", {**ok, "field": "translation"})
    assert errors("kural_id", "tk:1330") == [] and errors("kural_id", "tk:1331") and errors("kural_id", "tk:0000") == []


def test_layer_row_rejects_model_text():
    row = {"kural_id": "tk:0001", "layer_id": "x", "text": "t", "lang": "en", "author": "a", "work_title": "w",
           "rights_status": "public-domain", "license": "LicenseRef-PublicDomain", "source_id": "s", "locator": "l",
           "source_sha256": "a" * 64, "model_generated": False}
    assert errors("layer_row", row) == []
    assert errors("layer_row", {**row, "model_generated": True})
