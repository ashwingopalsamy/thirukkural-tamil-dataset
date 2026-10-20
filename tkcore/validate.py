"""Validator suite for the core dataset, the adjudication ledger and the layer manifest.

  python -m tkcore.validate            structural + hygiene + provenance checks (skeleton passes)
  python -m tkcore.validate --gate     release gate: also requires every kural resolved and every name filled

Every failure names the check, the subject (tk:NNNN, adhikaram:N, adj:NNNNN, ...) and the reason.
"""
import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import DATA_CORE, LAYERS, LEDGER, REGISTRY, ROOT
from . import registry as reg
from .ids import N_KURALS, kural_id
from .schema import errors as schema_errors
from .seer import count_seers
from .structure import (IYAL_SCHEMES, N_ADHIKARAMS, PAAL_SIZES, adhikaram_of, kural_range,
                        paal_of_adhikaram)
from .tamil import FORBIDDEN_NAMED, check_lines, check_name

LAYER_DATA = ROOT / "data" / "layers"

CORE_LICENSES = {"CC0-1.0", "LicenseRef-PublicDomain"}
PD_LICENSES = {"CC0-1.0", "LicenseRef-PublicDomain"}
UNVERIFIED_LICENSE = "LicenseRef-AuthorRightsUnverified"
TRANSCRIPTION_LICENSED = "public-domain author; transcription licensed by its source (see license)"
RESOLVED = {"verified_scan", "verified_digital_only", "adjudicated"}
CONTENT_FIELDS = {"kurals": ["lines_ta", "seer_lines_ta"], "adhikarams": ["name_ta", "name_en"],
                  "divisions": ["name_ta", "name_en"]}


@dataclass
class Report:
    errors: list = field(default_factory=list)

    def add(self, check: str, subject: str, msg: str):
        self.errors.append((check, subject, msg))

    @property
    def ok(self) -> bool:
        return not self.errors

    def by_check(self) -> Counter:
        return Counter(c for c, _, _ in self.errors)

    def __str__(self):
        lines = [f"{c}\t{s}\t{m}" for c, s, m in self.errors[:200]]
        if len(self.errors) > 200:
            lines.append(f"... {len(self.errors) - 200} more")
        summary = ", ".join(f"{c}={n}" for c, n in sorted(self.by_check().items())) or "no errors"
        return "\n".join(lines + [f"SUMMARY: {summary}"])


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def value_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()


def _subject(table: str, row: dict) -> str:
    if table == "kurals":
        return row.get("id", "?")
    if table == "adhikarams":
        return f"adhikaram:{row.get('number')}"
    return f"{row.get('level')}:{row.get('scheme')}:{row.get('number')}"


def check_schema(tables, rep):
    defs = {"kurals": "kural", "adhikarams": "adhikaram", "divisions": "division"}
    for t, rows in tables.items():
        for r in rows:
            for e in schema_errors(defs[t], r):
                rep.add("schema", _subject(t, r), e)


def check_structure(tables, rep):
    kurals, adh, div = tables["kurals"], tables["adhikarams"], tables["divisions"]
    if len(kurals) != N_KURALS:
        rep.add("count", "kurals", f"{len(kurals)} rows, expected {N_KURALS}")
    ids = [r.get("id") for r in kurals]
    if ids != [kural_id(n) for n in range(1, len(kurals) + 1)]:
        rep.add("ids", "kurals", "ids are not tk:0001.. contiguous in order")
    for dup, n in Counter(ids).items():
        if n > 1:
            rep.add("ids", dup, f"duplicate id ({n}x)")
    for r in kurals:
        n = r.get("number")
        if not isinstance(n, int) or not 1 <= n <= N_KURALS:
            continue
        a = adhikaram_of(n)
        want = {"id": kural_id(n), "adhikaram_number": a, "paal_number": paal_of_adhikaram(a), "position": (n - 1) % 10 + 1}
        for k, v in want.items():
            if r.get(k) != v:
                rep.add("structure", r.get("id", f"#{n}"), f"{k}={r.get(k)!r}, expected {v!r}")
    per_adh = Counter(r.get("adhikaram_number") for r in kurals)
    bad = {a: c for a, c in per_adh.items() if c != 10}
    if len(per_adh) != N_ADHIKARAMS or bad:
        rep.add("count", "kurals", f"{len(per_adh)} adhikarams in kurals, uneven: {dict(list(bad.items())[:5])}")

    if len(adh) != N_ADHIKARAMS:
        rep.add("count", "adhikarams", f"{len(adh)} rows, expected {N_ADHIKARAMS}")
    for r in adh:
        a = r.get("number")
        if not isinstance(a, int) or not 1 <= a <= N_ADHIKARAMS:
            continue
        lo, hi = kural_range(a)
        for k, v in {"first_kural": lo, "last_kural": hi, "paal_number": paal_of_adhikaram(a)}.items():
            if r.get(k) != v:
                rep.add("structure", f"adhikaram:{a}", f"{k}={r.get(k)!r}, expected {v!r}")
    paal_sizes = Counter(r.get("paal_number") for r in adh)
    if dict(paal_sizes) != PAAL_SIZES:
        rep.add("count", "adhikarams", f"paal sizes {dict(sorted(paal_sizes.items()))}, expected {PAAL_SIZES}")

    schemes = {}
    for r in div:
        schemes.setdefault((r.get("level"), r.get("scheme")), []).append(r)
    if ("paal", "paal") not in schemes:
        rep.add("structure", "divisions", "no paal rows")
    for (level, scheme), rows in schemes.items():
        rows = sorted(rows, key=lambda r: r.get("number", 0))
        if [r.get("number") for r in rows] != list(range(1, len(rows) + 1)):
            rep.add("structure", f"{level}:{scheme}", "numbers are not 1..n contiguous")
        nxt = 1
        for r in rows:
            lo, hi = r.get("first_adhikaram"), r.get("last_adhikaram")
            if lo != nxt or hi is None or hi < lo:
                rep.add("structure", _subject("divisions", r), f"range {lo}-{hi} does not continue from {nxt}")
                break
            if paal_of_adhikaram(lo) != paal_of_adhikaram(hi) or r.get("paal_number") != paal_of_adhikaram(lo):
                rep.add("structure", _subject("divisions", r), f"range {lo}-{hi} crosses or mislabels a paal")
            nxt = hi + 1
        if nxt != N_ADHIKARAMS + 1:
            rep.add("structure", f"{level}:{scheme}", f"covers 1..{nxt - 1}, expected 1..{N_ADHIKARAMS}")
    for scheme, spec in IYAL_SCHEMES.items():
        got = [(r["first_adhikaram"], r["last_adhikaram"]) for r in sorted(schemes.get(("iyal", scheme), []), key=lambda r: r["number"])]
        if got != spec["ranges"]:
            rep.add("structure", f"iyal:{scheme}", "ranges differ from tkcore/structure.py")


def check_text(tables, rep):
    for r in tables["kurals"]:
        for f in ("lines_ta", "seer_lines_ta"):
            for issue in check_lines(r.get(f)):
                rep.add(issue.code, r["id"], f"{f}: {issue}")
        if r.get("seer_lines_ta") is not None:
            sc = count_seers(r["seer_lines_ta"])
            if not sc.ok:
                rep.add("seer_count", r["id"], f"seer_lines_ta has {sc.counts} seers, expected (4, 3)")
    for t in ("adhikarams", "divisions"):
        for r in tables[t]:
            if r.get("name_ta") is not None:
                for issue in check_name(r["name_ta"]):
                    rep.add(issue.code, _subject(t, r), f"name_ta: {issue}")
            en = r.get("name_en")
            if en is not None:
                if en != unicodedata.normalize("NFC", en):
                    rep.add("not_nfc", _subject(t, r), "name_en not NFC")
                if any(ord(c) in FORBIDDEN_NAMED or unicodedata.category(c) == "Co" for c in en):
                    rep.add("forbidden_codepoint", _subject(t, r), "name_en")


def check_provenance(tables, registry, rep):
    hashes = reg.file_hashes(registry)
    for t, rows in tables.items():
        for r in rows:
            subj = _subject(t, r)
            prov = r.get("provenance") or []
            cited = {p.get("field") for p in prov}
            for f in CONTENT_FIELDS[t]:
                if r.get(f) is not None and f not in cited:
                    rep.add("provenance_missing", subj, f"{f} is set but has no provenance entry")
            for p in prov:
                f, sid = p.get("field"), p.get("source_id")
                if f not in CONTENT_FIELDS[t]:
                    rep.add("provenance_field", subj, f"provenance for unknown field {f!r}")
                elif r.get(f) is None:
                    rep.add("provenance_dangling", subj, f"provenance for {f} but the field is null")
                if sid not in registry:
                    rep.add("provenance_source", subj, f"source_id {sid!r} not in provenance/registry/sources.json")
                elif p.get("source_sha256") not in hashes[sid]:
                    rep.add("provenance_hash", subj, f"source_sha256 {str(p.get('source_sha256'))[:12]} is not a retrieval hash of {sid}")
                if p.get("license") not in CORE_LICENSES:
                    rep.add("provenance_license", subj, f"licence {p.get('license')!r} not allowed in the CC0 core")


def check_ledger(tables, ledger, rep):
    by_id = {}
    for e in ledger:
        lid = e.get("ledger_id", "?")
        for msg in schema_errors("ledger_entry", e):
            rep.add("ledger_schema", lid, msg)
        if lid in by_id:
            rep.add("ledger_schema", lid, "duplicate ledger_id")
        by_id[lid] = e
        v = e.get("value")
        if v is not None:
            if e.get("value_sha256") != value_sha256(v):
                rep.add("ledger_hash", lid, "value_sha256 does not match value")
            for s in ([v] if isinstance(v, str) else v):
                if s != unicodedata.normalize("NFC", s):
                    rep.add("ledger_nfc", lid, "value not NFC")
    superseded = {e.get("supersedes") for e in ledger if e.get("supersedes")}
    for s in superseded:
        if s not in by_id:
            rep.add("ledger_link", s, "superseded entry does not exist")
    for r in tables["kurals"]:
        for lid in r.get("adjudication_ids") or []:
            e = by_id.get(lid)
            if e is None:
                rep.add("ledger_link", r["id"], f"{lid} not in ledger")
            elif e.get("subject") != r["id"]:
                rep.add("ledger_link", r["id"], f"{lid} is about {e.get('subject')}")
        if r.get("text_status") == "adjudicated" and not r.get("adjudication_ids"):
            rep.add("ledger_link", r["id"], "text_status adjudicated without an adjudication id")
    live = [e for e in ledger if e.get("ledger_id") not in superseded and e.get("decision") != "unresolved"]
    rows = {r["id"]: r for r in tables["kurals"]}
    for e in live:
        subj, f = e.get("subject", ""), e.get("field")
        if subj in rows and f in ("lines_ta", "seer_lines_ta") and rows[subj].get(f) != e.get("value"):
            rep.add("ledger_mismatch", subj, f"{f} differs from live ruling {e.get('ledger_id')}")


def check_layers(manifest, registry, rep):
    seen = set()
    for l in manifest.get("layers", []):
        lid = l.get("layer_id", "?")
        for msg in schema_errors("layer", l):
            rep.add("layer_schema", lid, msg)
        if lid in seen:
            rep.add("layer_schema", lid, "duplicate layer_id")
        seen.add(lid)
        pd = l.get("rights_status") == "public-domain"
        transcribed = l.get("rights_status") == TRANSCRIPTION_LICENSED
        if pd and l.get("license") not in PD_LICENSES:
            rep.add("layer_license", lid, "public-domain layer must carry a PD/CC0 licence id")
        if transcribed and l.get("license") in PD_LICENSES | {UNVERIFIED_LICENSE}:
            rep.add("layer_license", lid, "a licensed transcription must carry its source's licence id")
        if not pd and not transcribed and l.get("license") != UNVERIFIED_LICENSE:
            rep.add("layer_license", lid, f"rights-unverified layer must carry {UNVERIFIED_LICENSE}")
        sid = l.get("source_id", "")
        if not sid.startswith("pending:") and sid not in registry:
            rep.add("layer_source", lid, f"source_id {sid!r} not in registry")
        for row in read_jsonl(LAYER_DATA / f"{lid}.jsonl"):
            subj = f"{lid}:{row.get('kural_id')}"
            for msg in schema_errors("layer_row", row):
                rep.add("layer_row_schema", subj, msg)
            for k in ("rights_status", "license", "author", "work_title"):
                if row.get(k) != l.get(k):
                    rep.add("layer_row_rights", subj, f"{k} differs from layers.json")


def check_gate(tables, rep):
    status = Counter(r.get("text_status") for r in tables["kurals"])
    unresolved = {s: n for s, n in status.items() if s not in RESOLVED}
    if unresolved:
        rep.add("gate", "kurals", f"unresolved text_status counts: {dict(sorted(unresolved.items()))}")
    missing = sum(1 for r in tables["kurals"] if r.get("lines_ta") is None)
    if missing:
        rep.add("gate", "kurals", f"{missing} kurals without lines_ta")
    for t in ("adhikarams", "divisions"):
        n = sum(1 for r in tables[t] if r.get("name_ta") is None and (t == "adhikarams" or r.get("level") == "paal"))
        if n:
            rep.add("gate", t, f"{n} rows without name_ta")


ATLAS = ROOT / "data" / "signature" / "variants_atlas.jsonl"
# Letters a native Tamil word does not begin with (மொழிமுதல் rule); a witness word starting with one is malformed.
BAD_INITIAL = set("டணரலழளறனங")


def _metre_positions(problems) -> set:
    import re
    out = set()
    for p in problems:
        m = re.match(r"seer (\d+)", p)
        if m:
            out.add(int(m.group(1)))
        m = re.match(r"thalai (\d+)->(\d+)", p)
        if m:
            out |= {int(m.group(1)), int(m.group(2))}
    return out


def check_metre_regression(tables, rep, atlas_path: Path = ATLAS):
    """Hard gate: a canonical line that breaks the venba rules (tkcore.prosody) at a position where an attested,
    well-formed reading with different letters scans: the reading chosen for the core is then the likely cause of
    the break. Lines that fail with no such witness stay advisory."""
    import re
    from .prosody import check
    if not atlas_path.exists():
        return
    readings = {}
    for r in read_jsonl(atlas_path):
        if r["status"].startswith(("rejected", "alternate")):
            readings.setdefault(r["kural_id"], []).append(r)
    for k in tables["kurals"]:
        lines = k.get("lines_ta")
        if not lines or k["id"] not in readings:
            continue
        res = check(lines)
        if res.ok:
            continue
        pos = _metre_positions(res.problems)
        words = [s.word for s in res.seers]
        for r in readings[k["id"]]:
            alt = [x for x in re.split(r"\n|<br\s*/?>", r["text"]) if x.strip()]
            if len(alt) != 2:
                continue
            ra = check(alt)
            if not ra.ok or len(ra.seers) != len(res.seers):
                continue
            changed = [i for i in pos if ra.seers[i - 1].word != words[i - 1]]
            if changed and all(ra.seers[i - 1].word[:1] not in BAD_INITIAL for i in changed):
                rep.add("metre_regression", k["id"],
                        f"canonical breaks the metre ({'; '.join(res.problems)}) where {r['reading_id']} "
                        f"({r['status']}) scans")
                break


def load_tables(core_dir: Path = DATA_CORE) -> dict:
    return {t: read_jsonl(core_dir / f"{t}.jsonl") for t in ("kurals", "adhikarams", "divisions")}


def run(core_dir: Path = DATA_CORE, ledger_path: Path = LEDGER, registry_path: Path = REGISTRY,
        layers_path: Path = LAYERS, gate: bool = False, atlas_path: Path = ATLAS) -> Report:
    rep = Report()
    tables = load_tables(core_dir)
    registry = reg.load(registry_path)
    check_schema(tables, rep)
    check_structure(tables, rep)
    check_text(tables, rep)
    check_provenance(tables, registry, rep)
    check_ledger(tables, read_jsonl(ledger_path), rep)
    if layers_path.exists():
        check_layers(json.loads(layers_path.read_text(encoding="utf-8")), registry, rep)
    if gate:
        check_gate(tables, rep)
        check_metre_regression(tables, rep, atlas_path)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--core", type=Path, default=DATA_CORE)
    args = ap.parse_args(argv)
    rep = run(args.core, gate=args.gate)
    print(rep)
    sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
