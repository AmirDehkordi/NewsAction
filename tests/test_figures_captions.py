"""NA-14 AC2: every number in a caption is a table cell (PRD NA-14 S4, AC2; ``figures.captions``).

- ``check`` passes on the committed captions: every cited key exists, equals its CSV cell (and, for a copy
  of an
  NA-12 table, the NA-12 cell), and no digit sits outside a citation, a literal or a name;
- the check is not vacuous: a bare number, an unknown key and a keys.json value that differs from the table
  are
  each reported;
- ``captions.md`` is the current rendering;
- the operator's labels follow the data: a figure that plots the anchor says "near-constant outputs", one that
  plots a vendor-label baseline says "possibly look-ahead-contaminated upper bound", one that plots span-02
  points
  to its S5 STOP, and the exploratory figures say "Exploratory (post hoc)".
"""

from __future__ import annotations

from typing import Any

import pytest

from newsaction.figures import captions, render
from newsaction.figures import keys as kz
from newsaction.paths import ROOT


def test_captions_match_the_tables() -> None:
    assert captions.check() == []


def test_every_figure_has_one_caption_with_a_section() -> None:
    caps = captions.load()
    assert set(caps) == set(render.MODULES)
    assert all({"section", "title", "caption"} <= set(c) for c in caps.values())


def test_rendered_captions_are_current() -> None:
    assert captions.render() == (ROOT / captions.RENDERED).read_text(encoding="utf-8")


def _one(caption: str) -> dict[str, dict[str, Any]]:
    return {"fig1_convergence": {"section": 4, "title": "t", "caption": caption}}


def _own(bad: list[str]) -> list[str]:
    return [b for b in bad if b.startswith("fig1_convergence:") and "caption" not in b.split(":", 1)[1][:12]]


def test_check_reports_a_bare_number() -> None:
    bad = _own(captions.check(captions=_one("κ is 0.36 at the close.")))
    assert bad == ["fig1_convergence: uncited number '0.36'"]


def test_check_reports_an_unknown_key() -> None:
    bad = _own(captions.check(captions=_one("κ is {{t6_convergence_ladder/nope:ladder:C_t/kappa@f2}}.")))
    assert len(bad) == 1 and "unknown key" in bad[0]


def test_check_reports_a_value_that_differs_from_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    real = kz.load

    def load(path: Any) -> dict[str, Any]:
        out = real(path)
        if str(path).endswith("keys.json"):
            out = dict(out)
            out["t6_convergence_ladder/laya_fin:ladder:C_t/kappa"] = 0.99
        return out

    monkeypatch.setattr(kz, "load", load)
    bad = _own(captions.check(captions=_one("κ is {{t6_convergence_ladder/laya_fin:ladder:C_t/kappa@f2}}.")))
    assert len(bad) == 1 and "in keys.json but" in bad[0]


def _plots(name: str, needles: tuple[str, ...]) -> bool:
    df = render.read(name)
    text = (
        " ".join(df["series"].astype(str))
        + " "
        + " ".join(df["label"].astype(str))
        + " "
        + " ".join(df["key"])
    )
    return any(n in text for n in needles)


@pytest.mark.parametrize("name", list(render.MODULES))
def test_labels_follow_the_data(name: str) -> None:
    cap = " ".join(str(captions.load()[name]["caption"]).split())
    if _plots(name, ("anchor",)):
        assert "near-constant outputs" in cap
    if _plots(name, ("sentiment", "tags_gbm")):
        assert "possibly look-ahead-contaminated upper bound" in cap
    if _plots(name, ("span_02", "span-02")):
        assert "S5" in cap
    if name.startswith("figA6") or name.startswith("figA7"):
        assert cap.startswith("Exploratory (post hoc)")


def test_results_are_captioned_as_found() -> None:
    caps = {k: " ".join(str(v["caption"]).split()) for k, v in captions.load().items()}
    assert "no small-move underreaction" in caps["fig2_drift_vs_move"]
    assert "not reached within" in caps["fig1_convergence"] and "never catch" in caps["fig1_convergence"]
    assert "negative net" in caps["fig7_strategies"] and "gap fade" in caps["fig7_strategies"]
    assert "after the sample" in caps["fig4_monthly_ic"]
    assert "Exploratory (post hoc)" in caps["figA3_identifiability"]
