# Changelog

Versions follow semantic versioning. A major version changes the text of at least one kural; a minor version adds tables, fields or status changes; a patch fixes metadata. Each release lists every kural whose text changed, by id, with the old and new `text_sha256`.

## 1.0.0 (2026-10-20)

### Text

- All 1,330 kurals in Tamil, with ids `tk:0001` to `tk:1330`, a verification status and provenance: 70 `verified_scan`, 78 `adjudicated`, 1,182 `verified_digital_only`.
- 103 rulings in the ledger, 85 on text and 18 on names.
- `text_sha256` on every kural. `MANIFEST.json` holds every file's hash and a root hash over all kural hashes. Two Merkle roots, exact and letters.

### Tables

| Group | Table | What it holds |
|---|---|---|
| Text | `kurals` | The two Tamil lines of each kural, its place in the book, `text_status`, `text_sha256` and provenance |
| Text | `adhikarams` | The 133 chapters: Tamil names, English titles printed in Pope 1886, kural ranges |
| Text | `divisions` | The three books (paal) and the section (iyal) schemes |
| English | `pope1886_en` | G. U. Pope's 1886 verse translation, each row compared with the printed page |
| English | `drew_lazarus_en` | The prose translation of W. H. Drew and John Lazarus, each row compared with the printed page |
| English | `aiyar1916_en` | V. V. S. Aiyar's 1916 translation, transcribed from a scan |
| Commentary | `parimelazhagar_ta` | Parimelazhagar's Tamil commentary (MIT) |
| Commentary | `parimelazhagar_ta_sa` | The commentary rows `parimelazhagar_ta` withholds, from Tamil Wikisource (CC-BY-SA-4.0) |
| Commentary | `parimelazhagar_struct` | The commentary parsed by rule: word glosses, situation notes, groupings, reported readings |
| Metre and sound | `seer` | Every metrical foot of every kural, with its asai and traditional name |
| Metre and sound | `derived` | Metre verdicts of checkers v0.1 and v0.3, search form, ISO 15919 transliteration |
| Metre and sound | `sound_index` | Letter weights, asai and seer patterns, monai, edukai, end rhyme |
| Readings and links | `variants_atlas` | Every attested reading of every kural, classified against the canonical text |
| Readings and links | `variants_atlas_sa` | Readings carried only under CC-BY-SA-4.0 |
| Readings and links | `quote_keys` | Exact hash, comparison key, per-line keys and citations for checking a quote |
| Readings and links | `echo_graph` | Links between kurals that share rare words or a chapter |
| Evaluation | `tasks` | Line completion, chapter naming, quote verification and masked words, with answer keys |
| Evaluation | `kuralbench_lite` | Quote a kural from its number, and its second line from its first |
| Agents | `agent_card` | One compact JSON object per kural for an agent to pass to a model |
| Agents | `merkle_proofs` | An RFC 9162 inclusion proof per kural in each Merkle tree |
| Evidence | `ledger` | Every ruling, with its candidates, sources, evidence and time |
| Evidence | `sources` | Every source, with lineage group, declared licence and file hashes |
| Evidence | `scan_locations` | Where each kural is printed in three scanned editions |
| Vectors | `embeddings_bge_m3` | One BAAI/bge-m3 vector per kural, marked `model_generated: true` |

### Tools

- Agent tools `find_kural`, `get_kural`, `verify_quote` and `search_english`, served over MCP and HTTP, with JSON Schemas, OpenAPI 3.1 and tool definitions in `input_schema` and OpenAI formats.
- KuralBench-lite harnesses for Inspect and lm-evaluation-harness.
- Token counts for the text under seven tokenizers, and a BGE-M3 retrieval benchmark with a no-model baseline.
- Croissant 1.1 metadata with the Responsible AI fields, keys and references.
- A static website with one page per kural and per chapter.
