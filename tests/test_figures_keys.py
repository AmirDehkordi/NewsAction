"""NA-14 S4: cell formatting, citations and the uncited-number check (``figures.keys``).

- ``fmt`` equals NA-12's ``analysis.tables.fmt`` (NA-14 repeats it so ``make paper`` never imports the lock);
- the display specs, ``cite`` with literals, and an unknown key or spec;
- ``bare_digits`` finds numbers and ignores names that hold digits.
"""

from __future__ import annotations

import math

import pytest

from newsaction.analysis import tables as na12
from newsaction.figures import keys as kz

VALUES = (
    0.0004,
    0.04567,
    12.0,
    12.5,
    math.inf,
    -math.inf,
    math.nan,
    True,
    False,
    0.00012,
    -0.0441,
    1500,
    0.0,
    "x",
)
COLUMNS = ("b_p", "q", "nobs", "n", "kappa", "lambda", "estimate", "in_family", "p_holm", "x", "n_days")


@pytest.mark.parametrize("column", COLUMNS)
def test_fmt_equals_na12(column: str) -> None:
    for v in VALUES:
        assert kz.fmt(v, column) == na12.fmt(v, column), (v, column)


def test_specs() -> None:
    assert kz.spec_format(0.9221, "pct0") == "92%" and kz.spec_format(0.9979, "pct1") == "99.8%"
    assert kz.spec_format(0.00252, "pct2") == "0.25%"
    assert kz.spec_format(-1.98, "signed2") == "−1.98" and kz.spec_format(0.61, "signed2") == "+0.61"
    assert kz.spec_format(545.0, "int") == "545" and kz.spec_format(15858, "int") == "15,858"
    assert kz.spec_format(-0.0017481, "f4") == "−0.0017" and kz.spec_format(-0.04, "abs2") == "0.04"
    assert kz.spec_format("inf", "f2") == "∞"
    with pytest.raises(ValueError):
        kz.spec_format(1.5, "int")
    with pytest.raises(ValueError):
        kz.spec_format(1.5, "f9")
    with pytest.raises(TypeError):
        kz.spec_format("not supported", "f2")


def test_cite_renders_values_and_literals() -> None:
    keys = {"t/k|1/c": 0.1234, "t/k|1/verdict": "not supported", "t/k|1/p": 0.0004}
    text = "κ {{t/k|1/c@f2}}, {{t/k|1/verdict}} (p {{t/k|1/p}}) at [[t+20]]"
    assert kz.cite(text, keys) == "κ 0.12, not supported (p <0.001) at t+20"
    assert kz.refs(text) == ["t/k|1/c@f2", "t/k|1/verdict", "t/k|1/p"]
    with pytest.raises(KeyError):
        kz.cite("{{t/k|2/c}}", keys)


def test_bare_digits() -> None:
    text = (
        "κ is 0.36 and 12 events, 93% of days, d1-ultra and NA-12 (§8.3; D0, H1b, y2, F5, 95%) at t+20, 10:00"
    )
    assert kz.bare_digits(text) == ["0.36", "12", "93%"]
    assert kz.bare_digits("{{a/b/c}} and [[0.5]] and S-D0, Top-100, e5, R², MA20/MA50") == []
    math = r"$y_2$, $t{+}20$, $C_{t-1}$, $R^2$, $z_{cc}$, $|G| \geq [[3]]$, $\kappa_h = [[1]]$"
    assert kz.bare_digits(math) == []
    assert kz.bare_digits(r"$\kappa_h = 1$ and $\pm 1.96$") == ["1", "1.96"]
