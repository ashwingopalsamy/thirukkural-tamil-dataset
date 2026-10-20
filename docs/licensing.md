# Licensing

Each table carries its own licence. The Thirukkural and the 19th-century and early 20th-century works here are in the public domain; the licence of a table covers what this project adds and, where a transcription comes from a licensed carrier, that carrier's terms.

## By table

| Table | Licence | Basis |
|---|---|---|
| `kurals`, `adhikarams`, `divisions` | CC0-1.0 | The text is centuries old and in the public domain; structure, ids, provenance and status are this project's work |
| `pope1886_en` | CC0-1.0 | Public domain: published 1886, G. U. Pope died 1908 |
| `drew_lazarus_en` | CC0-1.0 | Public domain: W. H. Drew died 1856, John Lazarus died 1925 |
| `aiyar1916_en` | CC0-1.0 | Public domain: published 1916, V. V. S. Aiyar died 1925. CC0 covers this dataset's transcription of the scan, its rule corrections and rulings |
| `seer`, `derived`, `quote_keys`, `sound_index`, `echo_graph` | CC0-1.0 | Computed from the canonical text by rule |
| `tasks`, `kuralbench_lite`, `agent_card`, `merkle_proofs` | CC0-1.0 | Built from the canonical text by rule |
| `ledger`, `sources`, `scan_locations`, `variants_atlas` | CC0-1.0 | This dataset's records of sources, rulings, page locations and readings |
| `parimelazhagar_ta`, `parimelazhagar_struct` | MIT | The commentary is in the public domain; this transcription is shared under its carrier's MIT terms, with attribution to `Selvakumarduraipandian/Thirukural`, column `Parimezhalagar_Urai` |
| `parimelazhagar_ta_sa` | CC-BY-SA-4.0 | Tamil Wikisource's transcription ([திருக்குறள் பரிமேலழகர் உரை](https://ta.wikisource.org/wiki/திருக்குறள்_பரிமேலழகர்_உரை)), with attribution to its contributors |
| `variants_atlas_sa` | CC-BY-SA-4.0 | Readings carried only by CC-BY-SA sources: Chandrasekar's seer-divided forms ([Chandrasekar/thirukkural-yaappu](https://huggingface.co/datasets/Chandrasekar/thirukkural-yaappu)) and Tamil Wikisource |
| `embeddings_bge_m3` | MIT | The licence declared on the `BAAI/bge-m3` model card at the revision used |

19 tables are CC0-1.0. The CC-BY-SA readings and commentary rows are kept in tables of their own, so the CC0 tables stay CC0. Join them on `kural_id`.

## Code and metadata

Everything else in this repository, including `tkcore/`, `scripts/`, `tests/`, the schema, the release metadata, the documentation and the website in `docs/`, is dedicated to the public domain under [CC0-1.0](../LICENSE). Licence texts: [`LICENSES/CC0-1.0.txt`](../LICENSES/CC0-1.0.txt), [`release/licenses/MIT.txt`](../release/licenses/MIT.txt).

## Carrier licences

A carrier is a dataset that holds a transcription. [`provenance/registry/sources.json`](../provenance/registry/sources.json) records each carrier's declared licence (`declared_license`) as evidence of its terms. A carrier's licence covers at most the uploader's own contribution, not the public-domain text inside it. Every row in a translation or commentary table also states `carrier_license` and `rights`.

## Attribution

When you redistribute a CC-BY-SA-4.0 or MIT table, keep the attribution above and the licence notice. For the CC0 tables, attribution is appreciated and not required; [`CITATION.cff`](../CITATION.cff) has the citation.

## Rights requests

If you hold rights in any text here, open an issue titled `Rights: <table>`. The table is removed from the next release while the request is reviewed.
