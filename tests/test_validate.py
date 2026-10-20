"""The validator suite on the committed core, and on injected faults."""
import json
import unicodedata

import pytest

from tkcore import validate
from tkcore.validate import value_sha256

from .helpers import synthetic_line

LINES = [synthetic_line(4), synthetic_line(3)]


def run(write_core, tables, ledger=(), gate=False):
    core, led = write_core(tables, ledger)
    return validate.run(core, led, gate=gate)


def checks(rep):
    return set(rep.by_check())


def test_committed_core_passes():
    rep = validate.run()
    assert rep.ok, str(rep)


def test_committed_core_gate_reports_only_gate_issues():
    rep = validate.run(gate=True)
    assert checks(rep) <= {"gate", "metre_regression"}


def _atlas_666():
    """Kural 666's readings, read from the committed atlas (no Tamil typed in tests)."""
    rows = [json.loads(l) for l in validate.ATLAS.read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if r["kural_id"] == "tk:0666"]


def test_metre_regression_flags_a_reading_that_breaks_the_metre(write_core, tables, tmp_path):
    rows = _atlas_666()
    from tkcore.prosody import check
    split = lambda t: [x for x in t.replace("<br />", "\n").split("\n") if x.strip()]
    failing = next(r for r in rows if len(split(r["text"])) == 2 and not check(split(r["text"])).ok
                   and not r["status"].startswith(("metrical", "corrupt")))
    scanning = next(r for r in rows if len(split(r["text"])) == 2 and check(split(r["text"])).ok
                    and not r["status"].startswith(("metrical", "corrupt")))
    atlas = tmp_path / "atlas.jsonl"
    atlas.write_text(json.dumps({**scanning, "status": "rejected reading (print comparison)"}, ensure_ascii=False) + "\n", encoding="utf-8")
    k = tables["kurals"][665]
    k["lines_ta"] = [unicodedata.normalize("NFC", x.strip()) for x in split(failing["text"])]
    core, led = write_core(tables)
    rep = validate.run(core, led, gate=True, atlas_path=atlas)
    assert any(c == "metre_regression" and s == "tk:0666" for c, s, _ in rep.errors)
    k["lines_ta"] = [unicodedata.normalize("NFC", x.strip()) for x in split(scanning["text"])]
    core, led = write_core(tables)
    rep = validate.run(core, led, gate=True, atlas_path=atlas)
    assert not any(c == "metre_regression" for c, _, _ in rep.errors)


def test_skeleton_tables_pass(write_core, tables):
    assert run(write_core, tables).ok


def test_count(write_core, tables):
    tables["kurals"].pop()
    assert "count" in checks(run(write_core, tables))


def test_ids_out_of_order(write_core, tables):
    k = tables["kurals"]
    k[0], k[1] = k[1], k[0]
    assert "ids" in checks(run(write_core, tables))


def test_duplicate_id(write_core, tables):
    tables["kurals"][1]["id"] = "tk:0001"
    rep = run(write_core, tables)
    assert "ids" in checks(rep)


def test_structure_mismatch(write_core, tables):
    tables["kurals"][10]["adhikaram_number"] = 1
    tables["adhikarams"][0]["last_kural"] = 11
    rep = run(write_core, tables)
    assert "structure" in checks(rep)


def test_paal_sizes(write_core, tables):
    tables["adhikarams"][38]["paal_number"] = 1
    rep = run(write_core, tables)
    assert "count" in checks(rep)


def test_text_without_provenance(write_core, tables):
    k = tables["kurals"][0]
    k["lines_ta"] = LINES
    assert "provenance_missing" in checks(run(write_core, tables))


def test_provenance_must_cite_registry_hash_and_core_licence(write_core, tables, a_hash):
    sid, sha = a_hash
    k = tables["kurals"][0]
    k["lines_ta"] = LINES
    k["provenance"] = [{"field": "lines_ta", "source_id": sid, "locator": "f#row=0", "source_sha256": sha, "license": "CC0-1.0"}]
    assert run(write_core, tables).ok
    k["provenance"][0]["source_sha256"] = "0" * 64
    assert "provenance_hash" in checks(run(write_core, tables))
    k["provenance"][0].update(source_sha256=sha, source_id="nope")
    assert "provenance_source" in checks(run(write_core, tables))
    k["provenance"][0].update(source_id=sid, license="LicenseRef-AuthorRightsUnverified")
    assert "provenance_license" in checks(run(write_core, tables))


def test_dangling_provenance(write_core, tables, a_hash):
    sid, sha = a_hash
    tables["adhikarams"][0]["provenance"] = [
        {"field": "name_ta", "source_id": sid, "locator": "x", "source_sha256": sha, "license": "LicenseRef-PublicDomain"}]
    assert "provenance_dangling" in checks(run(write_core, tables))


def test_hygiene_and_seer_count_on_text(write_core, tables, a_hash):
    sid, sha = a_hash
    k = tables["kurals"][0]
    k["lines_ta"] = [LINES[0] + chr(0x200D), LINES[1]]
    k["seer_lines_ta"] = [synthetic_line(3), synthetic_line(3)]
    k["provenance"] = [{"field": f, "source_id": sid, "locator": "x", "source_sha256": sha, "license": "CC0-1.0"}
                       for f in ("lines_ta", "seer_lines_ta")]
    rep = run(write_core, tables)
    assert {"forbidden_codepoint", "seer_count"} <= checks(rep)


def test_schema_rejects_wrong_shapes(write_core, tables):
    tables["kurals"][0]["lines_ta"] = [LINES[0]]
    tables["kurals"][1]["text_status"] = "verified"
    tables["kurals"][2]["extra"] = 1
    rep = run(write_core, tables)
    assert "schema" in checks(rep)


def _entry(**kw):
    e = {"ledger_id": "adj:00001", "subject": "tk:0001", "field": "lines_ta", "decision": "chose_candidate",
         "value": LINES, "value_sha256": value_sha256(LINES),
         "candidates": [{"candidate_id": "A", "value": LINES,
                         "sources": [{"source_id": "yuvaraj", "locator": "x", "source_sha256": "a" * 64}]}],
         "evidence": [{"kind": "note", "ref": "test"}], "adjudicator": "Ashwin", "adjudicator_kind": "human",
         "double_keyed": False, "decided_at": "2026-10-17T00:00:00Z", "rationale": "", "supersedes": None}
    e.update(kw)
    return e


def test_ledger_links_and_value_match(write_core, tables, a_hash):
    sid, sha = a_hash
    k = tables["kurals"][0]
    k.update(lines_ta=LINES, text_status="adjudicated", adjudication_ids=["adj:00001"],
             provenance=[{"field": "lines_ta", "source_id": sid, "locator": "adj:00001", "source_sha256": sha, "license": "CC0-1.0"}])
    assert run(write_core, tables, [_entry()]).ok
    assert "ledger_link" in checks(run(write_core, tables, []))
    assert "ledger_mismatch" in checks(run(write_core, tables, [_entry(value=[LINES[1], LINES[0]], value_sha256=value_sha256([LINES[1], LINES[0]]))]))
    assert "ledger_hash" in checks(run(write_core, tables, [_entry(value_sha256="b" * 64)]))


def test_adjudicated_without_ledger_id(write_core, tables):
    tables["kurals"][0]["text_status"] = "adjudicated"
    assert "ledger_link" in checks(run(write_core, tables))


@pytest.mark.parametrize("bad", [
    {"adjudicator_kind": "model"},
    {"decision": "transcribed_from_crop", "double_keyed": False},
    {"decision": "transcribed_from_crop", "double_keyed": True},  # no scan_crop evidence with sha256
    {"decision": "unresolved"},  # unresolved must carry value null
    {"ledger_id": "adj:1"},
    {"subject": "kural 1"},
])
def test_ledger_schema_rules(write_core, tables, bad):
    assert "ledger_schema" in checks(run(write_core, tables, [_entry(**bad)]))


def test_transcription_with_double_key_and_crop_is_valid(write_core, tables):
    e = _entry(subject="tk:0002", decision="transcribed_from_crop", double_keyed=True,
               evidence=[{"kind": "scan_crop", "ref": "scan:lazarus1885 leaf 30", "sha256": "c" * 64}])
    assert "ledger_schema" not in checks(run(write_core, tables, [e]))
