"""NA-12, the price-only D2 test step (PREREG §15 post-freeze NA-11 row; operator preamble NA-12 item 4).

- the test predictions wait for the freeze and the unblinding;
- ``check`` passes only when NA-09's val-A and val-B D2 predictions are reproduced (rows and values);
- importing the step never loads LightGBM (it and torch segfault in one process, NA-09).
"""

from __future__ import annotations

import subprocess
import sys

import pandas as pd
import pytest

from newsaction.analysis import price_only_d2
from newsaction.paths import Layout


def test_the_d2_step_waits_for_the_unblinding(tmp_layout: Layout) -> None:
    with pytest.raises(price_only_d2.PriceOnlyError, match="unblinding"):
        price_only_d2.run(tmp_layout)


def test_the_check_fails_unless_na09_is_reproduced(monkeypatch: pytest.MonkeyPatch) -> None:
    pred = pd.DataFrame(
        {"event_id": ["a", "b"], "call": "B", "split": ["val_a", "val_b"], "y_hat": [0.1, -0.2]}
    )
    monkeypatch.setattr(price_only_d2, "frame_val", lambda layout=None: pd.DataFrame())
    monkeypatch.setattr(price_only_d2, "predict", lambda df, layout=None: pred)
    monkeypatch.setattr(price_only_d2.io, "read_parquet", lambda rel, layout=None: pred)
    assert price_only_d2.check()["rows"] == 2
    off = pred.assign(y_hat=[0.1, -0.2001])
    monkeypatch.setattr(price_only_d2.io, "read_parquet", lambda rel, layout=None: off)
    with pytest.raises(price_only_d2.PriceOnlyError, match="not reproduced"):
        price_only_d2.check()
    extra = pd.concat([pred, pred.assign(event_id=["c", "d"])], ignore_index=True)
    monkeypatch.setattr(price_only_d2.io, "read_parquet", lambda rel, layout=None: extra)
    with pytest.raises(price_only_d2.PriceOnlyError, match="not reproduced"):
        price_only_d2.check()


def test_importing_the_d2_step_never_loads_lightgbm() -> None:
    code = "import sys, newsaction.analysis.price_only_d2; assert 'lightgbm' not in sys.modules"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
