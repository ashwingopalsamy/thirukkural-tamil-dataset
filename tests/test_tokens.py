import copy
import json

import pytest

from tkcore import release, tokens

TC = json.loads(release.TOKENIZER_COST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tables():
    return release.build_tables(embeddings=False)


@pytest.fixture(scope="module")
def card():
    return release.CARD_OUT.read_text(encoding="utf-8")


def test_token_counts_are_measured_on_these_texts(tables):
    assert TC["measured_on"]["texts_sha256"] == tokens.texts_sha256(tokens.token_texts(tables))
    changed = copy.deepcopy(tables)
    changed["pope1886_en"][0]["text"] += " "
    with pytest.raises(SystemExit, match="other layer text"):
        release.tokenizer_cost(changed)
    restored = copy.deepcopy(tables)
    restored["parimelazhagar_ta"][0]["text"] = None if restored["parimelazhagar_ta"][0]["text"] else "x"
    with pytest.raises(SystemExit, match="other layer text"):
        release.tokenizer_cost(restored)


def test_token_chart_is_drawn_from_the_report(card):
    chart = tokens.token_chart_text(TC)
    assert chart == tokens.token_chart_text(copy.deepcopy(TC)) and chart in card
    lines = chart.splitlines()[1:-1]
    for r in TC["tokenizers"]:
        for field in ("kural_ta", "pope_en"):
            assert any(l.endswith(f"{r['tokens_total'][field]:,}") for l in lines)
    top = max(TC["tokenizers"], key=lambda r: r["tokens_total"]["kural_ta"])
    assert tokens.BARS[8] * 40 in next(l for l in lines if l.startswith(top["tokenizer"]))
    more = sum(r["tokens_total"]["kural_ta"] > r["tokens_total"]["pope_en"] for r in TC["tokenizers"])
    assert f"under {more} of these {len(TC['tokenizers'])} tokenizers" in card


def test_card_states_what_is_model_generated(card):
    assert "No kural text, translation or commentary in this dataset is model output." in card
    assert "`embeddings_bge_m3`" in card and "model_generated: true" in card
