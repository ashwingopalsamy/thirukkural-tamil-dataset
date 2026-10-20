# Frequently asked questions

## What is the Thirukkural?

The Thirukkural (திருக்குறள், also spelled Tirukkural or Thirukural) is a classical Tamil work by Thiruvalluvar. It has 1,330 couplets, called kurals, in 133 chapters (adhikarams) of ten kurals each, in three books (paal): அறத்துப்பால் (chapters 1 to 38), பொருட்பால் (39 to 108) and காமத்துப்பால் (109 to 133).

## What is the Thirukkural Tamil dataset?

The Tamil text of all 1,330 kurals, with permanent ids `tk:0001` to `tk:1330`, each with its sources, verification status and sha256. Separate tables add the chapter and book structure, three public-domain English translations, Parimelazhagar's Tamil commentary, the metre of every foot, every attested variant reading, evaluation tasks, agent tables, Merkle proofs and BGE-M3 vectors: 24 tables in all. The [data dictionary](data-dictionary.md) lists every field.

## How many kurals and chapters does it have?

1,330 kurals in 133 chapters and three books. Each chapter has ten kurals. The `kurals` table has one row per kural and the `adhikarams` table one row per chapter, with its Tamil name and, for 118 chapters, the English title printed in Pope's 1886 edition.

## Is there a Thirukkural dataset in JSON or CSV?

Yes. Every table is JSON Lines (one JSON object per line) in the [`data/`](../data) folder: `data/core/kurals.jsonl` holds the Tamil text. `python -m tkcore.release` writes all 24 tables as Parquet. There is no CSV file; pandas converts any table in one line:

```python
import pandas as pd
base = "https://raw.githubusercontent.com/ashwingopalsamy/thirukkural-tamil-dataset/main"
pd.read_json(f"{base}/data/core/kurals.jsonl", lines=True).to_csv("kurals.csv", index=False)
```

## How do I load it in Python or with Hugging Face datasets?

With pandas:

```python
import pandas as pd
base = "https://raw.githubusercontent.com/ashwingopalsamy/thirukkural-tamil-dataset/main"
kurals = pd.read_json(f"{base}/data/core/kurals.jsonl", lines=True)
```

With Hugging Face `datasets`, from the same file:

```python
from datasets import load_dataset
kurals = load_dataset("json", data_files=f"{base}/data/core/kurals.jsonl", split="train")
```

Join a translation on `kural_id`, for example `data/layers/pope1886-en.jsonl`. See the [README](../README.md#quick-start).

## Which English translations does it include?

Three public-domain translations, each in its own table and joined to the Tamil by `kural_id`: G. U. Pope's 1886 verse translation (`pope1886_en`), the prose translation of W. H. Drew and John Lazarus (`drew_lazarus_en`), and V. V. S. Aiyar's 1916 translation (`aiyar1916_en`). The Tamil text is the dataset; the translations are layers on it.

## Is the Tamil text verified?

Yes. Each kural is compared letter by letter across six digital sources, grouped by lineage so copies of one upstream count once. Where they differ, three 19th-century printed editions settle the reading, and a remaining choice is a ruling in the ledger. Each kural's `text_status` says which applies: 70 `verified_scan`, 78 `adjudicated`, 1,182 `verified_digital_only`. See [sources and checks](sources.md).

## Which licence does it use?

The Tamil text, the structure, the three English translations and 19 of the 24 tables are CC0-1.0. Parimelazhagar's commentary (`parimelazhagar_ta`, `parimelazhagar_struct`) is MIT under its carrier's terms. Rows carried only under CC-BY-SA-4.0 are in tables of their own (`parimelazhagar_ta_sa`, `variants_atlas_sa`). The vectors are MIT. See [licensing](licensing.md).

## Does it work with LLMs and MCP?

Yes. `python -m tkcore.mcp_server` serves four read-only tools over MCP: `find_kural`, `get_kural`, `verify_quote` and `search_english`. `python -m tkcore.agent_tools serve` serves the same tools over HTTP. Every string they return is copied from the tables, with the Merkle proof checked. Tool definitions for API calls, JSON Schemas and OpenAPI are in [`agents/`](../agents). Register the MCP server with:

```json
{ "mcpServers": { "thirukkural": { "command": "python", "args": ["-m", "tkcore.mcp_server"] } } }
```

## Is any of it model-generated?

Only the vectors. `embeddings_bge_m3` holds BGE-M3 vectors, numbers and not text, and every row says `model_generated: true`. No kural text, translation or commentary is model output.

## How do I check that a quote is exact?

Compute the sha256 of the NFC-normalised `text_ta` and compare it with `text_sha256`. To check one kural against a published root, use its row in `merkle_proofs` (RFC 9162). To check a quote typed with different spacing or punctuation, compare its comparison key with `quote_keys`, or call `verify_quote`.

## What is kural venba?

The metre of every kural: two lines, of four and three metrical feet (seer), with fixed rules for how each foot links to the next. The `seer` table scans all 9,309 feet, and `derived` gives two rule-based metre verdicts per kural. 1,323 kurals scan under checker v0.3.

## Which numbering and order does it follow?

Parimelazhagar's: the numbering, order and nine-section (iyal) grouping of his commentary. The `divisions` table also keeps the grouping used by the digital sources.

## Can I use it to evaluate a language model?

Yes. `kuralbench_lite` asks a model to quote each kural by number and to give its second line from its first. `tasks` adds line completion, chapter naming, quote verification and masked words, with answer keys. A rule scores answers letter by letter; no model judges. Harnesses for Inspect and lm-evaluation-harness are in [`evals/`](../evals). Every evaluation row carries a canary string: keep the dataset out of training corpora for models you test with it.

## How do I cite it?

Use [`CITATION.cff`](../CITATION.cff). To cite one kural, give its id and `text_sha256`, for example kural 34, `tk:0034`, `5faee0bcb2efc501ba55522190813002c1863f130a8760061243f4bdaf862b4e`.

## How do I report a mistake?

Open a [text correction](https://github.com/ashwingopalsamy/thirukkural-tamil-dataset/issues/new?template=text_correction.yml) with the kural number and the printed source: edition, page and a link to the scan. See [CONTRIBUTING](../CONTRIBUTING.md).
