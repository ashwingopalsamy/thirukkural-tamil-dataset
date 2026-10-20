import json

import tkcore
from tkcore import ROOT, validate
from tkcore import registry as reg

LAYERS = json.loads(tkcore.LAYERS.read_text(encoding="utf-8"))["layers"]
UNVERIFIED = "author-rights-unverified; attributed, non-commercial intent"


def test_layers_manifest_passes():
    rep = validate.Report()
    validate.check_layers({"layers": LAYERS}, reg.load(), rep)
    assert rep.ok, str(rep)


def test_modern_layers_are_present_and_flagged():
    by_id = {l["layer_id"]: l for l in LAYERS}
    for lid in ("shuddhananda-en", "muva-ta", "solomon-pappaiah-ta", "karunanidhi-ta"):
        assert by_id[lid]["rights_status"] == UNVERIFIED
        assert by_id[lid]["license"] == "LicenseRef-AuthorRightsUnverified"
        assert by_id[lid]["declared_license"]  # carrier licence recorded separately


def test_mismatched_licence_is_caught():
    bad = [dict(LAYERS[0], license="CC-BY-SA-4.0")]
    rep = validate.Report()
    validate.check_layers({"layers": bad}, reg.load(), rep)
    assert "layer_license" in rep.by_check()


def test_card_lists_every_layer_and_removal_path():
    card = (ROOT / "release" / "hf" / "README.md").read_text(encoding="utf-8")
    for l in LAYERS:
        assert f"`{l['layer_id']}`" in card
    assert "Rights concerns and removal" in card
