# Contributing

## Report a text correction

A correction to a kural, a chapter name, a translation or the commentary needs a printed source.

1. Open a [text correction](https://github.com/ashwingopalsamy/thirukkural-tamil-dataset/issues/new?template=text_correction.yml).
2. Fill in every field:
   - **Kural number**, 1 to 1330.
   - **Table**: `kurals`, `adhikarams`, `pope1886_en`, `drew_lazarus_en`, `aiyar1916_en`, `parimelazhagar_ta` or other.
   - **Text in the dataset**, copied exactly.
   - **Reading you propose.**
   - **Printed source**: edition, year, page, and a link to the scan or a photo of the page.

Kural text changes only through a ruling in `provenance/ledger/adjudications.jsonl` that cites the sources and the page. The validators refuse a core that disagrees with the ledger.

For bugs in the code or tables, use the [bug report](https://github.com/ashwingopalsamy/thirukkural-tamil-dataset/issues/new?template=bug_report.yml) form.

## Run the checks

Python 3.11 or later.

```bash
git clone https://github.com/ashwingopalsamy/thirukkural-tamil-dataset
cd thirukkural-tamil-dataset
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m tkcore.validate          # structure, NFC, provenance, ledger, layers
python -m tkcore.validate --gate   # every kural has text, a status and provenance
python -m tkcore.release --check   # card and Croissant match the data
python -m pytest
python -m tkcore.site              # regenerates the website in docs/
```

CI runs the same commands on every pull request. When `python -m tkcore.release` or `python -m tkcore.site` changes a generated file, commit it with the change that caused it.

## Data-file rules

- Kural text needs a provenance entry that cites a registered source and its file hash.
- Tamil is Unicode NFC. Forbidden code points fail validation.
- Only CC0-1.0 or public-domain content enters the core tables.
- Translations and commentary stay in their own layers, joined by `kural_id`, never in a Tamil text column.
- Model output never enters a text column. A model-computed table names its model and revision and marks every row `model_generated: true`.
- Derived tables are deterministic: two builds from the same commit are byte-identical.

## Pull requests

Keep a pull request to one change. Use [Conventional Commits](https://www.conventionalcommits.org) for titles, such as `fix(layers): ...` or `docs: ...`. By contributing, you dedicate your contribution under [CC0-1.0](LICENSE).
