# Replication

NA-14 (2026-10-29). How to rebuild the paper's figures, tables and captions, what the rebuild needs, and what it
must reproduce. The analyses themselves were run once, chunk by chunk (NA-00 … NA-13), and their outputs are
committed under `artifacts/`; each chunk's `artifacts/NA-xx/REPORT.md` gives its own commands.

## Environment

- macOS 26.5 on arm64 (Apple M-series), Python 3.12.13, the project's locked `uv` environment (`uv.lock`):
  matplotlib 3.11.2, pandas 3.1.0, NumPy 2.5.4.
- Install with `uv sync --locked --all-extras`. Do not run `make sync`: it is an exact sync and removes the
  optional extras (`embed`, `laya`, `kaggle`) that earlier chunks use. `make paper` itself needs only the core
  dependencies.
- Fonts: DejaVu Sans, which ships with matplotlib, so the figures do not depend on the system's fonts. The PDF
  and PNG bytes still depend on the matplotlib and FreeType builds; the plotted numbers are the CSVs.
- LaTeX (optional): `artifacts/NA-14/tables/paper_tables.tex` compiles every table (NA-14 checked it with
  `tectonic`, which fetches its TeX bundle over the network). It is not part of `make paper`.

## What `make paper` needs

All of it is committed except the two NA-13 work files.

| Input | Where | Committed |
|---|---|---|
| NA-03, NA-06, NA-07, NA-11, NA-12, NA-13 outputs | `artifacts/NA-xx/` (figure data, tables, results JSON) | yes |
| NA-05 model catalog (release dates) | `artifacts/NA-05/catalog.json` | yes |
| NA-08 and NA-11 REPORTs (Kaggle GPU-hours) | `artifacts/NA-08/REPORT.md`, `artifacts/NA-11/REPORT.md` | yes |
| The operator's input (Laya's release date) | `artifacts/NA-14/inputs/operator.yaml` | yes |
| The caption templates | `artifacts/NA-14/captions.yaml` | yes |
| The test split's end, the budget caps | `configs/splits.yaml`, `configs/project.yaml` | yes |
| The ledgers (spend, FMP requests, trials, test access) | `ledgers/*.jsonl` (read only) | yes |
| NA-13's stored test positions and daily books | `work/strategy/positions_test.parquet`, `work/strategy/books_test.parquet`, registered in `work/MANIFEST.json` | no (gitignored) |

The two work files feed one table only, t26 (the S-CONV / gap-fade overlap that NA-13's REPORT §4 states but no
committed file holds). Without them, rebuild NA-13 first (its REPORT §12 lists the commands; the test-period
returns come through one `newsaction.lock` read after unblinding, as NA-13 did once).

`make paper` reads nothing else: no raw data (`Data/`), no ATOM snapshot, no decision-model cache, no API, no
Kaggle, no FMP. It never imports the decision-model client, `newsaction.lock`, `panel.targets` or
`panel.reactions`, and it fails if it does (`tests/test_figures_paper.py`).

## Commands

```bash
uv sync --locked --all-extras                       # the locked environment, extras kept
make verify                                         # lint, types, tests, manifest, ledger chains
make paper                                          # rebuild tables, figure CSVs, figures and captions; check digests
uv run --locked python -m newsaction.figures.captions   # re-check every caption number against its table
uv run --locked python -m newsaction.figures.render fig1_convergence   # one figure from its CSV
```

`make paper` (`newsaction.figures.paper`) runs in about 7 seconds and 0.3 GB:

1. checks the sha256 of each of its 33 inputs against `artifacts/NA-14/digests.json` and stops if one differs;
2. writes the tables (`artifacts/NA-14/tables`: CSV, LaTeX, `keys.json`, `index.json`), the 15 figure CSVs, the
   15 figures (PDF and 300-dpi PNG) and `captions.md`, after checking that every number in a caption equals its
   table cell;
3. compares the sha256 of its 87 text outputs (CSV, LaTeX, JSON, Markdown) with the committed digests and fails on
   any difference; the 30 PDF and PNG digests are compared and reported, not enforced;
4. fails if any `ledgers/*.jsonl` changed during the run.

The author's steps after a deliberate change: `python -m newsaction.figures.paper --write-digests`, then
`python -m newsaction.figures.contract` (registers every NA-14 file in `work/MANIFEST.json` and rewrites the
NA-14 section of `docs/DATA_CONTRACT.md`).

## How every number traces

- Each figure reads only its CSV (`render.read`; the figure modules read no file). A figure CSV holds one row per
  plotted value and names its upstream file, row key and column; `tests/test_figures_trace.py` re-reads every one
  of those cells. Intervals are the stored bootstrap bounds, or ±1.96 × a stored standard error, or ±1.96 × |value
  / t| from a stored t statistic.
- Each caption number is `{{table/key/column}}` from `artifacts/NA-14/tables/keys.json`;
  `tests/test_figures_captions.py` checks it against the table cell, and for a copied NA-12 table against NA-12's
  CSV. NA-12's tables are copied byte for byte; NA-13's strategy table and the NA-03, NA-06, NA-07 and NA-11 figure
  sources gain only a row key.

## Expected digests

The full list (inputs, outputs, figures) is `artifacts/NA-14/digests.json`. The figure CSVs:

| File | sha256 |
|---|---|
| `fig1_convergence.csv` | `079d16cc523bcf75f22703fbd18efe8d764f3b3173e4f000f3913f5955467bb4` |
| `fig2_drift_vs_move.csv` | `348440b1c041d0f5355bb703c556cdf8f81dfb5c0ce22582fb96592311f78fd7` |
| `fig3_tournament.csv` | `c6788dfe97cba9c440f209620c1d2ccd8e3727bd14bdc431935ca23a57eebd4f` |
| `fig4_monthly_ic.csv` | `d7eb0c3e66917162f8f1c44e95efc6958110b150cd49d14af9093bad0d7d60c5` |
| `fig5_shapley.csv` | `1b5cd0b736710082d02f341607fe5dae145a6199826308c0695242b8bb49a827` |
| `fig6_filters.csv` | `4b52f9bb5cca493ee95b7f59262a3a9b77efada079d70e883814ba38ab0d152c` |
| `fig7_strategies.csv` | `37bce00569e0ceb3ab69d81305b3b93c3514d37baf3304fc4e871958f4d29022` |
| `fig8_explain_move.csv` | `9d846917a8cacecbcfb1544fb667b3e0e57265b4bbf6a40dfe9fa37e2712dd57` |
| `figA1_reliability.csv` | `19622216a30f2b6278083345648ab208a354770a7725cff54eb973bb46ea2e44` |
| `figA2_encoding.csv` | `6b396f3d8a2e0ec1e6604cb07ccf23d7d782fc885a99b4e4728c7248effbd744` |
| `figA3_identifiability.csv` | `861801546e67bb414ce59cc6d2d84ca25d2a63accd48667c3f65c5cdc0739682` |
| `figA4_ablations.csv` | `951400bc7c3f67d66516900f6de96261621dc6ec0d574fa8aad953b1e24f20b3` |
| `figA5_robustness.csv` | `6e6981f45969cc9a505d42d33b585f42ee73952b060d0b64a86cbaf0027e726f` |
| `figA6_exploratory_d0.csv` | `ab7f013e97bebf90ca1e5454b62e6a0de3f3bf5b58d61d0ca806ff8f13ac62d3` |
| `figA7_exploratory_ma_cross.csv` | `710ccdd6d83adb734a1a1b32b6137b11453657197de7e306deb4f904d19c53c9` |

The table CSVs:

| File | sha256 |
|---|---|
| `f1_rg_class_paths.csv` | `a838f7cebc529dddae31a7ac7726e38370383daa84287af41b9e78f0f0d83ae9` |
| `f1_v_decile_paths.csv` | `db32683874d6ed03813810f73c9e3810786eb14bec245e73a43a0706f39ca210` |
| `f2_drift_vs_g.csv` | `2d82575553eaa79ce26fe05b9859470222255a81b0f030f53aa33d31e3e0551e` |
| `f4_monthly_ic.csv` | `10f7c22cd446a169ea4481b025686612c4f904df34b8ac554110306889f50468` |
| `f5_shapley_shares.csv` | `4b7114f321cf602e50d1fdb0874f65c03456d231bae8274cd3d2e6d9ac32f347` |
| `f8_explanation_ladder.csv` | `76696bf8a0f5a636b058c6e4f485b349f59cfc3eba7bdbc332b542dce9517f8b` |
| `fa_reliability.csv` | `af0ce4e245ff0c99a8b29c22e1b51325787d302135e1735ec1797c8b4f634c0c` |
| `t10_explanation_ladder.csv` | `d58de25f8b3bc8d38cd0722904e8afb121cb38be769cdcd268f44e1c80fe51e2` |
| `t11_explanation_share_theta.csv` | `4ad3c9e9feff9fcd6fc0657ee34cb92b6f1c383b27e07577936555506498978e` |
| `t12_question_battery.csv` | `5b29c92473bae8d038757d10f92c134adbac4618c1baad4a0efe86e29bd48fbc` |
| `t13_shapley.csv` | `a4fec4309891b7241386a7ce95059e736c2d4b87e7aa58cf6a5ccb0b43bb2992` |
| `t14_model_comparison.csv` | `1f09db3d94b5046e4ab761cd55bd32dccef063534d8ed4d2d0d2935adf63c0dd` |
| `t15_calibration.csv` | `c7fa83ab91049a6a328f397ebff93fe19fa9aa892b81ae08af04cebf55acefdc` |
| `t16_robustness.csv` | `5f2017bd953fc130ea3fb542f57612ab4c2fd6a4d7192612b42c0e0853ca8485` |
| `t17_sector_exploratory.csv` | `97dd083818aeb747ad3c16923b867b0ed6d0f0b616d0599ccc181c5b45c73d75` |
| `t18_probes_val_a.csv` | `114b88a202d89e4916eecbfd12cb19c667f99c181e6d600addef7201484f4fd9` |
| `t19_monthly_ic.csv` | `6ee63d6d4ac06908411d75fddb3170bcdb6855de2b44889db48d9264bb68046f` |
| `t1_primary.csv` | `a39e2f671ba9805c9381f28bb2db820fafc8aa83bde9192872f754ff342ae3c2` |
| `t1b_primary_by_model.csv` | `37cf7a2c0739482d26afc019866a3a57054d25a24ec97554eb7792fcc4c6d676` |
| `t20_strategies.csv` | `e5e999485685162a0c73a01fa8c2c44d274bc861f881befb5dc6e8eadbedd56a` |
| `t21_release_dates.csv` | `9b7df0c5f944a650285a3c66a4366d80042dcd8f432ee97f947ecf8e79eed551` |
| `t22_spend.csv` | `5266f2595b1c54e33428cd93d8d5ad644bea26a8a45f15a96f346dee3765c007` |
| `t23_company_identification.csv` | `37e72f312689045926f0c8330a79c2ecd61ccc41993ad278fe416ba16866cc8c` |
| `t24_exploratory_d0_signal.csv` | `7298e8d5ddc641824f7d1ba97282a4449c6d708254a4ab0911485b905a6f82c7` |
| `t25_ma_cross.csv` | `94b0e2993279bec1040f1bb65c3ad5024249e667d6ca6167ad3aa4858b9d0cca` |
| `t26_sconv_overlap.csv` | `7b38605a14f00a72c356131dd4af5301799a0bee1d67067006d53f333b3f6d62` |
| `t27_tournament.csv` | `0baff402fdc594dbfa2ea6333ce2684c536637771b3a90697f7b389b50545560` |
| `t28_filter_frontier.csv` | `33533b0056ffd67eeb6573d0f158c174229210ce1899276750ae0534c6e93d59` |
| `t29_encoding.csv` | `e7d8605787cb62b341d2758c7a4daf8435b99bb7eeed0cb3b784dc138f7f1855` |
| `t2_h2_over_under.csv` | `8bcb2c11f32a8574b4c70dbd21d211c31f5bf4884c731e4c99b6dafe0fe1306a` |
| `t30_derived.csv` | `37d0df01b47124dc6db9624b982279ad279f4f5dcfd72b191d37f86f6b37477f` |
| `t3_ic.csv` | `dae94be5f0635c9f7914619bc1bdb4541729ad29d2e6f2555b9a8ec4c544ef41` |
| `t4_secondary.csv` | `c474f9c40628f2da101a9c92ed41aec9b53012837fed16bc7a15c81f6f5b3067` |
| `t5_heterogeneity.csv` | `126066b207041c66d4e0b83cee5d8fec1bd6165a705e6578243e60c9562ba178` |
| `t6_convergence_ladder.csv` | `e2b1ff300300b610b187c12c5ea019d89e9fd13c69600306979245b296db7901` |
| `t7_gap_closure.csv` | `33062977043288242b154d2ab05d7097f9211457fe7ecb6465b426daa09a8d48` |
| `t8_tracking_error.csv` | `43ea9867777802a24d0d7d1ca4331f39c99e210428b1242ceef463bae84ef80b` |
| `t9_convergence_cuts.csv` | `a644adda42c8717329bdefe50f5b302895c6729ad119ddda3811e4dc5fbaa354` |

## Spend (from the ledgers; table t22)

| Resource | Used | Cap | Source |
|---|---|---|---|
| OpenRouter (decision-model API) | $15.73 (NA-05 $0.10, NA-06 $3.53, NA-07 $1.24, NA-09 $0.04, NA-11 $10.82) | $30 | `ledgers/spend.jsonl`, 310,587 spend lines |
| Kaggle (free 2×T4) | 25.38 GPU-hours: NA-08 23.38 (training), NA-11 2.00 (test inference) | 30 h a week | NA-08 and NA-11 REPORTs |
| FMP (30-minute bars, NA-10 only) | 15,858 requests | 17,000 | `ledgers/fmp_requests.jsonl` |

NA-12, NA-13 and NA-14 made no API call, Kaggle run or FMP request. The trials ledger holds 545 rows (the
deflated Sharpe's N); the test-access ledger holds 29 lines, none added by NA-14.
