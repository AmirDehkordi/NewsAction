"""Figure 3: the decision-model tournament and the final instruments (NA-06; NA-12 t14).

    uv run python -m newsaction.figures.fig3_tournament

(a) The zero-shot tournament on NA-06's val-A stage-1 sample: daily IC of Call A's N̂ with z_cc (95% bootstrap
CI) against the cost per 1,000 decisions (log scale; the local models cost $0 and sit in their own strip).
Squares ran the stage-2 contamination screens (§8.3) and failed them; every model is in the model confidence
set. The three API comparators carried to production are in orange. (b) Val-B (hollow) and test (filled) ICs
of the final instruments and baselines on their D0 events, with 95% intervals from the Newey–West t, and the
cost per 1,000 decisions.
"""

from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

from newsaction.figures import render, style

NAME = "fig3_tournament"
COMPARATORS = {"liquid/d1-ultra": "d1-ultra", "respan/span-02": "span-02‡", "nace-ai/drex-v2.0": "drex-v2.0"}
LOCAL = {"local/laya-typed-decisions": ("typed", -9), "local/laya-base": ("base", 4)}
LABELLED = {"inception/mercury-decide": "mercury-decide"}
ROWS = {
    "laya_fin": "Laya-Fin (primary)",
    "anchor": "anchor, uninformative\n(near-constant outputs)",
    "laya_zs": "Laya zero-shot",
    "d1_ultra": "d1-ultra",
    "span_02": "span-02‡",
    "drex_v2": "drex-v2.0",
    "price_only": "price-only",
    "embed_ridge": "bge-ridge",
    "llm": "LLM baseline",
    "sentiment": "vendor sentiment†",
    "tags_gbm": "tags-GBM†",
}
ROW_COLOR = {
    "laya_fin": "laya_fin",
    "d1_ultra": "api",
    "span_02": "api",
    "drex_v2": "api",
    "price_only": "price_only",
    "sentiment": "vendor",
    "tags_gbm": "vendor",
}


def _usd(x: float, _: object = None) -> str:
    return f"${x:.2f}" if x >= 0.1 else f"${x:.3f}".rstrip("0")


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_DOUBLE, 3.6, [["z", "a", "b"]], width_ratios=[0.55, 2.4, 3.0])
    z, a, b = axd["z"], axd["a"], axd["b"]
    t = df[df["panel"] == "a"]
    ic = t[t["role"] == "ic"].set_index("series")
    stage2 = t[t["role"] == "stage2"].set_index("series")["y"] > 0.5
    for model, r in ic.iterrows():
        local = r["x"] == "local"
        ax = z if local else a
        x = (0.0 if model == "local/laya-base" else 0.5) if local else float(r["xv"])
        color = style.COLOR["api"] if model in COMPARATORS else style.MUTED
        style.dots(
            ax,
            [x],
            [r["y"]],
            [r["lo"]],
            [r["hi"]],
            color=color,
            size=5.5,
            marker="s" if bool(stage2.get(model, False)) else "o",
            zorder=4 if model in COMPARATORS else 3,
        )
        if str(model) in LOCAL:
            text, dy = LOCAL[str(model)]
            ann = ax.annotate(
                text,
                (x, float(r["y"])),
                xytext=(0, dy),
                textcoords="offset points",
                ha="center",
                va="bottom" if dy > 0 else "top",
                fontsize=style.SIZE_NOTE,
                color=style.INK_2,
            )
            ann.set_in_layout(False)
        elif str(model) in LABELLED:
            ann = ax.annotate(
                LABELLED[str(model)],
                (x, float(r["y"])),
                xytext=(5, 3),
                textcoords="offset points",
                va="bottom",
                fontsize=style.SIZE_NOTE,
                color=style.INK_2,
            )
            ann.set_in_layout(False)
    a.set_xscale("log")
    a.xaxis.set_major_locator(FixedLocator([0.02, 0.05, 0.1, 0.2]))
    a.xaxis.set_minor_locator(NullLocator())
    a.xaxis.set_major_formatter(FuncFormatter(_usd))
    a.set_xlim(0.016, 0.26)
    a.set_xlabel("cost per 1,000 decisions (USD, log scale)")
    z.set_xlim(-0.4, 1.9)
    z.set_xticks([0.25], ["$0\n(local\nLaya)"])
    z.grid(axis="x", visible=False)
    lo = min(z.get_ylim()[0], a.get_ylim()[0])
    hi = max(z.get_ylim()[1], a.get_ylim()[1])
    for ax in (z, a):
        ax.set_ylim(lo, hi)
        style.zero_line(ax)
    a.tick_params(labelleft=False)
    z.set_ylabel("daily IC of N̂ with z_cc (val-A)")
    style.title(z, "a", "")
    a.set_title("Zero-shot tournament (NA-06, 95% CI)", color=style.INK)
    handles = [
        Line2D(
            [],
            [],
            color=style.MUTED,
            marker="s",
            linestyle="none",
            markersize=5,
            markeredgecolor=style.SURFACE,
            label="stage-2 screens run: all failed",
        ),
        Line2D(
            [],
            [],
            color=style.MUTED,
            marker="o",
            linestyle="none",
            markersize=5,
            markeredgecolor=style.SURFACE,
            label="stage 1 only",
        ),
        Line2D(
            [],
            [],
            color=style.COLOR["api"],
            marker="s",
            linestyle="none",
            markersize=5,
            markeredgecolor=style.SURFACE,
            label="carried to production:\nd1-ultra, span-02‡, drex-v2.0",
        ),
    ]
    a.legend(handles=handles, loc="lower right", handletextpad=0.3)
    style.note(a, 0.02, 0.97, "all models are in the model confidence set", ha="left", va="top")

    p = df[df["panel"] == "b"]
    order = list(ROWS)
    for i, key in enumerate(order):
        color = style.COLOR.get(ROW_COLOR.get(key, "other"), style.MUTED)
        if ROW_COLOR.get(key) is None:
            color = style.MUTED
        y0 = len(order) - 1 - i
        for split, off, hollow in (("val_b", 0.17, True), ("test", -0.17, False)):
            row = p[(p["series"] == key) & (p["role"] == split)]
            style.dots(
                b,
                row["y"],
                [y0 + off],
                row["lo"],
                row["hi"],
                color=color,
                hollow=hollow,
                size=5,
                horizontal=True,
            )
        c = p[(p["series"] == key) & (p["role"] == "cost")]
        if len(c):
            b.text(
                1.02,
                y0,
                _usd(float(c["y"].iloc[0])) if float(c["y"].iloc[0]) > 0 else "$0",
                transform=b.get_yaxis_transform(),
                va="center",
                ha="left",
                fontsize=style.SIZE_NOTE,
                color=style.INK_2,
            )
    b.text(
        1.02,
        len(order) - 0.45,
        "cost /\n1,000",
        transform=b.get_yaxis_transform(),
        va="bottom",
        ha="left",
        fontsize=style.SIZE_NOTE,
        color=style.INK_2,
    )
    b.set_yticks(range(len(order)), [ROWS[k] for k in reversed(order)])
    b.set_ylim(-0.6, len(order) + 0.5)
    b.grid(axis="y", visible=False)
    style.zero_line(b, horizontal=False)
    b.set_xlabel("daily IC of N̂ with z_cc (95% CI)")
    style.title(b, "b", "Final instruments: val-B → test")
    handles = [
        Line2D(
            [],
            [],
            color=style.INK_2,
            marker="o",
            linestyle="none",
            markersize=5,
            markerfacecolor=style.SURFACE,
            label="val-B",
        ),
        Line2D(
            [],
            [],
            color=style.INK_2,
            marker="o",
            linestyle="none",
            markersize=5,
            markeredgecolor=style.SURFACE,
            label="test",
        ),
    ]
    b.legend(handles=handles, loc="upper right", ncols=2, handletextpad=0.3, columnspacing=0.8)
    notes = [
        Line2D([], [], linestyle="none", label=f"{style.DAGGER} vendor-label baseline: {style.VENDOR_NOTE}"),
        Line2D(
            [],
            [],
            linestyle="none",
            label=f"{style.DDAGGER} span-02: S5 canary STOP after the freeze; "
            "the operator proceeded (PREREG §15)",
        ),
    ]
    fig.legend(handles=notes, loc="outside lower center", ncols=1, handlelength=0, handletextpad=0)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
