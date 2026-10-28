"""Option (iv)'s activity-matched distractors (production.company_id; PREREG §15 NA-06 operator row)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from newsaction.production import ProductionError
from newsaction.production.company_id import matched_distractors


def members() -> pd.DataFrame:
    rows = [
        (1, "Energy", "top100", 10),
        (2, "Energy", "top100", 20),
        (3, "Energy", "top100", 30),
        (4, "Energy", "top100", 40),
        (5, "Energy", "mid", 150),
        (6, "Energy", "mid", 160),
        (7, "Energy", "rest", 300),
        (8, "Utilities", "top100", 50),
    ]
    return pd.DataFrame(rows, columns=["company_id", "sector", "tier", "rank"])


def test_same_sector_and_tier_companies_with_news_first() -> None:
    ev = {"event_id": "W0:1:x", "company_id": 1}
    ids, how = matched_distractors(ev, members(), {1, 2, 3, 4, 5}, {}, 3, np.random.default_rng(0))
    assert how == "event_sector_tier" and sorted(ids) == [2, 3, 4]


def test_then_event_companies_by_rank_then_article_counts() -> None:
    ev = {"event_id": "W0:1:x", "company_id": 1}
    ids, how = matched_distractors(ev, members(), {1, 2, 5, 6}, {}, 3, np.random.default_rng(0))
    assert how == "event_sector_rank" and ids == [2, 5, 6]  # same tier first, then by nearest size rank
    ids, how = matched_distractors(
        ev, members(), {1}, {1: 4.0, 3: 5.0, 7: 4.0, 6: 0.0}, 3, np.random.default_rng(0)
    )
    assert how == "articles_fill" and ids[:2] in ([3, 7], [7, 3]) and 8 not in ids  # never another sector


def test_too_few_members_is_an_error() -> None:
    ev = {"event_id": "W0:8:x", "company_id": 8}
    with pytest.raises(ProductionError, match="fewer than 3"):
        matched_distractors(ev, members(), {8}, {}, 3, np.random.default_rng(0))
