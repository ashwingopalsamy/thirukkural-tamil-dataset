"""The one model-generated config: BGE-M3 vectors, shipped as a fixed file and refused once their input changes."""
import copy
import hashlib
import struct

import pyarrow.parquet as pq
import pytest

from tkcore import ROOT, release
from tkcore.release import CONFIGS, EMBED, LICENSES, build_release, build_tables

NPY = ROOT / EMBED["vectors"]["path"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("hf")
    return out, build_release(out)


@pytest.fixture(scope="module")
def tables():
    return build_tables(embeddings=False)


def _npy_rows():
    """The committed file, read here without tkcore.release.read_vectors."""
    raw = NPY.read_bytes()
    hlen = int.from_bytes(raw[8:10], "little")
    assert raw[:8] == b"\x93NUMPY\x01\x00" and "'descr': '<f2'" in raw[10:10 + hlen].decode()
    body, dim = raw[10 + hlen:], EMBED["vectors"]["shape"][1]
    return [struct.unpack_from(f"<{dim}e", body, i * 2 * dim) for i in range(len(body) // (2 * dim))]


def test_vectors_ship_unchanged_with_their_input_hash(built):
    out, res = built
    rows = pq.read_table(out / "data" / "embeddings_bge_m3.parquet").to_pylist()
    kh = {k["id"]: k["text_sha256"] for k in res["tables"]["kurals"]}
    assert [r["kural_number"] for r in rows] == list(range(1, 1331))
    assert all(r["source_text_sha256"] == kh[r["kural_id"]] for r in rows)
    assert all(r["model_generated"] and r["dim"] == 1024 == len(r["vector"]) and r["dtype"] == "float16" for r in rows)
    assert {(r["model_id"], r["model_revision"]) for r in rows} == {(EMBED["model"]["id"], EMBED["model"]["revision"])}
    assert [tuple(r["vector"]) for r in rows] == _npy_rows()  # float16 to float32 is exact
    assert all(abs(sum(x * x for x in r["vector"]) - 1) < 1e-3 for r in rows)
    assert hashlib.sha256(NPY.read_bytes()).hexdigest() == EMBED["vectors"]["sha256"]
    assert EMBED["input"]["kurals_root_sha256"] == res["manifest"]["kurals_root_sha256"]


def test_vectors_are_the_only_model_output_and_hold_no_text(built):
    _, res = built
    model = [n for n, (layer, _, _) in CONFIGS.items() if layer == "model"]
    assert model == ["embeddings_bge_m3"]
    for name, rows in res["tables"].items():
        flags = {r.get("model_generated") for r in rows} - {None}
        assert flags <= ({True} if name in model else {False}), name
    strings = [f for f, t, _ in CONFIGS["embeddings_bge_m3"][2] if str(t) == "string"]
    assert all(r[f].isascii() for r in res["tables"]["embeddings_bge_m3"] for f in strings)  # ids and hashes only
    assert LICENSES["embeddings_bge_m3"] == EMBED["model"]["license"] == "MIT"
    m = res["manifest"]["model_generated"]["embeddings_bge_m3"]
    assert (m["vectors_sha256"], m["model_revision"]) == (EMBED["vectors"]["sha256"], EMBED["model"]["revision"])


def test_release_refuses_vectors_once_their_input_changes(monkeypatch, tables):
    kurals = copy.deepcopy(tables["kurals"])
    kurals[665]["text_sha256"] = hashlib.sha256(b"another reading").hexdigest()  # kural 666 ruled again
    with pytest.raises(SystemExit, match=r"computed on other text for kurals \[666\]"):
        release.embedding_rows(kurals)
    for change, message in (
        (lambda e: e["vectors"].update(sha256="0" * 64), "the vectors file is not the one imported"),
        (lambda e: e["bench"]["input_files_sha256"].update({"data/layers/pope1886-en.jsonl": "0" * 64}),
         "the benchmark read other versions of data/layers/pope1886-en.jsonl"),
        (lambda e: e["model"].update(license="unverified"), "licence 'unverified' is not one this release can carry"),
    ):
        ev = copy.deepcopy(EMBED)
        change(ev)
        monkeypatch.setattr(release, "EMBED", ev)
        with pytest.raises(SystemExit, match=message):
            release.embedding_rows(tables["kurals"])
    monkeypatch.setattr(release, "EMBED", None)
    with pytest.raises(SystemExit, match="embeddings_bge_m3.json is missing"):
        release.embedding_rows(tables["kurals"])


def test_card_scores_come_from_the_evidence(built):
    card = built[1]["card"]
    b, base = EMBED["bench"]["model"], EMBED["bench"]["baseline"]
    for t, label in release.EMBED_TASKS:
        assert (f"| {label} | {b[t]['n']:,} | {b[t]['R@1']:.3f} | {b[t]['R@10']:.3f} | {b[t]['MRR']:.3f} | "
                f"{base[t]['R@1']:.3f} | {base[t]['R@10']:.3f} | {base[t]['MRR']:.3f} |") in card
    # the card's plain claims stay true of the numbers it prints
    assert b["ta->pope"]["R@1"] < 0.5 and b["pope->ta"]["R@1"] < 0.5 and "Tamil to English retrieval is weak" in card
    assert base["misquote"]["R@1"] >= b["misquote"]["R@1"] and "Misquotes need no model" in card
    assert EMBED["bench"]["queries"]["misquote"] == b["misquote"]["n"] == base["misquote"]["n"]
    assert "rests on that line alone" in card and "is not settled." in (built[0] / "LICENSES.md").read_text()

