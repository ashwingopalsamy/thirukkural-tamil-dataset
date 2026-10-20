import json

import yaml

from tkcore import ROOT
from tkcore.release import CONFIGS, CROISSANT_OUT, LICENSE_URLS, LICENSES, SCHEMAS


def _front_matter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_hf_card_yaml():
    meta = _front_matter(ROOT / "release" / "hf" / "README.md")
    assert meta["license"] == ["cc0-1.0", "mit", "cc-by-sa-4.0"]
    assert meta["language"] == ["ta", "en"]
    configs = {c["config_name"]: c for c in meta["configs"]}
    assert list(configs) == list(CONFIGS)
    assert configs["kurals"].get("default") is True
    for name, c in configs.items():
        assert c["data_files"] == [{"split": "train", "path": f"data/{name}.parquet"}]


def test_croissant_required_fields_and_record_sets():
    doc = json.loads(CROISSANT_OUT.read_text(encoding="utf-8"))
    assert doc["conformsTo"] == "http://mlcommons.org/croissant/1.1"
    for k in ("@context", "@type", "name", "description", "license", "url", "creator", "datePublished", "version"):
        assert doc.get(k), k
    assert doc["license"] == sorted({LICENSE_URLS[l] for l in LICENSES.values()})
    assert {d["name"].removesuffix("-parquet"): d["license"] for d in doc["distribution"]} == \
        {n: LICENSE_URLS[l] for n, l in LICENSES.items()}
    rs = {r["name"]: [f["name"] for f in r["field"]] for r in doc["recordSet"]}
    assert rs == {n: s.names for n, s in SCHEMAS.items()}
    assert doc["rai:hasSyntheticData"] is False
    for d in doc["distribution"]:
        assert d["contentUrl"].endswith(f"/resolve/v{doc['version']}/data/{d['name'].removesuffix('-parquet')}.parquet")


def test_citation_cff():
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["cff-version"] == "1.2.0" and cff["license"] == ["CC0-1.0", "MIT", "CC-BY-SA-4.0"] and cff["type"] == "dataset"
    assert cff["authors"]


def test_licence_files():
    assert (ROOT / "LICENSE").read_bytes() == (ROOT / "LICENSES" / "CC0-1.0.txt").read_bytes()
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("Creative Commons Legal Code")
