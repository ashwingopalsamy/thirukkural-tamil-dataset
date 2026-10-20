"""Croissant 1.1 + RAI metadata for the Hugging Face release, generated from tkcore.release.CONFIGS.

  python -m tkcore.release          writes release/croissant.json and dist/hf/croissant.json (calls build here)
  python -m tkcore.croissant        the same

Record sets and field descriptions come from the same table that builds the Parquet files, so the metadata cannot
drift from the data. File hashes are the sha256 of dist/hf/data/*.parquet, which the deterministic build reproduces.
contentUrl pins each file to the release tag, so the hashes stay true after later releases.
tests/test_release.py validates the output with mlcroissant and loads every record set from the local files.
"""
import json

import pyarrow as pa

from . import registry as reg
from .release import CONFIGS, EMBED, EXTRA_KEYS, EXTRA_REFERENCES, LICENSE_URLS, LICENSES, META, VERSION, retrieved

HF_URL = f"https://huggingface.co/datasets/{META['hf_repo']}"

CONTEXT = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "arrayShape": "cr:arrayShape",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "containedIn": "cr:containedIn",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "dct": "http://purl.org/dc/terms/",
    "equivalentProperty": "cr:equivalentProperty",
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileProperty": "cr:fileProperty",
    "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isArray": "cr:isArray",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "samplingRate": "cr:samplingRate",
    "sc": "https://schema.org/",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}

KEYS = {"kurals": ["id"], "adhikarams": ["number"], "divisions": ["level", "scheme", "number"],
        "seer": ["kural_id", "position"], "derived": ["kural_id"], "scan_locations": ["kural_id", "edition"],
        "ledger": ["ledger_id"], "sources": ["source_id"], **EXTRA_KEYS}
REFERENCES = {("kurals", "adhikaram_number"): "adhikarams/number", ("seer", "kural_id"): "kurals/id",
              ("derived", "kural_id"): "kurals/id", ("scan_locations", "kural_id"): "kurals/id",
              ("scan_locations", "source_id"): "sources/source_id", **EXTRA_REFERENCES}


def _dtype(t: pa.DataType) -> str:
    if pa.types.is_integer(t):
        return "sc:Integer"
    if pa.types.is_boolean(t):
        return "sc:Boolean"
    if pa.types.is_floating(t):
        return "sc:Float"
    return "sc:Text"


def _sub(fid: str, t: pa.DataType, file_id: str, column: str, path: str) -> list[dict]:
    """subFields of a struct column; a list of structs inside it nests once more via a [*] JSONPath."""
    out = []
    for c in t:
        f = {"@type": "cr:Field", "@id": f"{fid}/{c.name}", "name": c.name}
        ct = c.type
        if pa.types.is_list(ct):
            f["isArray"] = True
            ct = ct.value_type
        if pa.types.is_struct(ct):
            f["subField"] = [{"@type": "cr:Field", "@id": f"{fid}/{c.name}/{g.name}", "name": g.name,
                              "dataType": _dtype(g.type),
                              "source": {"fileObject": {"@id": file_id}, "extract": {"column": column},
                                         "transform": {"jsonPath": f"{path}{c.name}[*].{g.name}"}}} for g in ct]
        else:
            f["dataType"] = _dtype(ct)
        f["source"] = {"fileObject": {"@id": file_id}, "extract": {"column": column},
                       "transform": {"jsonPath": f"{path}{c.name}"}}
        out.append(f)
    return out


def _field(rs: str, name: str, t: pa.DataType, desc: str, file_id: str) -> dict:
    fid = f"{rs}/{name}"
    f = {"@type": "cr:Field", "@id": fid, "name": name, "description": desc}
    if pa.types.is_list(t):
        f["isArray"] = True
        t = t.value_type
    if pa.types.is_struct(t):
        f["subField"] = _sub(fid, t, file_id, name, "")
    else:
        f["dataType"] = _dtype(t)
    f["source"] = {"fileObject": {"@id": file_id}, "extract": {"column": name}}
    if (rs, name) in REFERENCES:
        f["references"] = {"field": {"@id": REFERENCES[(rs, name)]}}
    return f


def build(hashes: dict[str, str]) -> dict:
    distribution, record_sets = [], []
    for name, (layer, desc, fields) in CONFIGS.items():
        fid = f"{name}-parquet"
        distribution.append({
            "@type": "cr:FileObject", "@id": fid, "name": fid,
            "contentUrl": f"{HF_URL}/resolve/v{VERSION}/data/{name}.parquet",
            "encodingFormat": "application/x-parquet",
            "sha256": hashes[name],
            "license": LICENSE_URLS[LICENSES[name]],
        })
        rs = {"@type": "cr:RecordSet", "@id": name, "name": name, "description": f"{desc} Layer: {layer}.",
              "field": [_field(name, f, t, d, fid) for f, t, d in fields]}
        rs["key"] = [{"@id": f"{name}/{k}"} for k in KEYS[name]]
        record_sets.append(rs)
    sources = reg.load()
    return {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "conformsTo": "http://mlcommons.org/croissant/1.1",
        "name": "thirukkural",
        "alternateName": ["Thirukkural Tamil Dataset", "Tirukkural", "Thirukural", "Thiruvalluvar's Kural", "திருக்குறள்"],
        "description": ("Thirukkural Tamil dataset: the Tamil text of all 1,330 kurals of the Thirukkural, each "
                        "with the sources that carry it, its verification status, a sha256 of its exact text, and the "
                        "ruling that settled it where sources disagree. Also: chapter and book structure, metrical "
                        "analysis of every seer, the position of each kural in three 19th-century printed editions, "
                        "the ruling ledger and the source registry. Separate configs carry G. U. Pope's 1886 English "
                        "verse translation, the Drew and Lazarus English prose translation, V. V. S. Aiyar's 1916 "
                        "English translation and Parimelazhagar's Tamil commentary, each row compared with a printed "
                        "edition where one is available, and the commentary parsed by rule into word glosses, "
                        "situation notes and the readings it reports. One config, embeddings_bge_m3, holds vectors a "
                        "model computed from the text, labelled model_generated on every row; no text is model output."),
        "license": sorted({LICENSE_URLS[l] for l in LICENSES.values()}),
        "url": HF_URL,
        "sameAs": [META["github"]],
        "version": VERSION,
        "datePublished": META["date"],
        "inLanguage": ["ta", "en"],
        "keywords": ["Thirukkural", "Tirukkural", "Thirukural", "திருக்குறள்", "Thiruvalluvar", "Tamil",
                     "Tamil dataset", "classical Tamil", "kural venba", "prosody", "provenance", "textual criticism",
                     "digital edition"],
        "creator": {"@type": "Person", "name": "Ashwin Gopalsamy", "url": "https://ashwingopalsamy.in",
                    **({"identifier": f"https://orcid.org/{META['orcid']}"} if META.get("orcid") else {})},
        "citeAs": (f"@dataset{{gopalsamy_thirukkural_2026, author = {{Gopalsamy, Ashwin}}, title = {{Thirukkural "
                   f"Tamil Dataset}}, year = {{2026}}, version = {{{VERSION}}}, "
                   f"publisher = {{Hugging Face}}, url = {{{HF_URL}}}}}"),
        "isAccessibleForFree": True,
        "isBasedOn": [s["url"] for s in sources.values() if s["kind"] in ("digital_witness", "scan_witness")
                      and retrieved(s)],
        "rai:dataCollection": ("Four Hugging Face datasets were retrieved as digital witnesses, with revision and "
                               "sha256 recorded for every file (sources config); a fifth (TamilThagaval) is gated, "
                               "only its README was retrieved, and none of its content is used. Three scanned printed "
                               "editions on archive.org (Pope 1886, Lazarus and Mrugesa Mudaliyar 1885, Arumuga "
                               "Navalar) are the verification witnesses. Tamil Wikisource is consulted in two forms. Its "
                               "proofread மூலம் pages (source wikisource-mulam) are byte-identical to Chandrasekar's "
                               "raw lines on 1,220 of 1,330 kurals, including their error at kural 51, and are grouped with "
                               "lineage group L1. The seer-divided text of its Parimelazhagar edition, which "
                               "Chandrasekar's dataset carries as parimelazhagar_wikisource.json, is lineage group L3."),
        "rai:dataCollectionType": ["Secondary Data Analysis", "Manual Human Curation"],
        "rai:dataPreprocessingProtocol": ("Unicode NFC. Forbidden codepoints rejected (unassigned Tamil-block "
                                          "codepoints, ZWJ, ZWNJ, NBSP, private use). Deterministic cleaning rules "
                                          "only; no rule changes a Tamil letter. Disputed letters are settled in the "
                                          "ruling ledger, never by cleaning."),
        "rai:dataAnnotationProtocol": ("Candidate readings come only from cited witnesses. Machine reading of the "
                                       "scans locates each kural and compares the candidates; it never supplies "
                                       "text. Where witnesses and scans do not settle a reading, a ruling in the "
                                       "ledger records the candidates, evidence, time and a value hash. A reading "
                                       "typed from the print is keyed twice and must match. Every ruling's "
                                       "adjudicator is a person (adjudicator_kind human)."),
        "rai:machineAnnotationTools": ["Machine reading of the scanned Tamil editions: used only to locate kurals and "
                                       "compare candidate readings; it supplies no Tamil text",
                                       "The aiyar1916_en text is machine-read from a scan of the 1916 book and may "
                                       "contain reading errors; each row's tier says how it was checked",
                                       "tkcore.prosody, a rule-based kural venba checker (derived layer only)",
                                       f"{EMBED['model']['id']} at revision {EMBED['model']['revision']}: the vectors in "
                                       "embeddings_bge_m3 are model output, computed from the canonical text; no text"],
        "rai:dataBiases": ("Numbering, order and section grouping follow the Parimelazhagar tradition; other "
                           "commentators order and group differently."),
        "rai:dataLimitations": ("The two metre checkers are rule-based; v0.3 takes the foot boundaries of a few "
                                "kurals from an edition's seer division (Tamil Wikisource's Parimelazhagar text or a "
                                "printed edition). Scan boxes can be offset by a line. verified_digital_only kurals "
                                "have not been compared letter by letter with a print."),
        "rai:dataUseCases": ["Exact quotation and citation by number or id",
                             "Grounding for retrieval and question answering",
                             "Evaluating whether language models quote classical Tamil exactly",
                             "Tamil prosody and textual-criticism research"],
        "rai:dataSocialImpact": ("An exact, checkable Tamil text of a widely quoted work, with the sources behind "
                                 "every reading, so a misquotation can be detected."),
        "rai:hasSyntheticData": False,
        "rai:personalSensitiveInformation": "None. A classical text and bibliographic metadata.",
        "rai:dataReleaseMaintenancePlan": ("Semantic versions with the same tag on GitHub and Hugging Face. Ids are "
                                           "permanent. Text corrections go through the ledger and ship as a new major "
                                           "version with a per-kural changelog."),
        "distribution": distribution,
        "recordSet": record_sets,
    }


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":  # kept so `python -m tkcore.croissant [--check]` still regenerates release/croissant.json
    from .release import main

    main()
