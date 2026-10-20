"""Four tools that let an agent call the dataset instead of quoting from memory. Every Tamil or English string a tool
returns is copied from a release table; nothing is generated, and every kural comes with a Merkle proof against the
roots in MANIFEST.json and the card.

  find_kural      a Tamil quote of any quality -> ranked kurals (FTS5 trigram BM25 over compare_key)
  get_kural       a number -> text, chapter, citation, translations, proof
  verify_quote    a quote (and optionally the number it claims) -> verdict, the words that differ, proof
  search_english  English words -> kurals whose Pope or Drew/Lazarus translation matches (FTS5 porter)

The Pydantic models below are the one source for every interface in agents/ (JSON Schema, OpenAPI 3.1, `input_schema` and
OpenAI tool definitions); the MCP server (tkcore.mcp_server) serves the same functions.

  python -m tkcore.agent_tools call verify_quote '{"quote": "..."}'
  python -m tkcore.agent_tools emit        write agents/ from the models
  python -m tkcore.agent_tools --check     fail if agents/ differs from what the models give
  python -m tkcore.agent_tools serve       HTTP on 127.0.0.1:8765, POST /v1/<tool> (the OpenAPI document)

The tools read a SQLite file built from tkcore.release.build_tables() into dist/agents/, rebuilt when the data changes.
"""
import argparse
import copy
import difflib
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import ROOT, merkle
from .signature import compare_key

AGENTS = ROOT / "agents"
DB_PATH = ROOT / "dist" / "agents" / "thirukkural.sqlite"
DB_VERSION = 1
LAYERS = {"pope1886_en": "pope1886_en", "drew_lazarus_en": "drew_lazarus_en", "parimelazhagar_ta": "parimelazhagar_ta"}
Layer = Literal["pope1886_en", "drew_lazarus_en", "parimelazhagar_ta"]
MIN_SIMILARITY = 0.6  # below this a quote is not taken to be any kural


# ---------------------------------------------------------------- interfaces

class FindKuralIn(BaseModel):
    quote: str = Field(description="A Tamil quote of any quality: partial, misspelt, spaced or punctuated differently, one line or two.")
    limit: int = Field(5, ge=1, le=20, description="How many candidates to return, 1 to 20.")


class GetKuralIn(BaseModel):
    number: int = Field(ge=1, le=1330, description="Kural number, 1 to 1330.")
    layers: list[Layer] = Field(["pope1886_en", "drew_lazarus_en"], description="Translation or commentary configs to include.")


class VerifyQuoteIn(BaseModel):
    quote: str = Field(description="The Tamil text to check, exactly as the user or a model wrote it.")
    number: Optional[int] = Field(None, ge=1, le=1330, description="The kural it claims to be, 1 to 1330. Omit to let the tool find it.")


class SearchEnglishIn(BaseModel):
    query: str = Field(description="English words to look for in the public-domain translations, e.g. 'friendship adversity'.")
    limit: int = Field(5, ge=1, le=20, description="How many kurals to return, 1 to 20.")


class Chapter(BaseModel):
    number: int
    name_ta: str
    name_en: Optional[str] = Field(description="English title where printed in Pope 1886, else null.")


class Translation(BaseModel):
    config: str = Field(description="The release config the text comes from.")
    author: str
    rights: str
    carrier_license: str
    text: str


class Proof(BaseModel):
    tree: Literal["exact", "letters"] = Field(description="exact pins the NFC text; letters pins compare_key(text).")
    root_sha256: str = Field(description="The tree's root, as published in MANIFEST.json and the card.")
    leaf: str = Field(description="The leaf bytes (UTF-8 canonical JSON). Leaf hash = SHA-256(0x00 || leaf).")
    leaf_index: int
    tree_size: int
    path: list[str] = Field(description="RFC 9162 audit path, hex SHA-256, leaf to root. Node hash = SHA-256(0x01 || left || right).")
    verified: bool = Field(description="This tool re-checked the path against the root before answering.")


class Kural(BaseModel):
    id: str
    number: int
    chapter: Chapter
    position: int = Field(description="Verse 1 to 10 within the chapter.")
    text: str = Field(description="Canonical Tamil, two lines joined by a newline. Quote this exactly.")
    text_sha256: str
    text_status: str = Field(description="verified_scan, adjudicated or verified_digital_only (see the dataset card).")
    transliteration: str = Field(description="ISO 15919, a reading aid, not the text.")
    citation_en: str
    citation_ta: str
    translations: list[Translation] = []
    proof: Proof


class Candidate(BaseModel):
    id: str
    number: int
    text: str
    similarity: Optional[float] = Field(description="Letters-only similarity of the quote to this kural, 0 to 1; null for English search.")


class Candidates(BaseModel):
    candidates: list[Candidate]


class WordDiff(BaseModel):
    op: Literal["replace", "missing", "extra"]
    quote: str = Field(description="What the quote has here ('' if missing).")
    text: str = Field(description="What the canonical text has here ('' if extra).")


class Verdict(BaseModel):
    verdict: Literal["exact", "same_letters", "known_reading", "misquote", "not_found"] = Field(
        description="exact: identical to the canonical text after NFC. same_letters: only spacing, punctuation or joining "
                    "differ. known_reading: a reading a witness carries that the dataset did not adopt. misquote: close to "
                    "a kural but with other letters. not_found: no kural is close.")
    kural: Optional[Kural] = None
    similarity: float
    diff: list[WordDiff] = []
    reading_status: Optional[str] = Field(None, description="For known_reading: the reading's status in variants_atlas.")


# ---------------------------------------------------------------- the database

def _fingerprint() -> str:
    from . import release
    paths = [ROOT / "data" / "core" / "kurals.jsonl", merkle.PROOFS, *sorted((ROOT / "data" / "layers").glob("*.jsonl")),
             *sorted((ROOT / "data" / "signature").glob("*.jsonl")), Path(release.__file__), Path(__file__)]
    h = hashlib.sha256(str(DB_VERSION).encode())
    for p in paths:
        h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()


def build_db(path: Path = DB_PATH) -> Path:
    """Write the SQLite file from the release tables, in a fixed order."""
    from .release import build_tables
    t = build_tables()
    r = merkle.roots(t["kurals"])
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("""
    CREATE TABLE kurals (id TEXT PRIMARY KEY, number INTEGER UNIQUE, adhikaram INTEGER, adhikaram_ta TEXT, adhikaram_en TEXT,
      position INTEGER, text TEXT, text_sha256 TEXT, key TEXT, text_status TEXT, translit TEXT, citation_en TEXT,
      citation_ta TEXT, leaf_index INTEGER, tree_size INTEGER, exact_path TEXT, letters_path TEXT);
    CREATE TABLE translations (kural_id TEXT, config TEXT, author TEXT, rights TEXT, carrier_license TEXT, text TEXT);
    CREATE TABLE readings (kural_id TEXT, reading_id TEXT, status TEXT, key TEXT);
    CREATE VIRTUAL TABLE kural_fts USING fts5(key, kural_id UNINDEXED, tokenize='trigram');
    CREATE VIRTUAL TABLE en_fts USING fts5(text, kural_id UNINDEXED, config UNINDEXED, tokenize='porter unicode61');
    CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    der = {d["kural_id"]: d for d in t["derived"]}
    qk = {q["kural_id"]: q for q in t["quote_keys"]}
    pf = {p["kural_id"]: p for p in t["merkle_proofs"]}
    for k in t["kurals"]:
        q, p = qk[k["id"]], pf[k["id"]]
        db.execute("INSERT INTO kurals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            k["id"], k["number"], k["adhikaram_number"], k["adhikaram_name_ta"], k["adhikaram_name_en"], k["position"],
            k["text_ta"], k["text_sha256"], compare_key(k["text_ta"]), k["text_status"],
            "\n".join(der[k["id"]]["translit_iso15919"]), q["citation_en"], q["citation_ta"], p["leaf_index"],
            p["tree_size"], json.dumps(p["exact_path"]), json.dumps(p["letters_path"])))
        db.execute("INSERT INTO kural_fts VALUES (?,?)", (compare_key(k["text_ta"]), k["id"]))
    for name in LAYERS:
        for row in t[name]:
            if row["text"] is None:  # withheld by the release (coverage missing)
                continue
            db.execute("INSERT INTO translations VALUES (?,?,?,?,?,?)", (row["kural_id"], name, row["author"], row["rights"],
                                                                       row["carrier_license"], row["text"]))
            if row["lang"] == "en":
                db.execute("INSERT INTO en_fts VALUES (?,?,?)", (row["text"], row["kural_id"], name))
    for name in ("variants_atlas", "variants_atlas_sa"):
        for a in t[name]:
            db.execute("INSERT INTO readings VALUES (?,?,?,?)", (a["kural_id"], a["reading_id"], a["status"], compare_key(a["text"])))
    db.executemany("INSERT INTO meta VALUES (?,?)", [("fingerprint", _fingerprint()), ("exact_root", r["exact"]),
                                                    ("letters_root", r["letters"])])
    db.commit()
    db.execute("VACUUM")
    db.close()
    tmp.replace(path)
    return path


_DB: dict[Path, sqlite3.Connection] = {}


def db(path: Path = DB_PATH) -> sqlite3.Connection:
    if path not in _DB:
        fresh = False
        if path.exists():
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                fresh = c.execute("SELECT v FROM meta WHERE k='fingerprint'").fetchone()[0] == _fingerprint()
            except sqlite3.Error:
                pass
            c.close()
        if not fresh:
            build_db(path)
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        c.row_factory = sqlite3.Row
        _DB[path] = c
    return _DB[path]


def _meta(k: str) -> str:
    return db().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()[0]


# ---------------------------------------------------------------- the tools

def _proof(row, tree: str) -> Proof:
    letters = tree == "letters"
    leaf = merkle.leaf_bytes(row["id"], row["number"], row["text"], letters)
    path = json.loads(row["letters_path" if letters else "exact_path"])
    root = _meta("letters_root" if letters else "exact_root")
    ok = merkle.verify(row["leaf_index"], row["tree_size"], leaf, [bytes.fromhex(h) for h in path], bytes.fromhex(root))
    return Proof(tree=tree, root_sha256=root, leaf=leaf.decode("utf-8"), leaf_index=row["leaf_index"],
                 tree_size=row["tree_size"], path=path, verified=ok)


def _kural(row, layers=(), tree: str = "exact") -> Kural:
    tr = [Translation(config=t["config"], author=t["author"], rights=t["rights"], carrier_license=t["carrier_license"],
                      text=t["text"])
          for t in db().execute("SELECT * FROM translations WHERE kural_id=? ORDER BY config", (row["id"],))
          if t["config"] in layers]
    return Kural(id=row["id"], number=row["number"], position=row["position"], text=row["text"],
                 chapter=Chapter(number=row["adhikaram"], name_ta=row["adhikaram_ta"], name_en=row["adhikaram_en"]),
                 text_sha256=row["text_sha256"], text_status=row["text_status"], transliteration=row["translit"],
                 citation_en=row["citation_en"], citation_ta=row["citation_ta"], translations=tr, proof=_proof(row, tree))


def _by_number(number: int):
    row = db().execute("SELECT * FROM kurals WHERE number=?", (number,)).fetchone()
    if row is None:
        raise ValueError(f"no kural {number}; numbers run 1 to 1330")
    return row


def _sim(a: str, b: str) -> float:
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)


def _window_sim(key: str, kural_key: str) -> float:
    """A fragment is scored against its best-matching stretch of the kural, so half a kural can score 1."""
    if key in kural_key:
        return 1.0
    if len(key) >= len(kural_key):
        return _sim(key, kural_key)
    m = difflib.SequenceMatcher(None, key, kural_key, autojunk=False)
    return round(sum(b.size for b in m.get_matching_blocks()) / len(key), 4)


def find_kural(quote: str, limit: int = 5) -> Candidates:
    key = compare_key(quote)
    grams = sorted({key[i:i + 3] for i in range(len(key) - 2)})
    if not grams:
        return Candidates(candidates=[])
    q = " OR ".join('"' + g.replace('"', '""') + '"' for g in grams)
    ids = [r[0] for r in db().execute("SELECT kural_id FROM kural_fts WHERE kural_fts MATCH ? ORDER BY bm25(kural_fts) "
                                      "LIMIT ?", (q, max(limit, 10)))]
    rows = [db().execute("SELECT * FROM kurals WHERE id=?", (i,)).fetchone() for i in ids]
    scored = sorted(((_window_sim(key, r["key"]), i, r) for i, r in enumerate(rows)), key=lambda x: (-x[0], x[1]))[:limit]
    return Candidates(candidates=[Candidate(id=r["id"], number=r["number"], text=r["text"], similarity=s)
                                  for s, _, r in scored])


def get_kural(number: int, layers: list[str] = ("pope1886_en", "drew_lazarus_en")) -> Kural:
    return _kural(_by_number(number), layers)


def _word_diff(quote: str, text: str) -> list[WordDiff]:
    qa, ta = quote.split(), text.split()
    ops = difflib.SequenceMatcher(None, [compare_key(w) for w in qa], [compare_key(w) for w in ta], autojunk=False)
    return [WordDiff(op={"replace": "replace", "delete": "extra", "insert": "missing"}[op],
                     quote=" ".join(qa[i1:i2]), text=" ".join(ta[j1:j2]))
            for op, i1, i2, j1, j2 in ops.get_opcodes() if op != "equal"]


def verify_quote(quote: str, number: Optional[int] = None) -> Verdict:
    key = compare_key(quote)
    if number is None:
        c = find_kural(quote, 1).candidates
        if not c or c[0].similarity < MIN_SIMILARITY:
            return Verdict(verdict="not_found", similarity=c[0].similarity if c else 0.0)
        number = c[0].number
    row = _by_number(number)
    if unicodedata.normalize("NFC", quote.strip()) == row["text"]:
        return Verdict(verdict="exact", kural=_kural(row), similarity=1.0)
    if key == row["key"]:
        return Verdict(verdict="same_letters", kural=_kural(row, (), "letters"), similarity=1.0)
    sim = _sim(key, row["key"])
    rd = db().execute("SELECT status FROM readings WHERE kural_id=? AND key=? AND status != 'canonical' ORDER BY reading_id",
                      (row["id"], key)).fetchone()
    if rd:
        return Verdict(verdict="known_reading", kural=_kural(row), similarity=sim, diff=_word_diff(quote, row["text"]),
                       reading_status=rd["status"])
    if sim >= MIN_SIMILARITY:
        return Verdict(verdict="misquote", kural=_kural(row), similarity=sim, diff=_word_diff(quote, row["text"]))
    return Verdict(verdict="not_found", similarity=sim)


def search_english(query: str, limit: int = 5) -> Candidates:
    words = re.findall(r"[A-Za-z]+", query)
    out: list[str] = []
    for joiner in (" AND ", " OR "):  # every word first, then any word
        if len(out) >= limit or not words:
            break
        q = joiner.join(f'"{w}"' for w in words)
        for r in db().execute("SELECT kural_id FROM en_fts WHERE en_fts MATCH ? ORDER BY bm25(en_fts), kural_id LIMIT ?",
                              (q, limit * 3)):
            if r[0] not in out:
                out.append(r[0])
    rows = [db().execute("SELECT * FROM kurals WHERE id=?", (i,)).fetchone() for i in out[:limit]]
    return Candidates(candidates=[Candidate(id=r["id"], number=r["number"], text=r["text"], similarity=None) for r in rows])


TOOLS = {  # name -> (function, input model, output model, description)
    "find_kural": (find_kural, FindKuralIn, Candidates,
                   "Find which Thirukkural a Tamil quote comes from, even if it is partial, misspelt or differently spaced. "
                   "Returns ranked candidates with the canonical text. Use this before quoting any kural."),
    "get_kural": (get_kural, GetKuralIn, Kural,
                  "Get one Thirukkural by number (1 to 1330): canonical Tamil text, chapter, transliteration, citation, "
                  "public-domain translations and a Merkle proof of the text."),
    "verify_quote": (verify_quote, VerifyQuoteIn, Verdict,
                     "Check a Tamil quote of a kural against the canonical text. Says whether it is exact, differs only in "
                     "spacing or punctuation, is a known variant reading, or is a misquote, and lists the words that differ. "
                     "Use it on any kural a model wrote."),
    "search_english": (search_english, SearchEnglishIn, Candidates,
                       "Find kurals by English keywords in the Pope (1886) and Drew/Lazarus translations. Returns the "
                       "canonical Tamil text of each match."),
}


def call(name: str, args: dict) -> dict:
    fn, inp, _, _ = TOOLS[name]
    return fn(**inp.model_validate(args).model_dump()).model_dump(mode="json")


# ---------------------------------------------------------------- agents/

def _strip_titles(s):
    if isinstance(s, dict):
        return {k: _strip_titles(v) for k, v in s.items() if not (k == "title" and isinstance(v, str))}
    if isinstance(s, list):
        return [_strip_titles(v) for v in s]
    return s


def schemas() -> dict:
    return {n: (_strip_titles(i.model_json_schema()), _strip_titles(o.model_json_schema(mode="serialization")), d)
            for n, (_, i, o, d) in TOOLS.items()}


def openai_strict(schema: dict) -> dict:
    """OpenAI strict function schemas: every property required, optional ones nullable, no defaults or numeric bounds
    (the bounds stay in the descriptions), every object closed."""
    s = copy.deepcopy(schema)

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "object" and "properties" in o:
                req = set(o.get("required", []))
                for k, v in o["properties"].items():
                    v.pop("default", None)
                    if k not in req and "anyOf" not in v:
                        o["properties"][k] = {"anyOf": [v, {"type": "null"}]}
                o["required"] = list(o["properties"])
                o["additionalProperties"] = False
            for k in ("minimum", "maximum", "default"):
                o.pop(k, None)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(s)
    return s


def openapi(sc: dict) -> dict:
    from .release import META, VERSION
    comps, paths = {}, {}
    for name, (i, o, desc) in sc.items():
        for tag, s in (("In", i), ("Out", o)):
            s = copy.deepcopy(s)
            comps.update(s.pop("$defs", {}))
            comps[f"{name}_{tag}"] = s
        paths[f"/v1/{name}"] = {"post": {
            "operationId": name, "summary": desc.split(". ")[0] + ".", "description": desc,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}_In"}}}},
            "responses": {"200": {"description": "Result", "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}_Out"}}}},
                          "422": {"description": "Invalid arguments"}}}}
    doc = {"openapi": "3.1.0",
           "info": {"title": "Thirukkural tools", "version": VERSION, "license": {"name": "CC0-1.0", "identifier": "CC0-1.0"},
                    "description": "Read-only lookup, verification and search over the canonical Thirukkural "
                                   f"({META['hf_repo']}). Every string returned is copied from the dataset."},
           "servers": [{"url": "http://127.0.0.1:8765"}], "paths": paths, "components": {"schemas": dict(sorted(comps.items()))}}
    return json.loads(json.dumps(doc).replace("#/$defs/", "#/components/schemas/"))


def _dump(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1) + "\n"


def interface_files() -> dict[str, str]:
    """agents/<path> -> content, all generated from the models."""
    sc = schemas()
    files = {}
    for name, (i, o, _) in sc.items():
        for tag, s in (("input", i), ("output", o)):
            files[f"schemas/{name}.{tag}.json"] = _dump({"$schema": "https://json-schema.org/draft/2020-12/schema", **s})
    files["tools.json"] = _dump([{"name": n, "description": d, "input_schema": i} for n, (i, _, d) in sc.items()])
    files["tools.openai.json"] = _dump([{"type": "function", "name": n, "description": d, "parameters": openai_strict(i),
                                         "strict": True} for n, (i, _, d) in sc.items()])
    files["openapi.json"] = _dump(openapi(sc))
    return files


def emit() -> None:
    for rel, text in interface_files().items():
        (AGENTS / rel).parent.mkdir(parents=True, exist_ok=True)
        (AGENTS / rel).write_text(text, encoding="utf-8")


def stale() -> list[str]:
    return [rel for rel, text in interface_files().items()
            if not (AGENTS / rel).exists() or (AGENTS / rel).read_text(encoding="utf-8") != text]


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        name = self.path.removeprefix("/v1/")
        try:
            if name not in TOOLS:
                raise ValueError(f"unknown tool {name}")
            body, code = json.dumps(call(name, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))), 200
        except Exception as e:  # noqa: BLE001 - report any bad argument as a 422 with its message
            body, code = json.dumps({"error": str(e)}), 422
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def server(port: int = 8765) -> ThreadingHTTPServer:
    db()
    return ThreadingHTTPServer(("127.0.0.1", port), _Handler)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", choices=["call", "emit", "serve", "build-db"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--check", action="store_true", help="fail if agents/ is stale")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    if a.check:
        if s := stale():
            sys.exit(f"stale in agents/: {s}; run python -m tkcore.agent_tools emit")
        return
    if a.command == "call":
        print(json.dumps(call(a.args[0], json.loads(a.args[1] if len(a.args) > 1 else "{}")), ensure_ascii=False, indent=1))
    elif a.command == "emit":
        emit()
        print(f"agents/: {len(interface_files())} files")
    elif a.command == "build-db":
        print(build_db())
    elif a.command == "serve":
        print(f"POST http://127.0.0.1:{a.port}/v1/<tool>")
        server(a.port).serve_forever()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
