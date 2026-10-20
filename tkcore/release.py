"""The Hugging Face release: every config, the dataset card, Croissant, per-config licences, a hash manifest.
Deterministic.

  python -m tkcore.release                  dist/hf/ (upload this folder) + release/hf/README.md + release/croissant.json
  python -m tkcore.release --check          fail if the committed card or Croissant differ from what the data gives
  python -m tkcore.release --previous M     changelog against an earlier dist/hf/MANIFEST.json

Configs and their layer:
  kurals, adhikarams, divisions          canonical      data/core/*.jsonl, plus names and hashes joined in
  pope1886_en, drew_lazarus_en           translation    data/layers/*.jsonl with a per-row print check (SHIPPED_LAYERS)
  parimelazhagar_ta                      commentary     data/layers/parimelazhagar-ta.jsonl, MIT (its carrier's terms)
  seer, derived                          derived        tkcore.prosody and tkcore.derived, recomputed here
  scan_locations, ledger, sources        evidence       provenance/reports/collation.json, provenance/ledger/,
                                                        provenance/registry/
  release/configs/<name>.json            any of derived, tasks, agents, evidence: declared by spec, no code change
  embeddings_bge_m3                      model          data/embeddings/bge_m3_ta.npy, checked against
                                                        provenance/reports/embeddings_bge_m3.json; never recomputed
Nothing here writes kural text: every Tamil string in the output is copied from data/core, the ledger or the
registry, or computed from them by a documented deterministic rule. Every number in the card is computed here.
"""
import argparse
import ast
import functools
import hashlib
import json
import shutil
import statistics
import struct
import unicodedata
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from . import DATA_CORE, LAYERS, LEDGER, REGISTRY, REPORTS, ROOT
from . import derived as derived_mod
from . import merkle, prosody, tokens, translit

RELEASE_DIR = ROOT / "release"
META = json.loads((RELEASE_DIR / "release.json").read_text(encoding="utf-8"))
VERSION = META["version"]
CARD_TEMPLATE = RELEASE_DIR / "hf" / "README.template.md"
CARD_OUT = RELEASE_DIR / "hf" / "README.md"
CROISSANT_OUT = RELEASE_DIR / "croissant.json"
CHANGELOG = ROOT / "CHANGELOG.md"
COLLATION = REPORTS / "collation.json"
COLLATION_L3 = REPORTS / "collation_l3.json"
PARIMEL_CHECK = REPORTS / "parimel_check.json"
TOKENIZER_COST = REPORTS / "tokenizer_cost.json"
SCANSION_V02 = REPORTS / "scansion_v02.json"
EMBEDDINGS = REPORTS / "embeddings_bge_m3.json"
PRINT_DIVISIONS = REPORTS / "print_divisions.json"
# Files the embedding benchmark read besides the kural text; the card's scores hold only while they are unchanged.
EMBED_BENCH_INPUTS = ("data/layers/pope1886-en.jsonl", "data/layers/drew-lazarus-en.jsonl",
                      "data/signature/variants_atlas.jsonl")
DIST = ROOT / "dist" / "hf"
CANONICAL_IYAL_SCHEME = "parimelazhagar-9"
EDITIONS = ("pope1886", "lazarus1885", "navalar")

PROV = pa.struct([("field", pa.string()), ("source_id", pa.string()), ("locator", pa.string()),
                  ("source_sha256", pa.string()), ("license", pa.string())])
CAND_SOURCE = pa.struct([("source_id", pa.string()), ("locator", pa.string()), ("source_sha256", pa.string())])

# name -> (layer, description, [(field, arrow type, description)])
CONFIGS = {
    "kurals": ("canonical", "One row per kural, tk:0001 to tk:1330, in Parimelazhagar's order.", [
        ("id", pa.string(), "Permanent id, tk:0001 to tk:1330."),
        ("number", pa.int16(), "Kural number, 1 to 1330."),
        ("paal_number", pa.int8(), "Book (paal), 1 to 3."),
        ("paal_name_ta", pa.string(), "Book name, joined from the divisions config."),
        ("iyal_number", pa.int8(), "Section in Parimelazhagar's nine-iyal grouping (canonical scheme)."),
        ("iyal_name_ta", pa.string(), "Section name, joined from the divisions config."),
        ("adhikaram_number", pa.int16(), "Chapter, 1 to 133."),
        ("adhikaram_name_ta", pa.string(), "Chapter name, joined from the adhikarams config."),
        ("adhikaram_name_en", pa.string(), "English chapter title where printed in Pope 1886, else null."),
        ("position", pa.int8(), "Position in the chapter, 1 to 10."),
        ("lines_ta", pa.list_(pa.string()), "The two lines in Tamil, NFC, in the printed joined (sandhi) form."),
        ("text_ta", pa.string(), "lines_ta joined with a newline, for convenience."),
        ("text_sha256", pa.string(), "sha256 of text_ta as UTF-8. Cite it to pin the exact text."),
        ("text_status", pa.string(), "verified_scan, adjudicated or verified_digital_only (see the card)."),
        ("adjudication_ids", pa.list_(pa.string()), "Ledger rulings that settled this text, if any."),
        ("provenance", pa.list_(PROV), "Every witness that carries this text: source, row, file hash, licence."),
    ]),
    "adhikarams": ("canonical", "The 133 chapters with names, kural ranges and their book and section.", [
        ("number", pa.int16(), "Chapter, 1 to 133."),
        ("name_ta", pa.string(), "Chapter name in Tamil."),
        ("name_en", pa.string(), "English title, only where it is printed in Pope 1886 (public domain); else null."),
        ("paal_number", pa.int8(), "Book, 1 to 3."),
        ("paal_name_ta", pa.string(), "Book name."),
        ("iyal_number", pa.int8(), "Section in the canonical nine-iyal scheme."),
        ("iyal_name_ta", pa.string(), "Section name."),
        ("first_kural", pa.int16(), "First kural number in the chapter."),
        ("last_kural", pa.int16(), "Last kural number in the chapter."),
        ("provenance", pa.list_(PROV), "Witnesses for the name."),
    ]),
    "divisions": ("canonical", "Books (paal) and section schemes (iyal). The canonical scheme is parimelazhagar-9.", [
        ("level", pa.string(), "paal or iyal."),
        ("scheme", pa.string(), "paal; parimelazhagar-9 (canonical); witness-l1l2 (the digital witnesses' grouping)."),
        ("number", pa.int8(), "Number within the scheme."),
        ("paal_number", pa.int8(), "Book the division belongs to."),
        ("first_adhikaram", pa.int16(), "First chapter."),
        ("last_adhikaram", pa.int16(), "Last chapter."),
        ("name_ta", pa.string(), "Name in Tamil."),
        ("canonical", pa.bool_(), "True for the paal rows and the parimelazhagar-9 iyal rows."),
        ("provenance", pa.list_(PROV), "Witnesses for the name."),
    ]),
    "seer": ("derived", "One row per seer (metrical foot) as checker v0.1 reads the text, each printed word one foot: the word, its scansion form, asai and foot name.", [
        ("kural_id", pa.string(), "Kural id."),
        ("kural_number", pa.int16(), "Kural number."),
        ("line", pa.int8(), "1 or 2."),
        ("position", pa.int8(), "Position in the kural, 1 to 7."),
        ("word", pa.string(), "The word as printed in lines_ta, without the closing full stop."),
        ("scansion_form", pa.string(), "The word as scansion reads it after junction rules (tkcore.prosody.join)."),
        ("asai", pa.list_(pa.struct([("kind", pa.string()), ("text", pa.string())])), "Metrical syllables: ner or nirai, with their letters."),
        ("pattern", pa.string(), "The asai kinds joined by spaces, e.g. 'nirai ner ner'."),
        ("foot", pa.string(), "Foot class from the checker: thema, pulima, koovilam, karuvilam, kaai, kani, naal, malar, kaasu, pirappu."),
        ("foot_ta", pa.string(), "Traditional foot name, e.g. புளிமாங்காய். Null when the foot is not a recognised venba foot."),
        ("foot_ok", pa.bool_(), "Whether kural venba allows this foot here."),
    ]),
    "derived": ("derived", "Per-kural results of deterministic rules: the metre check, the search form and transliteration.", [
        ("kural_id", pa.string(), "Kural id."),
        ("kural_number", pa.int16(), "Kural number."),
        ("metre_ok", pa.bool_(), "Checker v0.1: True when the word-split text scans as kural venba with each printed word read as a foot (tkcore.prosody.check). Kept beside scansion_ok so the difference shows per kural."),
        ("word_shape", pa.list_(pa.int8()), "Words per line; venba needs [4, 3]."),
        ("metre_problems", pa.list_(pa.string()), "What checker v0.1 found. A failure is an annotation, never a reason to change text."),
        ("scansion_ok", pa.bool_(), "Checker v0.3 (tkcore.prosody.scan): True when these letters scan as kural venba with the regrouping traditional scansion uses. Not rules alone in every case: where scansion_method is 'attested division', the foot boundaries come from Tamil Wikisource's Parimelazhagar text (L3) or a printed edition (scansion_licences says which)."),
        ("scansion_method", pa.string(), "How v0.3 scanned it: word (printed words as feet), rules (an ஆய்தம் syllable joins the foot before it, or a word is divided into two feet), attested division (foot boundaries from Tamil Wikisource's Parimelazhagar text, L3, or from the foot breaks printed in an edition; the letters are this dataset's), or none."),
        ("scansion_licences", pa.list_(pa.string()), "Rules v0.3 applied, e.g. 'kutriyalikaram not counted', 'elision inside a written word', 'au read as one letter (கெள = கௌ)'."),
        ("scansion_problems", pa.list_(pa.string()), "What v0.3 found when the kural does not scan. An annotation, never a reason to change text."),
        ("scansion_note", pa.string(), "Why, in plain words, when the kural does not scan or is written split (form_ok false); null otherwise."),
        ("form_ok", pa.bool_(), "False when a line has more printed words than feet (4, 3): the text is written split where the print joins words."),
        ("checker", pa.string(), "Name and version of the v0.1 checker behind metre_ok and the seer config; the scansion_ fields come from tkcore.prosody.scan (v0.3)."),
        ("search_lines_ta", pa.list_(pa.string()), "lines_ta with rule C13 (ெள to ௌ) so Tamil search finds கௌ; equals lines_ta elsewhere."),
        ("search_rule", pa.string(), "C13 where the search form differs, else null."),
        ("translit_iso15919", pa.list_(pa.string()), "search_lines_ta in ISO 15919, letter by letter (tkcore.translit). A reading aid, not the text."),
        ("translit_plain", pa.list_(pa.string()), "translit_iso15919 with diacritics removed, for ASCII search."),
        ("letters_per_line", pa.list_(pa.int8()), "Tamil letters (aksharas) per line of lines_ta."),
    ]),
    "scan_locations": ("evidence", "Where each kural is printed in three editions scanned on archive.org: page image and box. Positions only; no text comes from this config.", [
        ("kural_id", pa.string(), "Kural id."),
        ("kural_number", pa.int16(), "Kural number."),
        ("edition", pa.string(), "pope1886, lazarus1885 or navalar."),
        ("source_id", pa.string(), "Registry id of the scan (sources config)."),
        ("archive_item", pa.string(), "archive.org item identifier."),
        ("leaf", pa.int16(), "Leaf index: the number in the JP2 file name."),
        ("image_file", pa.string(), "Path of the page image inside the item's _jp2.zip."),
        ("bbox", pa.list_(pa.int32()), "Box around the kural in that image's pixels: x0, y0, x1, y1."),
        ("located_confidently", pa.bool_(), "True when the box is within 3 leaves of the expected page and its text distance is under the 90th percentile."),
        ("ocr_distance_ratio", pa.float32(), "Edit distance per letter between the machine-read text in the box and the kural. Lower is closer."),
    ]),
    "ledger": ("evidence", "Every recorded ruling on text or names: the candidate readings with their sources, the evidence, who decided and when.", [
        ("ledger_id", pa.string(), "adj:NNNNN."),
        ("subject", pa.string(), "What was ruled on: a kural id, adhikaram:N or iyal:scheme:N."),
        ("field", pa.string(), "lines_ta or name_ta."),
        ("decision", pa.string(), "chose_candidate, transcribed_from_crop (typed from the print, double-keyed) or structure_ruling."),
        ("value", pa.list_(pa.string()), "The ruled value: two lines for a kural, one element for a name."),
        ("value_sha256", pa.string(), "sha256 of the ruled value as recorded in provenance/ledger/adjudications.jsonl."),
        ("candidates", pa.list_(pa.struct([("candidate_id", pa.string()), ("value", pa.list_(pa.string())),
                                            ("sources", pa.list_(CAND_SOURCE))])), "Readings that were on the table, each with the witnesses that carry it."),
        ("evidence", pa.list_(pa.struct([("kind", pa.string()), ("ref", pa.string()), ("sha256", pa.string())])), "Evidence cited: kind (scan_crop, print_comparison, wikisource_revid, scansion, note), reference and hash."),
        ("adjudicator", pa.string(), "Who decided."),
        ("adjudicator_kind", pa.string(), "Always human."),
        ("double_keyed", pa.bool_(), "True when the value was typed from the print twice and the keyings matched."),
        ("decided_at", pa.string(), "UTC time of the ruling, ISO 8601."),
        ("rationale", pa.string(), "The reason recorded with the ruling."),
        ("supersedes", pa.string(), "An earlier ruling this one replaces, if any."),
    ]),
    "sources": ("evidence", "Every source the build identified: the witnesses cited in provenance, and two listed for "
                "completeness that no row cites (tamilthagaval, identified but not retrieved; ref:wikipedia-tirukkural, "
                "consulted for iyal ranges only, no text copied). Each with what it is, its lineage group, declared "
                "licence and retrieved file hashes (null where a file was not retrieved).", [
        ("source_id", pa.string(), "Id used in provenance."),
        ("title", pa.string(), "Name of the source."),
        ("kind", pa.string(), "digital_witness, scan_witness, reference, or not_retrieved (identified, data not "
                              "retrieved, not a witness)."),
        ("lineage_group", pa.string(), "Sources in the same group descend from one upstream."),
        ("url", pa.string(), "Where it was retrieved."),
        ("revision", pa.string(), "Commit or revision retrieved."),
        ("declared_license", pa.string(), "The carrier's own declared licence. It does not license public-domain text inside it."),
        ("rights_note", pa.string(), "Notes on rights."),
        ("files", pa.list_(pa.struct([("path", pa.string()), ("sha256", pa.string()), ("size", pa.int64()),
                                       ("retrieved_at", pa.string())])), "Retrieved files with sha256, size and time."),
    ]),
}

# ---------------------------------------------------------------- layers that ship

# The layers whose authors are long dead ship with the core, each as its own config. Every other layer in
# provenance/layers.json (modern commentaries and translations) stays out of every release, and
# scripts/hf_publish.py refuses any file this table does not name.
SHIPPED_LAYERS = {"pope1886_en": ("pope1886-en", "translation"), "drew_lazarus_en": ("drew-lazarus-en", "translation"),
                  "aiyar1916_en": ("aiyar1916-en", "translation"),
                  "parimelazhagar_ta": ("parimelazhagar-ta", "commentary"),
                  "parimelazhagar_ta_sa": ("parimelazhagar-ta-wikisource", "commentary")}
# A layer that holds only the rows another layer withholds, from a carrier under another licence: layer -> that layer.
# Its rows must be withheld there, in kural order, and each must pass its print check (provenance/reports/parimel_patch.jsonl).
PARTIAL_LAYERS = {"parimelazhagar-ta-wikisource": "parimelazhagar-ta"}
PARIMEL_PATCH = REPORTS / "parimel_patch.jsonl"
PATCH_CLOSE, PATCH_FAR = 0.40, 0.60  # a row is used when distance <= CLOSE and control >= FAR
# layers read off a scanned book, checked by a page-check report instead of a carrier column
SCAN_LAYERS = {"aiyar1916-en": REPORTS / "aiyar1916_page_check.json"}
LAYER_DIR = ROOT / "data" / "layers"
QUARANTINE = REPORTS / "layer_quarantine.json"
PAGE_CHECK = REPORTS / "english_page_check.json"
PRINT_NOTES = REPORTS / "english_print_notes.json"
# layer_id -> edition whose printed page each row is checked on
PRINT_CHECK = {"pope1886-en": "pope1886", "drew-lazarus-en": "lazarus1885"}
PAGE_METHOD = ("share of the row's word 3-grams on the kural's own printed leaf or the next, in the edition's English "
               "OCR")
PARIMEL_METHOD = ("share of the row's Tamil 5-grams found on the Lazarus 1885 commentary page; 20-kural spot check, "
                  "no pass mark")
LAYER_FIELDS = [
    ("kural_id", pa.string(), "Kural id; joins kurals.id."),
    ("kural_number", pa.int16(), "Kural number."),
    ("text", pa.string(), "The translation or commentary, copied verbatim from the carrier column. Never edited. Null "
                          "where the carrier row is withheld (coverage missing)."),
    ("coverage", pa.string(), "complete; partial (part of the text is missing in the carrier); missing (the carrier row "
                              "is withheld, for example because it repeats another kural's text)."),
    ("coverage_note", pa.string(), "Why a row is partial or missing (provenance/reports/layer_quarantine.json); null when complete."),
    ("lang", pa.string(), "Language of text (BCP 47)."),
    ("author", pa.string(), "Who wrote this row. For the Drew/Lazarus layer, the translator of this kural."),
    ("work_title", pa.string(), "The work the text comes from, as far as it is identified."),
    ("source_id", pa.string(), "The dataset that carries the text; joins sources.source_id."),
    ("locator", pa.string(), "File, row and column in that dataset."),
    ("source_sha256", pa.string(), "sha256 of the carrier file as retrieved."),
    ("carrier_license", pa.string(), "The carrier's declared licence (SPDX id)."),
    ("rights", pa.string(), "Rights in the text itself, for the author and, where different, the transcription."),
    ("print_edition", pa.string(), "Printed edition the row was compared with, or null."),
    ("print_leaf", pa.int16(), "The scan leaf of that edition the row was compared on: for the English layers, where "
                               "the kural is printed (located by its Tamil, scan_locations); for parimelazhagar_ta_sa, "
                               "where its commentary matched. Null where it was not located."),
    ("print_check", pa.string(), "How the row was compared with that edition."),
    ("print_match_share", pa.float32(), "Result of print_check, 0 to 1. Null where the row was not compared."),
    ("print_match", pa.bool_(), "English layers: true when at least 60% of the row's 3-grams are on the kural's own "
                                "printed page. False marks a row to check on the page (damaged scan text, a mislocated page, "
                                "or a different text). parimelazhagar_ta_sa: true for every row, since a row ships only "
                                "when it passes its check. Null where no pass mark applies, the page was not located, "
                                "or the scan has no page for the kural (see print_note)."),
    ("print_note", pa.string(), "English layers: the known cause where print_match is false or the page is missing from "
                                "the scan (provenance/reports/english_print_notes.json); null otherwise."),
    ("book_match_share", pa.float32(), "English layers: the same share against the whole edition's machine-read text. High here but "
                                       "low on the page points to a mislocated page or another kural's text."),
    ("text_flags", pa.list_(pa.string()), "Deterministic flags on the text: digits, html (a tag such as <br>), "
                                          "virama_after_vowel. A flag never changes the text."),
    ("model_generated", pa.bool_(), "Always false. No row is written by a model."),
]


SCAN_FIELDS = [
    ("tier", pa.string(), "How the text was checked: ocr_letters_punct_agree, ocr_letters_agree, ocr_auto_resolved, ocr_rule_resolved, "
                          "ocr_se_resolved, adjudicated (settled against the page image), typed_edition_only (the scan lacks the kural; "
                          "text from the Standard Ebooks typing). No tier is a proofreading against the print; filter to the tiers you need."),
    ("pdf_page", pa.int16(), "Page of the scanned PDF the text was read from; null for typed_edition_only."),
]


def _layer_meta() -> dict:
    return {l["layer_id"]: l for l in json.loads(LAYERS.read_text(encoding="utf-8"))["layers"]}


for _name, (_lid, _kind) in SHIPPED_LAYERS.items():
    _l = _layer_meta()[_lid]
    CONFIGS[_name] = (_kind, f"{_l['author']}: {_l['work_title']}. " + (
        f"One row for each kural it carries; licensed {_l['license']}, so kept apart from the other rows of the work."
        if _lid in PARTIAL_LAYERS else "One row per kural."), LAYER_FIELDS + SCAN_FIELDS if _lid in SCAN_LAYERS else LAYER_FIELDS)

# ---------------------------------------------------------------- signature configs, declared in release/configs/

SPEC_DIR = RELEASE_DIR / "configs"
SPEC_LAYERS = ("derived", "evidence", "tasks", "agents")
SCALARS = {"string": pa.string(), "bool": pa.bool_(), "int8": pa.int8(), "int16": pa.int16(), "int32": pa.int32(),
           "int64": pa.int64(), "float32": pa.float32(), "float64": pa.float64()}


def arrow_type(t) -> pa.DataType:
    """Field types in a spec: a scalar name, {"list": T}, or {"struct": [{"name", "type"}, ...]}."""
    if isinstance(t, str):
        return SCALARS[t]
    if set(t) == {"list"}:
        return pa.list_(arrow_type(t["list"]))
    if set(t) == {"struct"}:
        return pa.struct([(f["name"], arrow_type(f["type"])) for f in t["struct"]])
    raise ValueError(f"unknown field type {t!r}")


def share_alike_only(r: dict) -> bool:
    """An atlas reading whose every carrier is CC-BY-SA (Chandrasekar's metrical forms, Wikisource corrections). The
    canonical reading is the kural text itself, public domain and already CC0 in `kurals`, so it never counts."""
    lic = r["carrier_licences"]
    return r["status"] != "canonical" and bool(lic) and all(c.startswith("CC-BY-SA") for c in lic)


@functools.cache
def _sa_reading_ids() -> frozenset[str]:
    return frozenset(r["reading_id"] for r in _jsonl(ROOT / "data" / "signature" / "variants_atlas.jsonl")
                     if share_alike_only(r))


def no_share_alike_reading(r: dict) -> bool:
    """A task whose prompt is an attested reading carried only under CC-BY-SA stays out of the CC0 tasks config. The
    reading id is the last parenthesised part of the task's note."""
    note = r.get("note") or ""
    return not (note.endswith(")") and note.rsplit("(", 1)[1][:-1] in _sa_reading_ids())


ROW_FILTERS = {"share_alike_only": share_alike_only, "not_share_alike_only": lambda r: not share_alike_only(r),
               "no_share_alike_reading": no_share_alike_reading}
LICENSE_URLS = {"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
                "MIT": "https://opensource.org/license/mit",
                "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/"}


def load_specs(spec_dir: Path = SPEC_DIR) -> dict[str, dict]:
    """release/configs/<name>.json declares one more config: its layer, description, licence, data file under data/,
    an optional row filter (a name in ROW_FILTERS), fields, key and references. The release builds it with no change
    to this file. A field with "from_object": true turns a JSON object into a list of {key, value} structs. Translations
    and commentary cannot be declared here; only SHIPPED_LAYERS carry them."""
    specs = {}
    for path in sorted(spec_dir.glob("*.json")):
        sp = json.loads(path.read_text(encoding="utf-8"))
        name, data = sp["name"], (ROOT / sp["data"]).resolve()
        problems = [m for m, bad in (
            ("file name must be <name>.json", path.stem != name),
            ("name must be lower_snake_case", not name.replace("_", "").isalnum() or not name.islower()),
            ("name taken", name in CONFIGS),
            (f"layer must be one of {SPEC_LAYERS}", sp["layer"] not in SPEC_LAYERS),
            ("data must be a .jsonl under data/", data.suffix != ".jsonl" or (ROOT / "data") not in data.parents),
            (f"license must be one of {sorted(LICENSE_URLS)}", sp.get("license", "CC0-1.0") not in LICENSE_URLS),
            (f"rows must be one of {sorted(ROW_FILTERS)}", sp.get("rows") not in (None, *ROW_FILTERS)),
        ) if bad]
        if problems:
            raise SystemExit(f"{path.name}: {'; '.join(problems)}")
        specs[name] = sp
    return specs


SPECS = load_specs()
for _name, _sp in SPECS.items():
    CONFIGS[_name] = (_sp["layer"], _sp["description"],
                      [(f["name"], arrow_type(f["type"]), f["description"]) for f in _sp["fields"]])

# ---------------------------------------------------------------- model-generated vectors

# The one config a model computed. Its rows are numbers, never text, and say model_generated true. The vectors are a
# fixed file; the build only checks and copies them (embedding_rows).
EMBED = json.loads(EMBEDDINGS.read_text(encoding="utf-8")) if EMBEDDINGS.exists() else None
CONFIGS["embeddings_bge_m3"] = ("model", (
    "Model-generated: one vector per kural, computed from kurals.text_ta by BAAI/bge-m3 at a pinned revision. Numbers, "
    "not text. For search and clustering; never a source for a kural's words."), [
    ("kural_id", pa.string(), "Kural id; joins kurals.id."),
    ("kural_number", pa.int16(), "Kural number."),
    ("model_id", pa.string(), "The model, as named on the Hugging Face Hub."),
    ("model_revision", pa.string(), "The model's Hub commit that computed the vector."),
    ("dim", pa.int16(), "Length of vector."),
    ("dtype", pa.string(), "Precision the vector was saved in: float16. Each value is stored here as float32 without "
                           "change, for tools that cannot read float16."),
    ("source_field", pa.string(), "The text that was embedded: kurals.text_ta, with no prompt or prefix."),
    ("source_text_sha256", pa.string(), "sha256 of that input string, equal to kurals.text_sha256. The build refuses "
                                        "the vectors when they differ."),
    ("vector", pa.list_(pa.float32()), "The embedding, L2-normalised: compare two kurals by dot product."),
    ("model_generated", pa.bool_(), "Always true: a model computed this row."),
])

LICENSES = {**{n: "CC0-1.0" for n in CONFIGS}, "parimelazhagar_ta": "MIT", "parimelazhagar_ta_sa": "CC-BY-SA-4.0",
            **{n: sp.get("license", "CC0-1.0") for n, sp in SPECS.items()},
            "embeddings_bge_m3": EMBED["model"]["license"] if EMBED else "unverified"}
LAYER_ORDER = ("canonical", "translation", "commentary", "derived", "tasks", "agents", "model", "evidence")
CONFIGS = dict(sorted(CONFIGS.items(), key=lambda kv: LAYER_ORDER.index(kv[1][0])))  # stable within a layer
# Keys and references for the configs added above; tkcore.croissant merges them with the core ones.
EXTRA_KEYS = {**{n: ["kural_id"] for n in SHIPPED_LAYERS}, **{n: sp["key"] for n, sp in SPECS.items()},
              "embeddings_bge_m3": ["kural_id"]}
EXTRA_REFERENCES = {**{(n, f): to for n in SHIPPED_LAYERS for f, to in (("kural_id", "kurals/id"),
                                                                        ("source_id", "sources/source_id"))},
                    **{(n, f): to for n, sp in SPECS.items() for f, to in sp.get("references", {}).items()},
                    ("embeddings_bge_m3", "kural_id"): "kurals/id"}
SCHEMAS = {name: pa.schema([(f, t) for f, t, _ in fields]) for name, (_, _, fields) in CONFIGS.items()}

FOOT_TA = {("ner", "ner"): "தேமா", ("nirai", "ner"): "புளிமா", ("ner", "nirai"): "கூவிளம்",
           ("nirai", "nirai"): "கருவிளம்"}
FINAL_TA = {"naal": "நாள்", "malar": "மலர்", "kaasu": "காசு", "pirappu": "பிறப்பு"}


def foot_ta(seer) -> str | None:
    kinds = tuple(k for k, _ in seer.asai)
    if seer.final:
        return FINAL_TA.get(seer.name)
    if len(kinds) == 2:
        return FOOT_TA[kinds]
    if len(kinds) == 3:
        return FOOT_TA[kinds[:2]] + ("ங்காய்" if kinds[2] == "ner" else "ங்கனி")
    return None


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def text_sha256(lines: list[str]) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", "\n".join(lines)).encode("utf-8")).hexdigest()


def build_tables(core: Path = DATA_CORE, embeddings: bool = True) -> dict[str, list[dict]]:
    kurals, adhikarams, divisions = (_jsonl(core / f"{n}.jsonl") for n in ("kurals", "adhikarams", "divisions"))
    paal = {d["number"]: d["name_ta"] for d in divisions if d["level"] == "paal"}
    iyal = {d["number"]: d["name_ta"] for d in divisions if d["level"] == "iyal" and d["scheme"] == CANONICAL_IYAL_SCHEME}
    adh = {a["number"]: a for a in adhikarams}

    t: dict[str, list[dict]] = {n: [] for n in CONFIGS}
    for k in kurals:
        a = adh[k["adhikaram_number"]]
        t["kurals"].append({
            "id": k["id"], "number": k["number"], "paal_number": k["paal_number"], "paal_name_ta": paal[k["paal_number"]],
            "iyal_number": a["iyal_number"], "iyal_name_ta": iyal[a["iyal_number"]],
            "adhikaram_number": k["adhikaram_number"], "adhikaram_name_ta": a["name_ta"],
            "adhikaram_name_en": a["name_en"], "position": k["position"],
            "lines_ta": k["lines_ta"], "text_ta": "\n".join(k["lines_ta"]), "text_sha256": text_sha256(k["lines_ta"]),
            "text_status": k["text_status"], "adjudication_ids": k["adjudication_ids"], "provenance": k["provenance"]})
    for a in adhikarams:
        t["adhikarams"].append({**{f: a[f] for f in ("number", "name_ta", "name_en", "paal_number", "iyal_number", "first_kural",
                                                       "last_kural", "provenance")},
                                "paal_name_ta": paal[a["paal_number"]], "iyal_name_ta": iyal[a["iyal_number"]]})
    for d in divisions:
        t["divisions"].append({**d, "canonical": d["level"] == "paal" or d["scheme"] == CANONICAL_IYAL_SCHEME})

    search = {r["id"]: r for r in derived_mod.build()}
    atlas = ROOT / "data" / "signature" / "variants_atlas.jsonl"
    prints = PRINT_DIVISIONS if PRINT_DIVISIONS.exists() else None
    attested = prosody.attested_divisions(atlas, prints) if atlas.exists() else {}
    for k in kurals:
        r = prosody.check(k["lines_ta"])
        sc = prosody.scan(k["lines_ta"], attested.get(k["number"]))
        words = [ln.replace(".", " ").split() for ln in k["lines_ta"]]
        line_of = [i + 1 for i, ws in enumerate(words) for _ in ws]
        printed = [w for ws in words for w in ws]
        assert len(printed) == len(r.seers), k["id"]
        for pos, (w, s) in enumerate(zip(printed, r.seers), start=1):
            t["seer"].append({"kural_id": k["id"], "kural_number": k["number"], "line": line_of[pos - 1], "position": pos,
                              "word": w, "scansion_form": s.word, "asai": [{"kind": a, "text": x} for a, x in s.asai],
                              "pattern": " ".join(a for a, _ in s.asai), "foot": s.name if s.ok else None,
                              "foot_ta": foot_ta(s) if s.ok else None, "foot_ok": s.ok})
        sr = search[k["id"]]
        t["derived"].append({"kural_id": k["id"], "kural_number": k["number"], "metre_ok": r.ok,
                             "word_shape": [len(ws) for ws in words], "metre_problems": r.problems,
                             "scansion_ok": sc.ok, "scansion_method": sc.method, "scansion_licences": sc.licences,
                             "scansion_problems": sc.problems, "scansion_note": prosody.plain_reason(sc), "form_ok": sc.form_ok,
                             "checker": f"{prosody.VenbaChecker.name} {prosody.VenbaChecker.version}",
                             "search_lines_ta": sr["text_search"], "search_rule": sr["rule"],
                             "translit_iso15919": [translit.iso15919(x) for x in sr["text_search"]],
                             "translit_plain": [translit.plain(x) for x in sr["text_search"]],
                             "letters_per_line": [derived_mod.letters(x) for x in k["lines_ta"]]})

    by_number = {k["number"]: k["id"] for k in kurals}
    for c in sorted(json.loads(COLLATION.read_text(encoding="utf-8")), key=lambda c: c["kural"]):
        for ed in EDITIONS:
            s = c["scans"].get(ed)
            if not s or not s.get("bbox"):
                continue
            item, image_file = s["image"].split(":", 1)
            t["scan_locations"].append({
                "kural_id": by_number[c["kural"]], "kural_number": c["kural"], "edition": ed, "source_id": f"scan:{ed}",
                "archive_item": item.split("/")[0], "leaf": s["leaf"], "image_file": image_file,
                "bbox": s["bbox"], "located_confidently": s["usable"], "ocr_distance_ratio": s["ratio"]})

    as_list = lambda v: v if isinstance(v, list) else [v]  # noqa: E731
    for l in _jsonl(LEDGER):
        t["ledger"].append({**l, "value": as_list(l["value"]),
                            "candidates": [{**c, "value": as_list(c["value"])} for c in l["candidates"]],
                            "evidence": [{"kind": e["kind"], "ref": e["ref"], "sha256": e.get("sha256")} for e in l["evidence"]]})

    for s in json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]:
        t["sources"].append({f: s.get(f) for f in SCHEMAS["sources"].names})

    ids = [k["id"] for k in kurals]
    carrier_license = {s["source_id"]: s["declared_license"] for s in t["sources"]}
    for name, (lid, _) in SHIPPED_LAYERS.items():
        t[name] = layer_rows(lid, ids, carrier_license)
    for name, sp in SPECS.items():
        t[name] = spec_rows(sp)
    if embeddings:  # False: every table but the vectors
        t["embeddings_bge_m3"] = embedding_rows(t["kurals"])
    return t


def spec_rows(sp: dict) -> list[dict]:
    rows = _jsonl(ROOT / sp["data"])
    if sp.get("rows"):
        rows = [r for r in rows if ROW_FILTERS[sp["rows"]](r)]
    want = [f["name"] for f in sp["fields"]]
    extra = {k for r in rows for k in r} - set(want)
    if extra:
        raise SystemExit(f"{sp['data']}: keys {sorted(extra)} are not fields of release/configs/{sp['name']}.json")
    objects = {f["name"]: [g["name"] for g in f["type"]["list"]["struct"]] for f in sp["fields"] if f.get("from_object")}
    out = []
    for r in rows:
        row = {f: r.get(f) for f in want}
        for f, (k, v) in objects.items():
            row[f] = [{k: key, v: val} for key, val in (row[f] or {}).items()]
        out.append(row)
    return out


TAMIL_VOWEL = "\u0b85-\u0b94\u0bbe-\u0bcc"


def text_flags(text: str) -> list[str]:
    import re
    flags = []
    if re.search("[0-9\u0be6-\u0bef]", text):
        flags.append("digits")
    if re.search("<[a-zA-Z/][^>]*>", text):
        flags.append("html")
    if re.search(f"[{TAMIL_VOWEL}]\u0bcd", text):
        flags.append("virama_after_vowel")
    return flags


def _translator(author: str, n: int) -> str:
    """'W. H. Drew (kurals 1-630); John Lazarus (631-1330)' -> the name whose range holds n; else author as is."""
    import re
    for name, lo, hi in re.findall(r"\s*([^;(]+?)\s*\((?:kurals )?(\d+)-(\d+)\)", author):
        if int(lo) <= n <= int(hi):
            return name
    return author


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quarantine() -> dict[tuple[str, str], dict]:
    """(layer_id, kural_id) -> the entry in provenance/reports/layer_quarantine.json."""
    return {(e["layer_id"], e["kural_id"]): e for e in json.loads(QUARANTINE.read_text(encoding="utf-8"))["rows"]}


def duplicate_texts(rows: list[dict]) -> list[list[str]]:
    """Groups of kural ids whose text is identical (NFC, outer whitespace ignored). A carrier that repeats a neighbour's
    cell is the defect this catches: such a row passes any check that looks for its text anywhere in the book."""
    by: dict[str, list[str]] = {}
    for r in rows:
        t = unicodedata.normalize("NFC", r["text"] or "").strip()
        if t:
            by.setdefault(t, []).append(r["kural_id"])
    return [ids for ids in by.values() if len(ids) > 1]


def print_notes() -> dict[tuple[str, int], dict]:
    """(layer_id, kural number) -> the entry in provenance/reports/english_print_notes.json."""
    return {(e["layer_id"], n): e for e in json.loads(PRINT_NOTES.read_text(encoding="utf-8"))["rows"] for n in e["kurals"]}


def check_layer(lid: str, carrier: list[dict], shipped: list[dict]) -> None:
    """Release gate for a shipped layer: quarantine entries match the carrier text they were decided on, no two shipped
    rows carry the same text, and the English page check was run on exactly the text that ships."""
    problems = [f"{k}: carrier text changed since the quarantine entry" for (l, k), e in quarantine().items()
                if l == lid and _text_sha(next(r["text"] for r in carrier if r["kural_id"] == k)) != e["carrier_text_sha256"]]
    problems += [f"same text on {', '.join(ids)}" for ids in duplicate_texts(shipped)]
    if lid in PRINT_CHECK:
        checked = json.loads(PAGE_CHECK.read_text(encoding="utf-8"))["layers"][lid]["rows"]
        problems += [f"{r['kural_id']}: page check is for other text"
                     for r in carrier if checked.get(str(int(r["kural_id"][3:])), {}).get("text_sha256") != _text_sha(r["text"] or "")]
        mark = json.loads(PAGE_CHECK.read_text(encoding="utf-8"))["threshold"]
        problems += [f"tk:{n:04d}: print note on a row that passes its page check" for (l, n) in print_notes()
                     if l == lid and (checked[str(n)]["page_share"] or 0) >= mark]
    if problems:
        raise SystemExit(f"data/layers/{lid}.jsonl: " + "; ".join(problems[:10]) + (" ..." if len(problems) > 10 else ""))


def parimel_patch() -> dict[str, dict]:
    """kural_id -> its entry in provenance/reports/parimel_patch.jsonl."""
    return {e["kural_id"]: e for e in _jsonl(PARIMEL_PATCH)}


SCAN_METHOD = ("the row's letters and digits found inside a whole-page machine reading of its own PDF page by a second "
               "engine; not a proofreading")


def scan_layer_rows(lid: str, ids: list[str], carrier_license: dict) -> list[dict]:
    """A layer read off a scan: one row per kural, each with its tier and page from its page-check report, which must
    have been made on exactly the text that ships."""
    meta = _layer_meta()[lid]
    rows = _jsonl(LAYER_DIR / f"{lid}.jsonl")
    if [r["kural_id"] for r in rows] != ids or {r["layer_id"] for r in rows} != {lid} or any(r["model_generated"] for r in rows):
        raise SystemExit(f"data/layers/{lid}.jsonl: not one row per kural in order, or a row from another layer")
    side = json.loads(SCAN_LAYERS[lid].read_text(encoding="utf-8"))["rows"]
    problems = [f"{r['kural_id']}: page check is for other text" for r in rows
                if side[str(int(r["kural_id"][3:]))]["text_sha256"] != _text_sha(r["text"])]
    problems += [f"same text on {', '.join(ids_)}" for ids_ in duplicate_texts(rows)]
    if problems:
        raise SystemExit(f"data/layers/{lid}.jsonl: " + "; ".join(problems[:10]) + (" ..." if len(problems) > 10 else ""))
    out = []
    for r in rows:
        n = int(r["kural_id"][3:])
        c = side[str(n)]
        typed = c["status"] == "typed_edition_only"
        out.append({"kural_id": r["kural_id"], "kural_number": n, "text": r["text"], "coverage": "complete", "coverage_note": None,
                    "lang": r["lang"], "author": meta["author"], "work_title": r["work_title"], "source_id": r["source_id"],
                    "locator": r["locator"], "source_sha256": r["source_sha256"], "carrier_license": carrier_license[r["source_id"]],
                    "rights": ("translator d. 1925, published 1916: public domain by date; typed edition, its contributions "
                               "dedicated CC0 1.0; not in the scan" if typed else
                               "translator d. 1925, published 1916: public domain by date; the text is OCR of a scan, "
                               "see tier; this project's reading, rules and adjudication are dedicated CC0-1.0; carrier_license is empty "
                               "because the scan declares no licence"),
                    "print_edition": None if typed else "aiyar1916", "print_leaf": None if typed else c["pdf_page"],
                    "print_check": None if typed else SCAN_METHOD, "print_match_share": None,
                    "print_match": None if typed else c["print_match"],
                    "print_note": "not in the scanned copy of the 1916 book; text from the Standard Ebooks typing" if typed else None,
                    "book_match_share": None, "text_flags": text_flags(r["text"]), "model_generated": False,
                    "tier": c["status"], "pdf_page": None if typed else c["pdf_page"]})
    return out


def layer_rows(lid: str, ids: list[str], carrier_license: dict) -> list[dict]:
    if lid in SCAN_LAYERS:
        return scan_layer_rows(lid, ids, carrier_license)
    meta = _layer_meta()[lid]
    rows = _jsonl(LAYER_DIR / f"{lid}.jsonl")
    base = PARTIAL_LAYERS.get(lid)
    got = [r["kural_id"] for r in rows]
    if base:
        gaps = [i for i in ids if quarantine().get((base, i), {}).get("coverage") == "missing"]
        if got != [i for i in gaps if i in set(got)] or not got:
            raise SystemExit(f"data/layers/{lid}.jsonl: rows must be kurals withheld from {base}, in kural order")
    if (not base and got != ids) or {r["layer_id"] for r in rows} != {lid} or any(r["model_generated"] for r in rows):
        raise SystemExit(f"data/layers/{lid}.jsonl: not one row per kural in order, or a row from another layer")
    held = {k: e for (l, k), e in quarantine().items() if l == lid}
    # rows this layer withholds that another config carries: kural_id -> that config
    filled = {r["kural_id"]: name for name, (l, _) in SHIPPED_LAYERS.items() if PARTIAL_LAYERS.get(l) == lid
              for r in _jsonl(LAYER_DIR / f"{l}.jsonl")}
    patch = parimel_patch() if base else {}
    if base:
        bad = [r["kural_id"] for r in rows if not (
            (e := patch.get(r["kural_id"])) and e["use"] and e["layer_id"] == base and e["text_sha256"] == _text_sha(r["text"])
            and e["print_check"]["distance"] <= PATCH_CLOSE and e["print_check"]["control_distance"] >= PATCH_FAR)]
        if bad:
            raise SystemExit(f"data/layers/{lid}.jsonl: {', '.join(bad)}: no passing print check for this text in "
                             "provenance/reports/parimel_patch.jsonl")
    if lid in PRINT_CHECK:
        edition, method = PRINT_CHECK[lid], PAGE_METHOD
        page = json.loads(PAGE_CHECK.read_text(encoding="utf-8"))
        checked, mark = page["layers"][lid]["rows"], page["threshold"]
        notes = {n: e for (l, n), e in print_notes().items() if l == lid}
        rights = "public domain"
    elif base:
        edition, method, checked, mark, notes = None, None, {}, None, {}
        rights = f"author: public domain; transcription: {meta['license']}, shared with attribution to its carrier (source_id, locator)"
    else:
        edition, method, checked, mark, notes = "lazarus1885", PARIMEL_METHOD, {}, None, {}
        spot = {str(c["kural"]): c["parimel_col_share"]
                for c in json.loads(PARIMEL_CHECK.read_text(encoding="utf-8"))["lazarus1885"]}
        rights = "author: public domain; transcription rights unverified (typist and edition not stated)"
    out = []
    for r in rows:
        n = int(r["kural_id"][3:])
        e = held.get(r["kural_id"], {})
        missing = e.get("coverage") == "missing"
        text = None if missing else r["text"]
        note = notes.get(n, {})
        no_page = note.get("status") == "unverifiable"
        c = {"book_share": checked[str(n)]["book_share"]} if no_page else checked.get(str(n), {})
        v = None if missing or base else (c.get("page_share") if lid in PRINT_CHECK else spot.get(str(n)))
        cover = e.get("reason")
        if missing and r["kural_id"] in filled:
            cover += (f". This kural's commentary is in the separate share-alike config {filled[r['kural_id']]}, "
                      "from another transcription, checked against the Navalar print")
        row = {"kural_id": r["kural_id"], "kural_number": n, "text": text,
              "coverage": e.get("coverage", "complete"), "coverage_note": cover, "lang": r["lang"],
              "author": _translator(meta["author"], n), "work_title": r["work_title"], "source_id": r["source_id"],
              "locator": r["locator"], "source_sha256": r["source_sha256"],
              "carrier_license": carrier_license[r["source_id"]], "rights": rights,
              "print_edition": edition if v is not None or (lid in PRINT_CHECK and not missing) else None,
              "print_leaf": c.get("leaf") if not missing else None,
              "print_check": method if v is not None or (lid in PRINT_CHECK and not missing) else None,
              "print_match_share": v,
              "print_match": (v >= mark) if (mark is not None and v is not None) else None,
              "print_note": note.get("reason"),
              "book_match_share": None if missing else c.get("book_share"),
              "text_flags": text_flags(text) if text else [], "model_generated": False}
        if base:
            pc = patch[r["kural_id"]]["print_check"]
            row.update(print_edition=pc["edition"], print_leaf=pc["leaf"], print_match=True, print_check=(
                f"approximate-substring distance {pc['distance']:.3f} between the row's Tamil letters and the "
                f"OCR of the {pc['edition']} scan after the kural, against {pc['control_distance']:.3f} for kural "
                f"{pc['control_kural']}'s commentary on the same region; a row ships only at <= {PATCH_CLOSE:.2f} with "
                f"the control >= {PATCH_FAR:.2f} (provenance/reports/parimel_patch.jsonl)"))
        out.append(row)
    check_layer(lid, rows, out)
    return out


def read_vectors(path: Path) -> tuple[tuple[int, int], list[list[float]]]:
    """A .npy file holding a C-order little-endian float16 matrix, read without numpy: its shape and its rows as Python
    floats, each the exact value of its float16."""
    raw = path.read_bytes()
    if raw[:6] != b"\x93NUMPY":
        raise SystemExit(f"{path}: not a .npy file")
    size = 2 if raw[6] == 1 else 4  # header length field: 2 bytes in format 1.0, 4 after
    hlen = int.from_bytes(raw[8:8 + size], "little")
    head = ast.literal_eval(raw[8 + size:8 + size + hlen].decode("latin1"))
    body = raw[8 + size + hlen:]
    if head["descr"] != "<f2" or head["fortran_order"] or len(head["shape"]) != 2:
        raise SystemExit(f"{path}: want a C-order float16 matrix, got {head}")
    n, dim = head["shape"]
    if len(body) != 2 * n * dim:
        raise SystemExit(f"{path}: {len(body)} bytes of data for shape {(n, dim)}")
    vals = struct.unpack(f"<{n * dim}e", body)
    return (n, dim), [list(vals[i * dim:(i + 1) * dim]) for i in range(n)]


def embedding_rows(kurals: list[dict]) -> list[dict]:
    """embeddings_bge_m3 from the committed vectors. Refused unless the file is the one
    provenance/reports/embeddings_bge_m3.json describes, every row's input hash is the shipped kural's text_sha256, the
    benchmark's input files are the ones in the repository, and the licence is one this release can carry."""
    if EMBED is None:
        raise SystemExit("provenance/reports/embeddings_bge_m3.json is missing")
    path, hashes = ROOT / EMBED["vectors"]["path"], EMBED["input"]["sha256"]
    stale = [k["number"] for k, h in zip(kurals, hashes) if k["text_sha256"] != h]
    moved = [f for f in EMBED_BENCH_INPUTS if sha256_file(ROOT / f) != EMBED["bench"]["input_files_sha256"][f]]
    problems = [m for m, bad in (
        ("the vectors file is not the one imported", sha256_file(path) != EMBED["vectors"]["sha256"]),
        (f"computed on other text for kurals {stale[:10]}", stale or len(hashes) != len(kurals)),
        (f"the benchmark read other versions of {', '.join(moved)}", moved),
        (f"licence {EMBED['model']['license']!r} is not one this release can carry",
         EMBED["model"]["license"] not in LICENSE_URLS),
    ) if bad]
    (n, dim), vecs = read_vectors(path)
    if (n, dim) != tuple(EMBED["vectors"]["shape"]) or n != len(kurals):
        problems.append(f"shape {(n, dim)} is not {EMBED['vectors']['shape']}")
    if problems:
        raise SystemExit("provenance/reports/embeddings_bge_m3.json: " + "; ".join(problems)
                         + ". The vectors must be computed again for this text.")
    m = EMBED["model"]
    return [{"kural_id": k["id"], "kural_number": k["number"], "model_id": m["id"], "model_revision": m["revision"],
             "dim": dim, "dtype": EMBED["vectors"]["dtype"], "source_field": EMBED["input"]["field"],
             "source_text_sha256": h, "vector": v, "model_generated": True}
            for k, h, v in zip(kurals, hashes, vecs)]


def _table(name: str, rows: list[dict]) -> pa.Table:
    schema = SCHEMAS[name]
    return pa.Table.from_pylist([{f: r.get(f) for f in schema.names} for r in rows], schema=schema)


def write_parquet(tables: dict, out: Path):
    (out / "data").mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        pq.write_table(_table(name, rows), out / "data" / f"{name}.parquet", compression="zstd", compression_level=19,
                       write_statistics=False, store_schema=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def kurals_root(tables: dict) -> str:
    """sha256 over lines 'id<TAB>text_sha256<LF>' in id order: one hash that changes when any kural's text does."""
    return hashlib.sha256("".join(f"{k['id']}\t{k['text_sha256']}\n" for k in tables["kurals"]).encode()).hexdigest()


def merkle_roots(tables: dict) -> dict:
    """The two Merkle roots (tkcore.merkle) over the kurals config. The manifest and the card both read them from here,
    and the build stops if any shipped proof in merkle_proofs does not verify against them."""
    r = merkle.roots(tables["kurals"])
    proofs = {p["kural_id"]: p for p in tables["merkle_proofs"]}
    for k in tables["kurals"]:
        p, text = proofs.get(k["id"]), k["text_ta"]
        ok = p is not None and all(
            merkle.verify(p["leaf_index"], p["tree_size"], merkle.leaf_bytes(k["id"], k["number"], text, letters),
                          [bytes.fromhex(h) for h in p[path]], bytes.fromhex(r[tree]))
            for letters, path, tree in ((False, "exact_path", "exact"), (True, "letters_path", "letters")))
        if not ok:
            raise SystemExit(f"merkle_proofs: no valid proof for {k['id']}; run python -m tkcore.merkle")
    return r


def manifest(tables: dict, out: Path) -> dict:
    kh = {k["id"]: k["text_sha256"] for k in tables["kurals"]}
    root = kurals_root(tables)
    mr = merkle_roots(tables)
    files = {str(p.relative_to(out)): {"sha256": sha256_file(p), "bytes": p.stat().st_size}
             for p in sorted(out.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}
    return {"dataset": META["hf_repo"], "version": VERSION, "generator": "tkcore.release", "pyarrow": pa.__version__,
            "kurals_root_sha256": root, "kurals_root_rule": "sha256 over lines 'id<TAB>text_sha256<LF>' in id order",
            "merkle_exact_root_sha256": mr["exact"], "merkle_letters_root_sha256": mr["letters"],
            "merkle_rule": merkle.RULE,
            "model_generated": {"embeddings_bge_m3": {
                "model_id": EMBED["model"]["id"], "model_revision": EMBED["model"]["revision"],
                "license": EMBED["model"]["license"], "vectors_sha256": EMBED["vectors"]["sha256"],
                "input_kurals_root_sha256": EMBED["input"]["kurals_root_sha256"],
                "evidence": "provenance/reports/embeddings_bge_m3.json"}},
            "files": files, "kurals": kh}


# ---------------------------------------------------------------- card

def _counts(tables: dict) -> dict:
    K, L = tables["kurals"], tables["ledger"]
    st = Counter(k["text_status"] for k in K)
    dec = Counter(l["decision"] for l in L)
    der = tables["derived"]
    loc = tables["scan_locations"]
    located_all = Counter(r["kural_number"] for r in loc)
    conf = Counter(r["kural_number"] for r in loc if r["located_confidently"])
    prov_src = Counter(p["source_id"] for k in K for p in k["provenance"])
    feet = Counter(s["foot_ta"] for s in tables["seer"] if s["foot_ta"])
    return {
        "N_KURALS": len(K), "N_ADH": len(tables["adhikarams"]), "N_DIV": len(tables["divisions"]),
        "N_EN_TITLES": sum(1 for a in tables["adhikarams"] if a["name_en"]),
        "N_SEER": len(tables["seer"]), "N_SCANLOC": len(loc), "N_LEDGER": len(L), "N_SOURCES": len(tables["sources"]),
        "ST_SCAN": st["verified_scan"], "ST_ADJ": st["adjudicated"], "ST_DIGITAL": st["verified_digital_only"],
        "ST_OTHER": len(K) - st["verified_scan"] - st["adjudicated"] - st["verified_digital_only"],
        "ST_SCAN_READ": sum(1 for k in K if k["text_status"] == "verified_scan"
                            and any("confirmed on the page image" in p["locator"] for p in k["provenance"])),
        "ST_SCAN_MATCH": sum(1 for k in K if k["text_status"] == "verified_scan"
                            and not any("confirmed on the page image" in p["locator"] for p in k["provenance"])),
        "DIG_SCAN_FAIL": sum(1 for k, d in zip(K, der) if k["text_status"] == "verified_digital_only" and not d["scansion_ok"]),
        "L_CHOSE": dec["chose_candidate"], "L_TYPED": dec["transcribed_from_crop"], "L_STRUCT": dec["structure_ruling"],
        "L_KURAL": sum(1 for l in L if l["field"] == "lines_ta"), "L_NAME": sum(1 for l in L if l["field"] == "name_ta"),
        "L_SUPERSEDED": sum(1 for l in L if l["supersedes"]),
        "M_OK": sum(d["metre_ok"] for d in der), "M_FAIL": sum(not d["metre_ok"] for d in der),
        "S_OK": sum(d["scansion_ok"] for d in der), "S_FAIL": sum(not d["scansion_ok"] for d in der),
        "S_L3": sum(d["scansion_method"] == "attested division" for d in der),
        "S_RESCUED": sum(d["scansion_ok"] and not d["metre_ok"] for d in der),
        "M_SHAPE": sum(d["word_shape"] == [4, 3] for d in der), "SEARCH_DIFF": sum(1 for d in der if d["search_rule"]),
        "LOC_ALL3": sum(1 for n, c in located_all.items() if c == 3), "LOC_NONE": len(K) - len(located_all),
        "LOC_CONF2": sum(1 for n, c in conf.items() if c >= 2),
        "PROV_TOTAL": sum(prov_src.values()), "PROV_SCAN": sum(v for s, v in prov_src.items() if s.startswith("scan:")),
        "TOP_FOOT": feet.most_common(1)[0][0], "TOP_FOOT_N": feet.most_common(1)[0][1],
        **_layer_counts(tables),
    }


PRINT_LAYER = {"pope1886_en": "pope1886-en", "drew_lazarus_en": "drew-lazarus-en"}


def _aiyar_counts(rows: list[dict]) -> dict:
    """The card's figures for the Aiyar layer: rows per tier, rows found on their page, and the kurals the scan lacks."""
    tiers = Counter(r["tier"] for r in rows)
    gaps = [r["kural_number"] for r in rows if r["tier"] == "typed_edition_only"]
    return {"AIYAR_TIERS": ", ".join(f"{n:,} `{t}`" for t, n in sorted(tiers.items(), key=lambda x: -x[1])),
            "AIYAR_OK": sum(1 for r in rows if r["print_match"]),
            "AIYAR_GAPS": "6-10 and 36-40" if gaps == [*range(6, 11), *range(36, 41)] else ", ".join(map(str, gaps))}


def _layer_counts(tables: dict) -> dict:
    out = {}
    nums = lambda rows: ", ".join(str(r["kural_number"]) for r in rows)  # noqa: E731
    for key, name in (("POPE", "pope1886_en"), ("DL", "drew_lazarus_en")):
        rows = tables[name]
        miss = [r for r in rows if r["print_match"] is False]
        noleaf = [r for r in rows if r["print_match"] is None and not r["print_note"]]
        noted: dict[str, list] = {}
        for (l, k), e in print_notes().items():
            if l == PRINT_LAYER[name]:
                noted.setdefault(e["status"], []).append((k, e["short"]))
        notes = "".join(
            f" For {', '.join(str(k) for k, _ in v)} the cause is known: {v[0][1]}." if st == "kept" else
            f" {len(v)} more ({', '.join(str(k) for k, _ in v)}) cannot be checked, because {v[0][1]}; their `print_match` "
            f"is null and `print_note` says why." for st, v in sorted(noted.items(), key=lambda x: x[0] != "kept"))
        other = Counter(r["source_id"] for r in rows if r["source_id"] != "yuvaraj")
        out.update({f"{key}_OK": sum(1 for r in rows if r["print_match"]), f"{key}_MISS": len(miss),
                    f"{key}_MISS_LIST": nums(miss), f"{key}_NOLEAF": len(noleaf), f"{key}_NOLEAF_LIST": nums(noleaf),
                    f"{key}_NOTES": notes,
                    f"{key}_OTHER_CARRIER": "".join(
                        f" ({nums([r for r in rows if r['source_id'] == sid])} from `{sid}`, whose cell matches the printed "
                        f"page where `yuvaraj`'s holds the wrong text)" for sid in sorted(other))})
    out.update(_aiyar_counts(tables["aiyar1916_en"]))
    par = tables["parimelazhagar_ta"]
    flags = Counter(f for r in par for f in r["text_flags"])
    withheld = [r for r in par if r["coverage"] == "missing"]
    partial = [r for r in par if r["coverage"] == "partial"]
    held = quarantine()
    listed = lambda rows: "; ".join(f"{r['kural_number']} ({held[('parimelazhagar-ta', r['kural_id'])]['short']})"  # noqa: E731
                                    for r in rows)
    out.update({"PAR_SPOT_N": sum(1 for r in par if r["print_match_share"] is not None), "PAR_DIGITS": flags["digits"],
                "PAR_HTML": flags["html"], "PAR_VIRAMA": flags["virama_after_vowel"],
                "PAR_SHIP": len(par) - len(withheld), "PAR_MISSING_N": len(withheld), "PAR_MISSING_LIST": listed(withheld),
                "PAR_PARTIAL_N": len(partial), "PAR_PARTIAL_LIST": listed(partial)})
    sa = tables["parimelazhagar_ta_sa"]
    checks = [parimel_patch()[r["kural_id"]]["print_check"] for r in sa]
    out.update({"PAR_SA_N": len(sa), "PAR_SA_LIST": ", ".join(str(r["kural_number"]) for r in sa),
                "PAR_SA_DMIN": f"{min(c['distance'] for c in checks):.2f}",
                "PAR_SA_DMAX": f"{max(c['distance'] for c in checks):.2f}",
                "PAR_SA_CTRL": f"{min(c['control_distance'] for c in checks):.2f}"})
    if "parimelazhagar_struct" in tables:
        ps = tables["parimelazhagar_struct"]
        inbam = [r for r in ps if int(r["kural_id"][3:]) >= 1081]
        pf = Counter(f for r in ps for f in r["flags"])
        cov = [r["head_letter_coverage"] for r in ps if r["head_letter_coverage"] is not None]
        out.update({"PS_PAIRS": sum(len(r["pada_urai"]) for r in ps), "PS_ROWS": sum(1 for r in ps if r["pada_urai"]),
                    "PS_COVERAGE": f"{statistics.mean(cov):.1%}", "PS_INBAM": len(inbam),
                    "PS_TURAI": sum(1 for r in inbam if r["turai_resolved"]),
                    "PS_GROUPS": sum(1 for r in ps if r["group_end"]), "PS_SUMMARY": sum(1 for r in ps if r["summary"]),
                    "PS_READINGS": sum(len(r["reported_readings"]) for r in ps),
                    "PS_EXTRA": pf["heads_carry_extra_words"], "PS_UNCLOSED": pf["vilakkam_unclosed"]})
    if "variants_atlas" in tables:
        readings = tables["variants_atlas"] + tables["variants_atlas_sa"]
        echo = Counter(e["kind"] for e in tables["echo_graph"])
        out.update({"N_READINGS": len(readings), "N_READ_SA": len(tables["variants_atlas_sa"]),
                    "N_READ_DIFF": sum(1 for r in readings if not r["same_letters_as_canonical"]),
                    "N_ECHO_RARE": echo["shared rare word"], "N_ECHO_CHAPTER": echo["same chapter"],
                    "N_TASKS": len(tables["tasks"]), "N_CC0": sum(1 for l in LICENSES.values() if l == "CC0-1.0"),
                    "N_TASK_SA": len(spec_rows({**SPECS["tasks"], "rows": None})) - len(tables["tasks"])})
    return out


def _fmt(v) -> str:
    return f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v)


def _yaml_configs() -> str:
    out = []
    for name in CONFIGS:
        out.append(f"- config_name: {name}\n  data_files:\n  - split: train\n    path: data/{name}.parquet")
        if name == "kurals":
            out[-1] += "\n  default: true"
    return "\n".join(out)


def _field_tables() -> str:
    parts = []
    for name, (layer, desc, fields) in CONFIGS.items():
        rows = "\n".join(f"| `{f}` | {_type_name(t)} | {d} |" for f, t, d in fields)
        parts.append(f"#### `{name}` ({layer})\n\n{desc}\n\n| field | type | meaning |\n|---|---|---|\n{rows}")
    return "\n\n".join(parts)


def _type_name(t: pa.DataType) -> str:
    if pa.types.is_list(t):
        return f"list<{_type_name(t.value_type)}>"
    if pa.types.is_struct(t):
        return "struct"
    return {"string": "string", "bool": "bool", "float": "float32"}.get(str(t), str(t))


def retrieved(source: dict) -> bool:
    """Every file the registry lists for the source was retrieved and hashed. TamilThagaval's data file is gated, so
    only its README was: it is identified, not used."""
    return all(f.get("sha256") for f in source["files"])


def _sources_table(tables: dict) -> str:
    rows = []
    for s in tables["sources"]:
        kind = s["kind"].replace("_", " ") if retrieved(s) else \
            "identified, not retrieved" + (" (gated)" if "gated" in s["title"] else "")
        rows.append(f"| `{s['source_id']}` | {kind} | {s['lineage_group'] or ''} | "
                    f"{s['declared_license'] or 'none declared'} | [link]({s['url']}) |")
    return "| source | kind | lineage group | carrier's declared licence | where |\n|---|---|---|---|---|\n" + "\n".join(rows)


def _parimel_note() -> str:
    """The Parimelazhagar column's carrier is known, its edition is not; the card says so. The overlap figure is
    computed from provenance/reports/parimel_check.json."""
    withheld = {int(k[3:]) for (l, k), e in quarantine().items() if l == "parimelazhagar-ta" and e["coverage"] == "missing"}
    checks = [c for c in json.loads(PARIMEL_CHECK.read_text(encoding="utf-8"))["lazarus1885"] if c["kural"] not in withheld]
    med = statistics.median(c["parimel_col_share"] for c in checks)
    return (f"commentary labelled Parimelazhagar in the Selvakumar dataset; upstream and printed edition not identified; "
            f"spot-check shows classical text (median {med:.0%} 5-gram overlap with the 1885 pages, {len(checks)} kurals); "
            f"transcription rights unverified")


def _config_table(tables: dict) -> str:
    rows = [f"| `{n}`{' (default)' if n == 'kurals' else ''} | {len(tables[n]):,} | {layer} | {LICENSES[n]} | {desc} |"
            for n, (layer, desc, _) in CONFIGS.items()]
    return "| config | rows | layer | licence | what a row is |\n|---|---|---|---|---|\n" + "\n".join(rows)


def licenses_md() -> str:
    """LICENSES.md in the release folder: the licence of every config, with the notices the non-CC0 ones need."""
    rows = "\n".join(f"| `data/{n}.parquet` | {LICENSES[n]} | {LICENSE_URLS[LICENSES[n]]} |" for n in CONFIGS)
    return (f"# Licences\n\nEach file in this dataset has its own licence.\n\n| file | licence | text |\n|---|---|---|\n{rows}\n"
            "| README.md, croissant.json, CITATION.cff, CHANGELOG.md, MANIFEST.json, LICENSES.md, LICENSE (CC0 legal code) | CC0-1.0 | "
            f"{LICENSE_URLS['CC0-1.0']} |\n\n"
            "## parimelazhagar_ta and parimelazhagar_struct (MIT)\n\nTranscription of Parimelazhagar's commentary (public "
            "domain) from the "
            "`Parimezhalagar_Urai` column of https://huggingface.co/datasets/Selvakumarduraipandian/Thirukural, whose card "
            "declares the MIT licence and names no copyright holder. Revision and file hash: `sources` config, source_id "
            "`selvakumar`. `parimelazhagar_struct` holds spans of the same transcription, parsed by rule. The carrier gives no "
            "copyright line; its licence is MIT, whose terms follow.\n\n"
            + (RELEASE_DIR / "licenses" / "MIT.txt").read_text(encoding="utf-8") + "\n"
            "## parimelazhagar_ta_sa (CC-BY-SA-4.0)\n\nParimelazhagar's commentary (public domain) on the kurals whose "
            "row `parimelazhagar_ta` withholds, as transcribed on Tamil Wikisource, "
            "https://ta.wikisource.org/wiki/திருக்குறள்_பரிமேலழகர்_உரை (CC-BY-SA-4.0), by its contributors; each row's "
            "`locator` names the page and revision, and `sources` (source_id `wikisource-parimel`) the file hashes. Only "
            "Wikisource's section labels, markup and the editors' bracketed additions are left out. Adaptations must be shared "
            "under the same licence: https://creativecommons.org/licenses/by-sa/4.0/\n\n"
            "## variants_atlas_sa (CC-BY-SA-4.0)\n\nReadings copied without change from "
            "https://huggingface.co/datasets/Chandrasekar/thirukkural-yaappu (CC-BY-SA-4.0) and Tamil Wikisource "
            "(https://ta.wikisource.org, CC-BY-SA-4.0); each row's `sources` gives file and row. Adaptations must be shared "
            "under the same licence: https://creativecommons.org/licenses/by-sa/4.0/\n\n"
            f"## embeddings_bge_m3 ({EMBED['model']['license']})\n\nVectors computed by the model {EMBED['model']['id']} "
            f"(https://huggingface.co/{EMBED['model']['id']}) at revision {EMBED['model']['revision']}. The model card's "
            f"header at that revision says `{EMBED['model']['license_quote']}`. The model snapshot at that revision holds no LICENSE file, so "
            "the licence rests on that line alone. This config takes the model's declared licence "
            f"({LICENSE_URLS[EMBED['model']['license']]}). Whether a model's licence covers what the model computes is not settled. "
            f"Details: provenance/reports/embeddings_bge_m3.json in {META['github']}.\n")


def _layers_table() -> str:
    shipped = {lid for lid, _ in SHIPPED_LAYERS.values()}
    layers = [l for l in json.loads(LAYERS.read_text(encoding="utf-8"))["layers"] if l["layer_id"] not in shipped]
    rows = []
    for l in layers:
        cleared = l["rights_status"] == "public-domain"
        rows.append(f"| `{l['layer_id']}` | {l['lang']} | {l['kind'].capitalize()} by {l['author']}: *{l['work_title']}* "
                    f"| `{l['source_id']}` | {'public domain' if cleared else 'author rights not cleared'} "
                    f"| {'no digital copy yet' if cleared else 'not in any release'} |")
    return "| layer | lang | what it is | carrier | rights | status |\n|---|---|---|---|---|---|\n" + "\n".join(rows)


def _example(tables: dict) -> str:
    k = next(k for k in tables["kurals"] if k["id"] == "tk:0034")
    return "\n".join(k["lines_ta"])


def tokenizer_cost(tables: dict) -> dict:
    """provenance/reports/tokenizer_cost.json, refused once the kural text, or a translation or commentary text it
    counted, changes."""
    doc = json.loads(TOKENIZER_COST.read_text(encoding="utf-8"))
    if doc["measured_on"]["kurals_root_sha256"] != kurals_root(tables):
        raise SystemExit("provenance/reports/tokenizer_cost.json was measured on other kural text")
    if doc["measured_on"].get("texts_sha256") != tokens.texts_sha256(tokens.token_texts(tables)):
        raise SystemExit("provenance/reports/tokenizer_cost.json was measured on other layer text")
    return doc


def scansion_evidence(tables: dict) -> dict:
    """provenance/reports/scansion_v02.json: the foot-name agreement with Chandrasekar's analysis. Refused unless its
    rows are exactly the kurals this build's checkers reject or disagree on, with the same verdicts, methods, licences
    and problems."""
    doc = json.loads(SCANSION_V02.read_text(encoding="utf-8"))
    keys = (("kural", "kural_number"), ("v01_ok", "metre_ok"), ("v02_ok", "scansion_ok"), ("form_ok", "form_ok"),
            ("method", "scansion_method"), ("licences", "scansion_licences"), ("problems", "scansion_problems"))
    want = [{a: d[b] for a, b in keys} for d in tables["derived"] if not (d["metre_ok"] and d["scansion_ok"] and d["form_ok"])]
    if [{a: r[a] for a, _ in keys} for r in doc["rows"]] != want:
        raise SystemExit("provenance/reports/scansion_v02.json does not match this text's metre verdicts")
    return doc


def collation_values(tables: dict) -> dict:
    """provenance/reports/collation_l3.json: the comparison of every kural with Tamil Wikisource's verse (L3),
    junctions included. Refused unless it covers every kural with this build's text_status and live rulings, and checked
    each difference against at least two prints, as the card says. COL_EARLIER counts the kurals with no usable L3 that
    the print comparison in provenance/reports/collation.json covers."""
    rows = json.loads(COLLATION_L3.read_text(encoding="utf-8"))["rows"]
    K = {str(k["number"]): k for k in tables["kurals"]}
    if rows.keys() != K.keys() or any(r["text_status"] != K[n]["text_status"]
                                      or not set(K[n]["adjudication_ids"]) <= set(r["ledger"]) for n, r in rows.items()):
        raise SystemExit("provenance/reports/collation_l3.json is not for this text")
    if any(r["diffs"] and r["usable_prints"] < 2 for r in rows.values()):
        raise SystemExit("provenance/reports/collation_l3.json has a difference checked against fewer than two prints; "
                         "the card says at least two")
    no_l3 = {n for n, r in rows.items() if r["status"] == "no usable L3"}
    earlier = {str(c["kural"]) for c in json.loads(COLLATION.read_text(encoding="utf-8"))}
    return {"COL_N": f"{len(rows) - len(no_l3):,}",
            "COL_SAME": f"{sum(r['status'] == 'no difference' for r in rows.values()):,}",
            "COL_NO_L3": f"{len(no_l3):,}", "COL_EARLIER": f"{len(no_l3 & earlier):,}"}


def _division_sources(rows: list) -> str:
    """'5 from L3, 2 from the Lazarus 1885 print': which edition gave the foot division, by scansion_licences."""
    names = {"L3": "L3", "Lazarus 1885": "the Lazarus 1885 print", "Navalar": "the Navalar print", "Pope 1886": "the Pope 1886 print"}
    c = Counter(next((v for k, v in names.items() if any(k in x for x in d["scansion_licences"] if x.startswith("vakaiyuli"))), "?")
                for d in rows)
    return ", ".join(f"{n} from {src}" for src, n in sorted(c.items(), key=lambda kv: (kv[0] != "L3", kv[0])))


def _scansion_values(tables: dict) -> dict:
    der = tables["derived"]
    fails = [d["kural_number"] for d in der if not d["scansion_ok"]]
    form = sum(not d["form_ok"] for d in der)
    agree, n = scansion_evidence(tables)["agreement_with_chandrasekar_seers"]["v0.3"]
    return {"S_FAIL_LIST": ", ".join(map(str, fails)),
            "S_FORM": ("No kural has more printed words on a line than feet (`form_ok`), so every failure is in the "
                       "metre, not in how the text is written." if not form else
                       f"{form:,} kurals have more printed words on a line than feet (`form_ok` false)."),
            "S_RESCUED_L3": f"{sum(d['scansion_method'] == 'attested division' and not d['metre_ok'] for d in der):,}",
            "S_RESCUED_SOURCES": _division_sources([d for d in der if d["scansion_method"] == "attested division" and not d["metre_ok"]]),
            "S_DIV_SOURCES": _division_sources([d for d in der if d["scansion_method"] == "attested division"]),
            "CHA_AGREE": f"{agree:,}", "CHA_N": f"{n:,}"}


def _tokenizer_table(doc: dict) -> str:
    rows = [f"| {r['tokenizer']}{'' if r['first_party'] else ' *'} | {r['kural_ta_tokens_mean']} | {r['kural_ta_tokens_max']} | "
            f"{r['kural_ta_tokens_per_word']} | {r['tamil_vs_pope_ratio']} | {r['kural_ta_tokens_total']:,} | "
            f"{r['four_texts_tokens_total']:,} |" for r in doc["tokenizers"]]
    return ("| tokenizer | tokens per kural | most in one kural | per Tamil word | Tamil ÷ Pope's English | all 1,330 kurals "
            "| kurals + Pope + Drew/Lazarus + Parimelazhagar |\n|---|---|---|---|---|---|---|\n" + "\n".join(rows))


EMBED_TASKS = (("ta->pope", "Tamil to Pope"), ("pope->ta", "Pope to Tamil"), ("drew->pope", "Drew/Lazarus to Pope"),
               ("misquote", "Misquote"))


def _embed_values() -> dict:
    """The card's embedding section, from provenance/reports/embeddings_bge_m3.json (the model's scores and the
    no-model baseline on the same files)."""
    b, base = EMBED["bench"]["model"], EMBED["bench"]["baseline"]
    rows = [f"| {label} | {b[t]['n']:,} | {b[t]['R@1']:.3f} | {b[t]['R@10']:.3f} | {b[t]['MRR']:.3f} | "
            f"{base[t]['R@1']:.3f} | {base[t]['R@10']:.3f} | {base[t]['MRR']:.3f} |" for t, label in EMBED_TASKS]
    atlas = Counter(r["status"].split(" (")[0] for r in _jsonl(ROOT / "data" / "signature" / "variants_atlas.jsonl")
                    if r["status"].lower().startswith(("rejected", "metrical")))
    pct = lambda v: f"{v:.1%}"  # noqa: E731
    return {"EMBED_MODEL": EMBED["model"]["id"], "EMBED_REV": EMBED["model"]["revision"],
            "EMBED_DIM": f"{EMBED['vectors']['shape'][1]:,}", "EMBED_LICENSE": EMBED["model"]["license"],
            "EMBED_LICENSE_QUOTE": EMBED["model"]["license_quote"],
            "EMBED_TABLE": ("| task | queries | BGE-M3 R@1 | R@10 | MRR | baseline R@1 | R@10 | MRR |\n"
                            "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows)),
            "EMBED_MIS_METRICAL": f"{atlas['metrical form']:,}", "EMBED_MIS_REJECTED": f"{atlas['rejected reading']:,}",
            "EMBED_TA_POPE_R1": pct(b["ta->pope"]["R@1"]), "EMBED_TA_POPE_R10": pct(b["ta->pope"]["R@10"]),
            "EMBED_POPE_TA_R1": pct(b["pope->ta"]["R@1"]),
            "EMBED_MIS_R1": pct(b["misquote"]["R@1"]), "EMBED_MIS_BASE_R1": pct(base["misquote"]["R@1"]),
            "EMBED_DREW_R1": pct(b["drew->pope"]["R@1"]), "EMBED_DREW_BASE_R1": pct(base["drew->pope"]["R@1"]),
            "N_NOT_CC0": str(sum(1 for l in LICENSES.values() if l != "CC0-1.0"))}


def render_card(tables: dict) -> str:
    vals = {k: _fmt(v) for k, v in _counts(tables).items()}
    mr = merkle_roots(tables)
    tc = tokenizer_cost(tables)
    first = [r for r in tc["tokenizers"] if r["first_party"]]  # the headline compares vendor files only
    lo, hi = first[0], first[-1]
    k34 = next(k for k in tables["kurals"] if k["id"] == "tk:0034")
    vals.update({
        "VERSION": VERSION, "DATE": META["date"], "HF_REPO": META["hf_repo"], "GITHUB": META["github"],
        "SITE": META["site"], "ORCID": META["orcid"], "YAML_CONFIGS": _yaml_configs(), "FIELD_TABLES": _field_tables(),
        "SOURCES_TABLE": _sources_table(tables), "LAYERS_TABLE": _layers_table(), "CONFIG_TABLE": _config_table(tables),
        "PAR_WHAT": _parimel_note(), "CANARY": META["canary"],
        "K34_TEXT": _example(tables), "K34_SHA": k34["text_sha256"], "KURALS_ROOT": kurals_root(tables), "K34_ADH": k34["adhikaram_name_ta"],
        "K34_STATUS": k34["text_status"], "K34_RULING": ", ".join(k34["adjudication_ids"]),
        "CHECKER": f"{prosody.VenbaChecker.name} {prosody.VenbaChecker.version}",
        "MERKLE_ROOT": mr["exact"], "MERKLE_LETTERS_ROOT": mr["letters"], "N_KB": f"{len(tables['kuralbench_lite']):,}",
        "TOKENIZER_TABLE": _tokenizer_table(tc), "TOK_LO": lo["tokenizer"], "TOK_HI": hi["tokenizer"],
        "TOK_RATIO": f"{hi['kural_ta_tokens_total'] / lo['kural_ta_tokens_total']:.1f}",
        **_embed_values(), **_scansion_values(tables), **collation_values(tables),
        **tokens.values(tc),
    })
    text = CARD_TEMPLATE.read_text(encoding="utf-8")
    for key, v in vals.items():
        text = text.replace("{{" + key + "}}", v)
    if "{{" in text:
        i = text.index("{{")
        raise ValueError(f"unfilled placeholder in card template: {text[i:i + 40]}")
    return text


def changelog_section(tables: dict, previous: Path | None) -> str:
    if previous is None:
        return ""
    prev = json.loads(previous.read_text(encoding="utf-8"))
    cur = {k["id"]: k["text_sha256"] for k in tables["kurals"]}
    changed = [i for i in cur if prev["kurals"].get(i) != cur[i]]
    lines = [f"- `{i}`: `{prev['kurals'].get(i, 'new')[:12]}` to `{cur[i][:12]}`" for i in changed]
    return f"\n### Kural text changes since {prev['version']}\n\n" + ("\n".join(lines) if lines else "None.") + "\n"


def build_release(out: Path = DIST, previous: Path | None = None) -> dict:
    from . import croissant
    tables = build_tables()
    if out.exists():
        shutil.rmtree(out)
    write_parquet(tables, out)
    card = render_card(tables)
    (out / "README.md").write_text(card, encoding="utf-8")
    hashes = {name: sha256_file(out / "data" / f"{name}.parquet") for name in CONFIGS}
    (out / "croissant.json").write_text(croissant.dump(croissant.build(hashes)), encoding="utf-8")
    shutil.copyfile(ROOT / "CITATION.cff", out / "CITATION.cff")
    shutil.copyfile(ROOT / "LICENSE", out / "LICENSE")
    (out / "LICENSES.md").write_text(licenses_md(), encoding="utf-8")
    (out / "CHANGELOG.md").write_text(CHANGELOG.read_text(encoding="utf-8") + changelog_section(tables, previous),
                                      encoding="utf-8")
    m = manifest(tables, out)
    (out / "MANIFEST.json").write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"tables": tables, "card": card, "manifest": m}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DIST)
    ap.add_argument("--check", action="store_true", help="fail if release/hf/README.md or release/croissant.json is stale")
    ap.add_argument("--previous", type=Path, help="MANIFEST.json of the previous release, for the changelog")
    args = ap.parse_args(argv)
    res = build_release(args.out, args.previous)
    built_card = res["card"]
    built_croissant = (args.out / "croissant.json").read_text(encoding="utf-8")
    if args.check:
        stale = [p.name for p, want in ((CARD_OUT, built_card), (CROISSANT_OUT, built_croissant))
                 if not p.exists() or p.read_text(encoding="utf-8") != want]
        if stale:
            raise SystemExit(f"stale: {stale}; run python -m tkcore.release")
        return
    CARD_OUT.write_text(built_card, encoding="utf-8")
    CROISSANT_OUT.write_text(built_croissant, encoding="utf-8")
    m = res["manifest"]
    print(f"{args.out}: {len(m['files'])} files; kurals root {m['kurals_root_sha256'][:16]}")
    for name, rows in res["tables"].items():
        print(f"  {name:15} {len(rows):6,}")


if __name__ == "__main__":
    main()
