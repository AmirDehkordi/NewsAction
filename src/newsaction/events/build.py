"""NA-03 build: ``uv run python -m newsaction.events.build --stage <stage>``.

Stages, run one process at a time and in this order (each reads the registered files of the previous
ones; schemas in docs/DATA_CONTRACT.md):
1. ``labels``: work/events/labels_public.parquet (S1; public panel, sessions ≤ end of val-B);
2. ``counts``: work/events/window_counts.parquet (articles only);
3. ``fit``: F5 / F6 fit on the fit window, tuned on the tune window, frozen (S3; trials logged);
4. ``scores``: work/events/article_scores.parquet and ticker_days.parquet (S2; articles + frozen models);
5. ``compare``: val-A comparison, frontier, rule → artifacts/NA-03/*.csv and configs/frozen.yaml (S4);
6. ``events``: work/events/events_d0.parquet and events_d2.parquet for every period (S5; no outcome read);
7. ``project``: artifacts/NA-03/call_projection.csv (S6).
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from collections.abc import Callable
from typing import Any, Final

from newsaction.paths import Layout

STAGES: Final = ("labels", "counts", "fit", "scores", "compare", "events", "project")


def _stage(name: str) -> Callable[[Layout | None], Any]:
    if name == "labels":
        from newsaction.events.labels import run

        return run
    if name == "counts":
        from newsaction.events.attention import run as run_counts

        return run_counts
    if name == "fit":
        from newsaction.events.learned import run_fit

        return run_fit
    if name == "scores":
        from newsaction.events.scores import run_scores

        return run_scores
    if name == "compare":
        from newsaction.events.select import run_compare

        return run_compare
    if name == "events":
        from newsaction.events.aggregate import run_events

        return run_events
    from newsaction.events.projection import run_projection

    return run_projection


def _summary(result: Any) -> str:
    if isinstance(result, dict):
        try:
            return json.dumps(result, default=str)[:4000]
        except TypeError:
            return str(list(result))
    return f"{type(result).__name__} with {len(result) if hasattr(result, '__len__') else '?'} rows"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="newsaction.events.build", description=__doc__)
    ap.add_argument("--stage", choices=STAGES, required=True)
    args = ap.parse_args(argv)
    t0 = time.time()
    result = _stage(args.stage)(None)
    rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS
    print(f"stage {args.stage}: {time.time() - t0:,.0f}s, peak RSS {rss_gb:.1f} GB", flush=True)
    print(_summary(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
