"""PRD NA-03 AC5: 1–6 third-party-OK articles per event, ≤ 600 news tokens, unique event ids."""

from __future__ import annotations

import itertools
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.events import load_events_config
from newsaction.events.aggregate import build_window
from newsaction.events.tokens import ArticleText, cap_articles, render_block
from newsaction.paths import ROOT


class WordTokenizer:
    """A whitespace tokenizer with the HF call signature used by ``tokens`` (one token per word)."""

    def _one(self, text: str, offsets: bool) -> dict[str, list[object]]:
        ids, offs, pos = [], [], 0
        for w in text.split():
            start = text.index(w, pos)
            pos = start + len(w)
            ids.append(hash(w) % 1000)
            offs.append((start, pos))
        return {"input_ids": ids, "offset_mapping": offs} if offsets else {"input_ids": ids}

    def __call__(self, text: str | list[str], **kw: object) -> dict[str, list[object]]:
        off = bool(kw.get("return_offsets_mapping"))
        if isinstance(text, list):
            return {"input_ids": [self._one(t, off)["input_ids"] for t in text]}
        return self._one(text, off)


def _enc(text: str) -> list[int]:
    return [0] * len(text.split())


def _off(text: str) -> list[tuple[int, int]]:
    out, pos = [], 0
    for w in text.split():
        s = text.index(w, pos)
        pos = s + len(w)
        out.append((s, pos))
    return out


def _art(n_title: int, n_snip: int, tag: str) -> ArticleText:
    return ArticleText(" ".join([f"{tag}t"] * n_title), " ".join([f"{tag}s{i}" for i in range(n_snip)]))


def test_cap_drops_lowest_score_articles_first() -> None:
    arts = [_art(5, 40, "a"), _art(5, 40, "b"), _art(5, 40, "c")]
    capped = cap_articles(arts, 100, _enc, _off)
    assert [a.title for a in capped.articles] == [arts[0].title, arts[1].title]
    assert capped.n_dropped == 1 and capped.n_tokens == 90
    assert not any(a.snippet_truncated for a in capped.articles)


def test_cap_truncates_the_last_snippet_only_when_one_article_is_left() -> None:
    capped = cap_articles([_art(5, 700, "a"), _art(5, 10, "b")], 600, _enc, _off)
    assert len(capped.articles) == 1 and capped.n_dropped == 1
    only = capped.articles[0]
    assert only.snippet_truncated and not only.title_truncated
    assert capped.n_tokens == 600 == len(_enc(render_block(capped.articles)))
    assert only.snippet.split()[-1] == "as594"  # the first 595 snippet words kept, in order


def test_cap_leaves_short_lists_alone() -> None:
    arts = [_art(5, 20, "a"), _art(5, 20, "b")]
    capped = cap_articles(arts, 600, _enc, _off)
    assert capped.articles == arts and capped.n_dropped == 0


def _window_articles() -> pd.DataFrame:
    s = date(2025, 8, 5)
    t = pd.Timestamp("2025-08-05 12:00", tz="UTC")
    rows = []
    for company, n_ok, n_bad in ((1, 8, 1), (2, 0, 2), (3, 2, 0)):
        for i in range(n_ok + n_bad):
            rows.append(
                {
                    "id": f"{company}-{i}",
                    "company_id": company,
                    "session": s,
                    "t_avail": t + pd.Timedelta(minutes=i),
                    "score": 1.0 - i / 100,
                    "third_party_ok": i >= n_bad,
                    "precision": "exact",
                    "source_class": "other",
                    "source_class_domain": "other",
                    "non_english_hint": False,
                    "novelty": 0.5,
                    "dup_count_w0": 1.0,
                    "dup_count_w2": 1.0,
                    "title_clean": f"title {company} {i}",
                    "snippet_clean": "word " * 10,
                }
            )
    return pd.DataFrame(rows)


def test_build_window_excludes_and_counts_non_third_party_articles() -> None:
    arts = _window_articles()
    sel = pd.DataFrame({"company_id": [1, 2, 3], "session": [date(2025, 8, 5)] * 3})
    ev, stats = build_window("W0", sel, arts, load_events_config().events, WordTokenizer())
    assert stats == {"selected": 3, "events": 2, "dropped_no_third_party": 1}
    e1 = ev.set_index("company_id").loc[1]
    assert e1["n_list_w0"] == 6 and e1["n_not_third_party_w0"] == 1 and e1["n_ok_w0"] == 8
    ids = [x["id"] for x in e1["news_w0"]]
    assert ids == [f"1-{i}" for i in range(1, 7)]  # 1-0 is not third-party OK; order by score
    assert [x["rank"] for x in e1["news_w0"]] == list(range(1, 7))
    assert int(ev.set_index("company_id").loc[3, "n_list_w0"]) == 2


# --- the built events (skip until the events stage has run) -----------------------------------------


@pytest.fixture(scope="module", params=["W0", "W2"])
def events(request: pytest.FixtureRequest) -> tuple[str, pd.DataFrame]:
    rel = "events/events_d0.parquet" if request.param == "W0" else "events/events_d2.parquet"
    if not (ROOT / "work" / rel).is_file():
        pytest.skip(f"{rel} not built")
    from newsaction import io

    return request.param, io.read_parquet(rel)


def test_real_event_constraints(events: tuple[str, pd.DataFrame]) -> None:
    window, ev = events
    sfx = window.lower()
    n = ev[f"n_list_{sfx}"]
    assert n.between(1, 6).all()
    assert (ev[f"news_tokens_{sfx}"] <= 600).all()
    assert ev["event_id"].is_unique
    assert (ev[f"news_{sfx}"].map(len) == n).all()
    assert (
        ev["event_id"]
        == [f"{window}:{c}:{d.isoformat()}" for c, d in zip(ev["company_id"], ev["session"], strict=True)]
    ).all()


def test_real_event_articles_are_third_party_ok_and_in_window(events: tuple[str, pd.DataFrame]) -> None:
    from newsaction import io

    window, ev = events
    sfx = window.lower()
    lists = ev[f"news_{sfx}"]
    ids = [x["id"] for lst in lists for x in lst]
    arts = io.read_parquet(
        "news/articles_clean.parquet", columns=["id", "third_party_ok", "keep", "company_id", "t_avail"]
    )
    arts = arts.set_index("id").loc[ids]
    assert arts["third_party_ok"].all() and arts["keep"].all()
    sample = ev.sample(200, random_state=2026)
    for r in sample.itertuples(index=False):
        w = calendar.window_w0(r.session) if window == "W0" else calendar.window_w2(r.session)
        for x in getattr(r, f"news_{sfx}"):
            assert w.contains(x["t_avail"]), (r.event_id, x["id"])
            assert int(arts.loc[x["id"], "company_id"]) == r.company_id


def test_real_token_counts_retokenize(events: tuple[str, pd.DataFrame]) -> None:
    from newsaction.events import tokens

    window, ev = events
    sfx = window.lower()
    try:
        tok = tokens.tokenizer()
    except OSError:
        pytest.skip("ModernBERT-large tokenizer not in the local cache")
    sample = ev.sample(300, random_state=7)
    for r in sample.itertuples(index=False):
        lst = getattr(r, f"news_{sfx}")
        block = render_block([ArticleText(x["title"], x["snippet"]) for x in lst])
        assert len(tok(block, add_special_tokens=False)["input_ids"]) == getattr(r, f"news_tokens_{sfx}")
    order_ok = [
        all(
            (a["score"], -pd.Timestamp(a["t_avail"]).value) >= (b["score"], -pd.Timestamp(b["t_avail"]).value)
            for a, b in itertools.pairwise(lst)
        )
        for lst in ev[f"news_{sfx}"].iloc[:5000]
    ]
    assert np.all(order_ok)


def test_render_leaves_out_empty_parts() -> None:
    assert (
        render_block([ArticleText("", "only snippet"), ArticleText("only title", "")])
        == "only snippet\n\nonly title"
    )
    assert render_block([ArticleText("t", "s")]) == "t\ns"
