# Sources and checks

## Printed editions

Three 19th-century editions, scanned on archive.org, are the verification witnesses for the Tamil text.

| Source id | Edition | Scan |
|---|---|---|
| `scan:pope1886` | G. U. Pope, *The 'Sacred' Kurral of Tiruvalluva-Nayanar* (1886) | [tiruvalluvanayan00tiruuoft](https://archive.org/details/tiruvalluvanayan00tiruuoft) |
| `scan:lazarus1885` | John Lazarus and Mrugesa Mudaliyar, the Kural with Parimelazhagar's commentary (1885) | [kuraloftiruvallu00tirurich](https://archive.org/details/kuraloftiruvallu00tirurich) |
| `scan:navalar` | Arumuga Navalar's edition with Parimelazhagar's commentary | [11ThirukkuralParimelAlagarArumugaNavalarGood](https://archive.org/details/11ThirukkuralParimelAlagarArumugaNavalarGood) |

`scan_locations` gives the page image and box of each kural in each edition. 1,316 kurals are located in all three.

## Digital sources

A digital witness is a dataset or page that carries the text. Witnesses in one lineage group descend from one upstream, so their agreement counts once.

| Group | Source id | Source | Declared licence |
|---|---|---|---|
| L1 | `aitamilnadu` | [aitamilnadu/thirukkural_instruct](https://huggingface.co/datasets/aitamilnadu/thirukkural_instruct) | Apache-2.0 |
| L1 | `chandrasekar` | [Chandrasekar/thirukkural-yaappu](https://huggingface.co/datasets/Chandrasekar/thirukkural-yaappu), raw lines | CC-BY-SA-4.0 |
| L1 | `selvakumar` | [Selvakumarduraipandian/Thirukural](https://huggingface.co/datasets/Selvakumarduraipandian/Thirukural) | MIT |
| L1 | `wikisource-mulam` | [Tamil Wikisource, திருக்குறள், மூலம்](https://ta.wikisource.org/wiki/திருக்குறள்,_மூலம்), byte-identical to `chandrasekar` on 1,220 of 1,330 kurals | CC-BY-SA-4.0 |
| L2 | `yuvaraj` | [yuvarajvelmurugan/thirukkural](https://huggingface.co/datasets/yuvarajvelmurugan/thirukkural), an edited copy of L1 | CC0-1.0 |
| L3 | `wikisource-parimel` | [Tamil Wikisource, திருக்குறள் பரிமேலழகர் உரை](https://ta.wikisource.org/wiki/திருக்குறள்_பரிமேலழகர்_உரை), the seer-divided Parimelazhagar-edition text; `chandrasekar` carries the same text in its corrected lines | CC-BY-SA-4.0 |

`tamilthagaval` ([TamilThagaval/thirukkural-dataset](https://huggingface.co/datasets/TamilThagaval/thirukkural-dataset)) is gated. It is listed in the registry, and none of its content is used.

[`provenance/registry/sources.json`](../provenance/registry/sources.json) records each source's revision, the sha256 of every file used, its declared licence and its lineage group. A carrier's declared licence covers at most its uploader's own contribution, not the public-domain text inside it. The licence of each table is in [licensing](licensing.md).

## Translation and commentary sources

| Table | Work | Carrier | Rights |
|---|---|---|---|
| `pope1886_en` | G. U. Pope's verse translation (1886) | `yuvaraj` | Public domain |
| `drew_lazarus_en` | W. H. Drew (kurals 1 to 630) and John Lazarus (631 to 1330), prose translation | `yuvaraj` | Public domain |
| `aiyar1916_en` | V. V. S. Aiyar, *The Kural, or The Maxims of Tiruvalluvar* (1916) | `scan:aiyar1916`, a scan on Wikimedia Commons; kurals 6 to 10 and 36 to 40 from `se:aiyar-kural` ([Standard Ebooks](https://standardebooks.org/ebooks/thiruvalluvar/the-kural/v-v-s-aiyar), CC0-1.0) | Public domain |
| `parimelazhagar_ta` | Parimelazhagar's commentary | `selvakumar` (MIT) | Public domain text, MIT transcription |
| `parimelazhagar_ta_sa` | Parimelazhagar's commentary on the kurals `parimelazhagar_ta` withholds | `wikisource-parimel` (CC-BY-SA-4.0) | Public domain text, CC-BY-SA-4.0 transcription |

Each row names its author, work, carrier, file hash, licence and rights, and joins `kurals` by `kural_id`. [`provenance/layers.json`](../provenance/layers.json) holds the rights evidence for every layer.

## Text status

Every kural has one `text_status`.

| `text_status` | Meaning | Kurals |
|---|---|---|
| `verified_scan` | The printed editions settle the reading: confirmed on the page image (27), or the machine-read text of at least two editions matches one of the readings the sources carry (43). The `scan:` entries in `provenance` give the page and box. | 70 |
| `adjudicated` | A ruling in [`provenance/ledger/adjudications.jsonl`](../provenance/ledger/adjudications.jsonl) settles the reading; `adjudication_ids` names it. | 78 |
| `verified_digital_only` | Every digital source that carries the kural has the same letters after cleaning. It has not been compared letter by letter with a print. | 1,182 |

Each ruling lists every candidate reading, the sources that carry it, the evidence cited, the decision and its time. 101 rulings choose among sourced readings, 1 is typed from the print and keyed twice, and 1 settles a question of structure. A ruling that replaces an earlier one names it in `supersedes`.

## What is checked

- **Letters.** Each kural's readings are compared letter by letter after Unicode NFC and fixed cleaning rules that never change a Tamil letter. 1,284 kurals are also compared with the L3 text, word junctions included: 1,210 are identical, and every difference is checked against at least two of the three prints ([`provenance/reports/collation_l3.json`](../provenance/reports/collation_l3.json)).
- **Characters.** Tamil is Unicode NFC. Unassigned Tamil-block code points, ZWJ, ZWNJ, no-break space and private-use characters fail validation.
- **Provenance.** No kural text ships without a provenance entry that cites a registered source and its file hash. The validators refuse a core that disagrees with the ledger.
- **Metre.** Two rule-based checkers in [`tkcore/prosody.py`](../tkcore/prosody.py) scan every kural as kural venba. Checker v0.1 reads each printed word as one foot; 1,293 kurals scan. Checker v0.3 regroups letters as traditional scansion does; 1,323 kurals scan. A metre result is an annotation and never changes text.
- **Translations.** Each Pope and Drew/Lazarus row is compared with the printed page of its kural: 1,292 Pope rows and 1,291 Drew/Lazarus rows have at least 60% of their word 3-grams on that page (`print_match`). The release refuses a layer in which two rows carry the same text.
- **Quotations.** `quote_keys` gives each kural an exact hash and a comparison key that ignores spacing, punctuation and word joins, so a quote can be checked letter for letter.
- **Hashes.** Every kural has `text_sha256`, the sha256 of its NFC text. `MANIFEST.json` lists every release file's sha256 and a root over all kural hashes: `86d8d109697176ee8d15150255c76265cbb5a067546215210c974fee49c6a1df`.
- **Merkle proofs.** `merkle_proofs` holds an RFC 9162 inclusion proof per kural in two SHA-256 trees, one over the exact text and one over the comparison key.
- **Reproducibility.** `pyarrow` is pinned, so two builds from the same commit give byte-identical Parquet and the same `MANIFEST.json`.

```bash
python -m tkcore.validate --gate    # structure, NFC, provenance, ledger, layers, release gate
python -m tkcore.release --check    # card and Croissant match the data
python -m pytest
```
