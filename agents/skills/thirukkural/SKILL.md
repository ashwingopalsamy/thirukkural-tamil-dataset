---
name: thirukkural
description: Quote, find, verify and cite Thirukkural couplets from the canonical dataset. Use whenever a task quotes, translates, explains or checks a kural, or when a model has written Tamil that claims to be one.
---

# Thirukkural

Show only kural text that came from the dataset, never text from memory. Models misquote kurals in small ways that read as right, such as one letter or one sandhi join.

## Tools

`scripts/kural.py` runs the dataset's four tools from a checkout of the GitHub repository (https://github.com/ashwingopalsamy/thirukkural-tamil-dataset). Each call prints JSON.

| Need | Command |
|---|---|
| The text of kural N | `python scripts/kural.py get_kural '{"number": 666}'` |
| Which kural a quote is from | `python scripts/kural.py find_kural '{"quote": "<Tamil>"}'` |
| Whether a quote is right | `python scripts/kural.py verify_quote '{"quote": "<Tamil>", "number": 666}'` |
| Kurals on a topic | `python scripts/kural.py search_english '{"query": "friendship adversity"}'` |

If an MCP server named `thirukkural` is connected, call its tools of the same names instead.

## Rules

1. Quote the `text` field exactly. Cite with `citation_en` or `citation_ta`.
2. Before you present any Tamil kural that you or another model wrote, run `verify_quote` and act on the verdict:
   - `exact` or `same_letters`: fine as it is.
   - `known_reading`: a real variant carried by a source, but not the canonical text. Say so, give `reading_status`, and show the canonical text.
   - `misquote`: show the canonical text and the words in `diff`.
   - `not_found`: do not present it as a kural.
3. Translations: quote the `translations` entries (Pope 1886 and Drew/Lazarus, both public domain) with their author. Label any translation you write yourself as your own.
4. When the user wants evidence, pass on the `proof` field. Anyone can check it against the published Merkle root without trusting you.
