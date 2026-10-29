"""Figure 8: explaining the move, firm-level Kelly–Su–Zhang (PREREG A3; NA-12 t10, t11).

    uv run python -m newsaction.figures.fig8_explain_move

(a) d1-ultra's out-of-sample R² of the stock-specific daily move z_cc on the test period, stacked by step:
ex-ante news (D0), + ex-post news (W2, Call A), + the explanation (Call B, which sees the move), by cut; the
bar's whisker is the final step's 95% bootstrap CI. (b) The news-only steps for the three instruments
(×10⁻³; hollow ex-ante, filled ex-post; 95% bootstrap CI). (c) Persistence by the model's move_reason: mean
sign(G)·y2 with its 95% CI, and θ, the D2 regression of persistence on being explained (±1.96 SE).
"""

from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from newsaction.figures import render, style

NAME = "fig8_explain_move"
STEPS = (
    ("ex_ante", style.INK, "ex-ante news (D0)"),
    ("ex_post", style.INK_2, "+ ex-post news (W2)"),
    ("explanation", style.BASELINE, "+ explanation (Call B sees the move)"),
)
CUTS = {
    "all": "all days",
    "event_days": "event\ndays",
    "tier:top100": "Top-\n100",
    "tier:mid": "101–\n250",
    "tier:rest": "251–\n500",
}
MODELS = ("laya_fin", "d1_ultra", "anchor")
DODGE = {"laya_fin": -0.22, "d1_ultra": 0.0, "anchor": 0.22}
REASONS = {
    "analyst_action": "analyst action",
    "capital_returns_financing": "capital returns / financing",
    "deal_ma_partnership": "deal / M&A / partnership",
    "earnings_results": "earnings / results",
    "guidance_outlook": "guidance / outlook",
    "legal_regulatory": "legal / regulatory",
    "management_governance": "management / governance",
    "market_or_sector_move": "market or sector move",
    "no_identifiable_news": "no identifiable news",
    "product_operations": "product / operations",
    "sector_or_macro": "sector or macro",
}


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_DOUBLE, 5.6, [["a", "b"], ["c", "c"]], height_ratios=[1.2, 1.0])
    a, b, c = axd["a"], axd["b"], axd["c"]
    seg = df[(df["panel"] == "a") & (df["role"] == "segment")]
    cum = df[(df["panel"] == "a") & (df["role"] == "cumulative")]
    base = None
    for step, color, _ in STEPS:
        m = seg[seg["series"] == step].sort_values("xv")
        bottom = base.reindex(m["xv"].to_numpy()).fillna(0.0).to_numpy() if base is not None else 0.0
        a.bar(
            m["xv"],
            m["y"],
            bottom=bottom,
            width=0.55,
            color=color,
            edgecolor=style.SURFACE,
            linewidth=0.8,
            zorder=2,
        )
        top = pd.Series(m["y"].to_numpy() + bottom, index=m["xv"].to_numpy())
        base = top
    fin = cum[cum["series"] == "explanation"].sort_values("xv")
    a.vlines(fin["xv"], fin["lo"], fin["hi"], color=style.INK, linewidth=style.LINE_THIN, zorder=3)
    for x, y in zip(fin["xv"], fin["hi"], strict=True):
        v = float(fin.loc[fin["xv"] == x, "y"].iloc[0])
        a.text(
            float(x),
            float(y) + 0.008,
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=style.SIZE_NOTE,
            color=style.INK_2,
        )
    ticks = fin.drop_duplicates("xv").sort_values("xv")
    a.set_xticks(ticks["xv"].to_numpy(), [CUTS[x] for x in ticks["x"]])
    a.grid(axis="x", visible=False)
    a.set_ylabel("OOS R² of z_cc (test)")
    roll = df[(df["panel"] == "a") & (df["role"] == "roll")]
    style.note(
        a,
        0.98,
        0.585,
        f"step 1, market + sector (Roll):\nR² {float(roll['y'].iloc[0]):.2f} of the total daily variance",
        ha="right",
        va="top",
    )
    a.set_ylim(0, float(fin["hi"].max()) * 1.45)
    style.title(a, "a", "d1-ultra, by step")
    a.legend(
        handles=[Patch(color=col, linewidth=0, label=lab) for _, col, lab in STEPS][::-1],
        loc="upper right",
        handlelength=1.2,
    )

    n = df[df["panel"] == "b"]
    for model in MODELS:
        for step, hollow in (("ex_ante", True), ("ex_post", False)):
            m = n[(n["series"] == model) & (n["label"] == step)].sort_values("xv")
            style.dots(
                b,
                m["xv"] + DODGE[model] + (-0.05 if hollow else 0.05),
                m["y"] * 1e3,
                m["lo"] * 1e3,
                m["hi"] * 1e3,
                color=style.COLOR[model],
                hollow=hollow,
                size=4.5,
            )
    style.zero_line(b)
    b.set_ylim(top=float(n["hi"].max()) * 1e3 * 1.5)
    ticks = n.drop_duplicates("xv").sort_values("xv")
    b.set_xticks(ticks["xv"].to_numpy(), [CUTS[x].replace("\n", "") for x in ticks["x"]])
    b.grid(axis="x", visible=False)
    b.set_ylabel("OOS R² of z_cc (×10⁻³)")
    style.title(b, "b", "News only (95% CI)")
    b.legend(
        handles=[
            Line2D(
                [],
                [],
                color=style.COLOR["laya_fin"],
                marker="o",
                linestyle="none",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                label="Laya-Fin",
            ),
            Line2D(
                [],
                [],
                color=style.COLOR["d1_ultra"],
                marker="o",
                linestyle="none",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                label="d1-ultra",
            ),
            Line2D(
                [],
                [],
                color=style.COLOR["anchor"],
                marker="o",
                linestyle="none",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                label=f"anchor, {style.ANCHOR_NOTE}",
            ),
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4.5,
                markerfacecolor=style.SURFACE,
                label="hollow: ex-ante; filled: ex-post",
            ),
        ],
        loc="upper left",
        handletextpad=0.3,
    )

    p = df[(df["panel"] == "c") & (df["role"] == "persistence")].sort_values("y")
    y = list(range(len(p)))
    style.dots(c, p["y"], y, p["lo"], p["hi"], color=style.COLOR["d1_ultra"], size=4.5, horizontal=True)
    th = df[(df["panel"] == "c") & (df["role"] == "theta")]
    yt = len(p) + 0.8
    style.dots(c, th["y"], [yt], th["lo"], th["hi"], color=style.INK, size=4.5, marker="D", horizontal=True)
    c.axhline(len(p) + 0.1, color=style.GRID, linewidth=0.6)
    c.set_yticks([*y, yt], [*[REASONS[r] for r in p["x"]], "θ at D2 (explained → persists)"])
    c.set_ylim(-0.7, yt + 0.7)
    c.grid(axis="y", visible=False)
    style.zero_line(c, horizontal=False)
    c.set_xlabel("persistence after D2: mean sign(G)·y2 by the model's move_reason (95% CI); θ: ±1.96 SE")
    style.title(c, "c", "d1-ultra: explained moves do not persist more")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
