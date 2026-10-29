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
  points to its S5 STOP, and the exploratory appendix figures (A6, A13–A19) say "Exploratory" first;
- NA-13b's figures (A16–A19) name the chunk, say that its thresholds and medians come from val-A and that
  the test was evaluated once; A18 calls the vendor fields retrospective labels and says that no selected pair
  held on the test, A19 that its reliability diagram's confidence is not the stated confidence of its
  histograms;
- the captions are LaTeX-ready: notation in math, no raw underscore, and they render through the preview's
  text converter.
"""

from __future__ import annotations

from typing import Any

import pytest

from newsaction.figures import captions, latex, render
from newsaction.figures import keys as kz
from newsaction.paths import ROOT

NA13B_FIGURES = (
    "figA16_selective_coverage",
    "figA17_watch_open",
    "figA18_conditioning_map",
    "figA19_output_histograms",
)
EXPLORATORY_FIGURES = (
    "figA6_monthly_ic",
    "figA13_probes",
    "figA14_exploratory_d0",
    "figA15_exploratory_ma_cross",
    *NA13B_FIGURES,
)


def test_captions_match_the_tables() -> None:
    assert captions.check() == []


def test_every_figure_has_one_caption_with_a_section() -> None:
    caps = captions.load()
    assert set(caps) == set(render.MODULES)
    assert all({"section", "title", "caption"} <= set(c) for c in caps.values())


def test_rendered_captions_are_current() -> None:
    assert captions.render() == (ROOT / captions.RENDERED).read_text(encoding="utf-8")


def _one(caption: str) -> dict[str, dict[str, Any]]:
    return {"fig3_convergence": {"section": 4, "title": "t", "caption": caption}}


def _own(bad: list[str]) -> list[str]:
    return [b for b in bad if b.startswith("fig3_convergence:") and "caption" not in b.split(":", 1)[1][:12]]


def test_check_reports_a_bare_number() -> None:
    bad = _own(captions.check(captions=_one("κ is 0.36 at the close.")))
    assert bad == ["fig3_convergence: uncited number '0.36'"]
    bad = _own(captions.check(captions=_one(r"$\kappa_h$ is $0.36$ at the close.")))
    assert bad == ["fig3_convergence: uncited number '0.36'"]


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
    if name in EXPLORATORY_FIGURES:
        assert cap.startswith("Exploratory (post hoc)")
        assert str(captions.load()[name]["section"]) == "appendix"


@pytest.mark.parametrize("name", NA13B_FIGURES)
def test_na13b_captions_say_how_the_study_ran(name: str) -> None:
    entry = captions.load()[name]
    cap = " ".join(str(entry["caption"]).split())
    assert str(entry["title"]).startswith("Exploratory (post hoc)")
    assert cap.startswith("Exploratory (post hoc): NA-13b")
    assert "come from val-A" in cap or name == "figA17_watch_open"
    if name in ("figA16_selective_coverage", "figA17_watch_open"):  # the operator's earlier looks shaped them
        assert "The operator's assistant" in cap and "the test was evaluated once" not in cap
    else:
        assert "the test was evaluated once" in cap
    if name == "figA17_watch_open":
        assert "expected by chance" in cap  # the prompt's multiple-comparison caveat
    if name == "figA18_conditioning_map":
        assert "None held on the test" in cap and "{{t38_conditioning/" in cap
        assert "produced retrospectively, possibly look-ahead-contaminated" in cap
    if name == "figA19_output_histograms":
        assert "top-class probability" in cap and "not the entropy confidence of (b)" in cap


def test_results_are_captioned_as_found() -> None:
    caps = {k: " ".join(str(v["caption"]).split()) for k, v in captions.load().items()}
    assert (
        "no small-move underreaction" in caps["fig4_over_under"]
        and "never catch up" in caps["fig4_over_under"]
    )
    assert "on $|V|$" in caps["fig4_over_under"]  # the terciles, NA-12's split (a presentation deviation)
    assert "not reached within" in caps["fig3_convergence"]
    assert "every one is negative" in caps["fig6_strategies"] and "the gap fade" in caps["fig6_strategies"]
    assert "positive net" in caps["fig6_strategies"]  # owner decision 1: NA-13's result as found
    assert "released after the sample" in caps["fig7_memorisation"]
    assert "SE bands" in caps["fig3_convergence"] and "pooled over the tiers" in caps["fig4_over_under"]


def test_captions_render_as_latex() -> None:
    keys = kz.load(ROOT / "artifacts" / "NA-14" / "tables" / "keys.json")
    for name, entry in captions.load().items():
        text = latex.tex(kz.cite(" ".join(str(entry["caption"]).split()), keys))
        assert "\\_" not in text and text.count("$") % 2 == 0, name
