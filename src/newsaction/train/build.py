"""NA-08 build: ``uv run python -m newsaction.train.build --stage <stage>``.

Stages, one process each, in this order (schemas in docs/DATA_CONTRACT.md):
1. ``labels``: work/kaggle/labels.parquet (S1; public panel, purged);
2. ``export``: work/kaggle/dataset/ (S2; the private Kaggle dataset and its sha256 manifest);
3. ``notebook``: src/newsaction/train/notebook/newsaction_laya_fin.ipynb from its parts (S3);
4. ``kernels``: work/kaggle/kernels/<run>/ (S6; one private GPU kernel per planned run);
   the operator then uploads and runs them on Kaggle (artifacts/NA-08/REPORT.md, runbook);
5. ``plan``: artifacts/NA-08/throughput.json from the downloaded pilot (S4);
6. ``import``: work/kaggle/predictions/ from the downloaded runs (S7);
7. ``cards``: artifacts/NA-08/{controls.json, model_card_laya_fin.md, model_card_anchor.md} (S5, S8).
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

STAGES: Final = ("labels", "export", "notebook", "kernels", "plan", "import", "cards")


def _stage(name: str) -> Callable[[Layout | None], Any]:
    if name == "labels":
        from newsaction.train.labels import run

        return run
    if name == "export":
        from newsaction.train.kaggle_export import run as run_export

        return run_export
    if name == "notebook":
        from newsaction.train.nbbuild import write_notebook

        return lambda _layout: str(write_notebook())
    if name == "kernels":
        from newsaction.train.kaggle_export import write_kernels

        return write_kernels
    if name == "plan":
        from newsaction.train.plan import run as run_plan

        return run_plan
    if name == "import":
        from newsaction.train.import_preds import run as run_import

        return run_import
    from newsaction.train.cards import run as run_cards

    return run_cards


def _summary(result: Any) -> str:
    if isinstance(result, dict):
        try:
            return json.dumps(result, default=str)[:4000]
        except TypeError:
            return str(list(result))
    if isinstance(result, str):
        return result
    return f"{type(result).__name__} with {len(result) if hasattr(result, '__len__') else '?'} rows"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="newsaction.train.build", description=__doc__)
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
