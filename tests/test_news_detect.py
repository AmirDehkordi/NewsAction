"""PRD NA-02 AC3: after-the-fact / pre-market detectors on the planted set; scrub (PREREG §6.3–6.4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from newsaction.news import detect

PLANTED = Path(__file__).parent / "data" / "detector_planted.csv"


@pytest.fixture(scope="module")
def planted() -> pd.DataFrame:
    df = pd.read_csv(PLANTED)
    det = detect.load_detector()
    flags = [det.flags(s) for s in df["sentence"]]
    df["got_af"] = [int(f.after_fact) for f in flags]
    df["got_pm"] = [int(f.premarket) for f in flags]
    return df


def test_planted_set_size(planted: pd.DataFrame) -> None:
    assert len(planted) >= 60
    assert planted["id"].is_unique
    assert (planted["after_fact"] == 1).sum() >= 30 and (planted["premarket"] == 1).sum() >= 10
    assert ((planted["after_fact"] == 0) & (planted["premarket"] == 0)).sum() >= 30


@pytest.mark.parametrize("flag", ["after_fact", "premarket"])
def test_planted_recall(planted: pd.DataFrame, flag: str) -> None:
    got = "got_af" if flag == "after_fact" else "got_pm"
    pos = planted[planted[flag] == 1]
    assert pos[got].mean() >= 0.95, pos.loc[pos[got] == 0, "sentence"].tolist()


def test_planted_hard_negatives(planted: pd.DataFrame) -> None:
    neg = planted[(planted["after_fact"] == 0) & (planted["premarket"] == 0)]
    fp = neg[(neg["got_af"] == 1) | (neg["got_pm"] == 1)]
    assert fp.empty, fp["sentence"].tolist()


def test_split_sentences_keeps_abbreviations() -> None:
    text = (
        'Acme Inc. said U.S. sales rose. Shares fell 3% in early trading. "It was good." Next; more • bullet'
    )
    assert detect.split_sentences(text) == [
        "Acme Inc. said U.S. sales rose.",
        "Shares fell 3% in early trading.",
        '"It was good."',
        "Next",
        "more",
        "bullet",
    ]
    assert detect.split_sentences("EPS of $1.23 beat. Revenue was $4.5 billion.") == [
        "EPS of $1.23 beat.",
        "Revenue was $4.5 billion.",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Acme raised guidance. Shares jumped 8% in early trading.", "Acme raised guidance."),
        ("Price target raised to $200; shares hit $150 a share.", "Price target raised to $200"),
        ("Analysts expect earnings of $1.23 a share.", "Analysts expect earnings of $1.23 a share."),
        (
            "Acme agreed to acquire Beta for $45 per share in cash.",
            "Acme agreed to acquire Beta for $45 per share in cash.",
        ),
        ("The fund bought shares at $45.10 a share last quarter.", "The fund bought shares at last quarter."),
        ("The 52-week high of $412.50 was set in March.", "The 52-week high was set in March."),
        ("Shares rose 3% in premarket trading. The company beat estimates.", "The company beat estimates."),
    ],
)
def test_scrub(text: str, expected: str) -> None:
    assert detect.scrub(text) == expected


def test_scrub_can_keep_premarket_talk_for_call_b() -> None:
    text = "Futures pointed to a higher open before the bell. The company beat estimates."
    assert detect.scrub(text) == "The company beat estimates."
    assert detect.scrub(text, keep_premarket=True) == text


def test_detect_articles_combines_title_and_snippet() -> None:
    out = detect.detect_articles(
        ["Nvidia jumps 6% after earnings", "Acme names new CFO", None],
        ["Revenue rose 20%.", "Shares were indicated 2% higher before the bell.", "Acme closed up 1%."],
        processes=1,
    )
    assert out["after_fact"].tolist() == [True, True, True]
    assert out["premarket_talk"].tolist() == [False, True, False]
    assert out["title_clean"].tolist() == ["", "Acme names new CFO", ""]
    assert out["snippet_clean"].tolist() == ["Revenue rose 20%.", "", ""]


def test_parallel_equals_serial() -> None:
    titles = ["Nvidia jumps 6% after earnings", "Acme names new CFO", "Stocks rallied in late trading"] * 9000
    snippets = ["Revenue rose 20%.", "The company beat estimates.", "As of 10:30, shares were up"] * 9000
    serial = detect.detect_articles(titles[:300], snippets[:300], processes=1)
    parallel = detect.detect_articles(titles, snippets, processes=2)
    pd.testing.assert_frame_equal(parallel.head(300), serial)


def test_non_english_hint() -> None:
    hint = detect.non_english_hint(
        [
            "Kaum Impulse für die Altria Group-Aktie",
            "Acme raises guidance",
            "Bumble可能縮小價值差距",
        ],
        ["", "Earnings per share rose per the filing, per analysts.", ""],
    )
    assert hint.tolist() == [True, False, True]
    assert not detect.non_english_hint(
        ["Zacks Research Expects Weaker Earnings for Las Vegas Sands"], [""]
    ).iloc[0]
