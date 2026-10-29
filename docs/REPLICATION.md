# Replication

NA-14 (2026-10-29; revision pass the same day). How to rebuild the paper's figures, tables, captions and LaTeX
preview, what the rebuild needs, and what it must reproduce. The analyses themselves were run once, chunk by chunk
(NA-00 … NA-13), and their outputs are committed under `artifacts/`; each chunk's `artifacts/NA-xx/REPORT.md` gives
its own commands.

## Environment

- macOS 26.5 on arm64 (Apple M-series), Python 3.12.13, the project's locked `uv` environment (`uv.lock`):
  matplotlib 3.11.2, pandas 3.1.0, NumPy 2.5.4.
- Install with `uv sync --locked --all-extras`. Do not run `make sync`: it is an exact sync and removes the
  optional extras (`embed`, `laya`, `kaggle`) that earlier chunks use. `make paper` itself needs only the core
  dependencies.
- Fonts: Computer Modern, through matplotlib's bundled `cmr10` and mathtext's `cm` set, so the figures match a
  default LaTeX document and do not depend on the system's fonts. The PDF and PNG bytes still depend on the
  matplotlib and FreeType builds; the plotted numbers are the CSVs.
- LaTeX (for `make paper-preview` only): `tectonic` (Homebrew; it fetches its TeX bundle over the network on first
  use). `make paper` writes the LaTeX but does not compile it.

## What `make paper` needs

All of it is committed except three NA-13 work files.

| Input | Where | Committed |
|---|---|---|
| NA-03, NA-06, NA-07, NA-11, NA-12, NA-13 and NA-13b outputs | `artifacts/NA-xx/` (figure data, tables, results JSON; NA-11's val-B run of the frozen spec; NA-13b's eight exploratory tables) | yes |
| NA-05 model catalog (release dates) | `artifacts/NA-05/catalog.json` | yes |
| NA-08 and NA-11 REPORTs (Kaggle GPU-hours) | `artifacts/NA-08/REPORT.md`, `artifacts/NA-11/REPORT.md` | yes |
| The operator's input (Laya's release date) | `artifacts/NA-14/inputs/operator.yaml` | yes |
| The summaries of the pre-registration deviations | `artifacts/NA-14/inputs/prereg_deviations.yaml`, checked against `docs/PREREG.md` §15 | yes |
| The caption templates | `artifacts/NA-14/captions.yaml` | yes |
| The test split's end, the budget caps | `configs/splits.yaml`, `configs/project.yaml` | yes |
| The ledgers (spend, FMP requests, trials, test access) | `ledgers/*.jsonl` (read only) | yes |
| NA-13's stored test positions, daily books and placebo books | `work/strategy/{positions,books,placebo}_test.parquet`, registered in `work/MANIFEST.json` | no (gitignored) |

The three work files feed two tables: t26 (the S-CONV / gap-fade overlap that NA-13's REPORT §4 states but no
committed file holds) and t33 (the placebo's Sharpe quantiles, which NA-13's REPORT §7 quotes in part). Without
them, rebuild NA-13 first (its REPORT §12 lists the commands; the test-period returns come through one
`newsaction.lock` read after unblinding, as NA-13 did once).

`make paper` reads nothing else: no raw data (`Data/`), no ATOM snapshot, no decision-model cache, no API, no
Kaggle, no FMP. It never imports the decision-model client, `newsaction.lock`, `panel.targets` or
`panel.reactions`, and it fails if it does (`tests/test_figures_paper.py`).

## Commands

```bash
uv sync --locked --all-extras                       # the locked environment, extras kept
make verify                                         # lint, types, tests, manifest, ledger chains
make paper                                          # rebuild tables, LaTeX, figure CSVs, figures, captions, preview .tex
make paper-preview                                  # compile artifacts/NA-14/paper_preview.tex with tectonic and check it
uv run --locked python -m newsaction.figures.captions   # re-check every caption number against its table
uv run --locked python -m newsaction.figures.render fig3_convergence   # one figure from its CSV
```

`make paper` (`newsaction.figures.paper`) runs in about 10 seconds:

1. checks the sha256 of each of its 45 inputs against `artifacts/NA-14/digests.json` and stops if one differs;
2. writes the tables (`artifacts/NA-14/tables`: CSV, `keys.json`, `index.json`), their LaTeX (six main tables
   `tab1` … `tab6` and an appendix table per CSV, with `latex.json` listing every cell each one prints), the 26
   figure CSVs, the 26 figures (PDF and 300-dpi PNG; a figure in which a label touches a line, a marker, a bar, a
   spine or another label is refused), `captions.md` after checking that every number in a caption
   equals its table cell, and `paper_preview.tex`;
3. compares the sha256 of its 127 text outputs (CSV, LaTeX, JSON, Markdown) with the committed digests and fails on
   any difference; the 52 PDF and PNG digests are compared and reported, not enforced;
4. fails if any `ledgers/*.jsonl` changed during the run.

`make paper-preview` (`newsaction.figures.preview --compile`) compiles the preview with tectonic in deterministic
mode (`--keep-logs`) and fails on a TeX error, any overfull box, a float taller than the page, an undefined
reference or a font that is not embedded; it copies the PDF to `artifacts/NA-14/paper_preview.pdf` and the log to
`artifacts/NA-14/paper_preview.log` (not committed: it names the temporary build directory), and reports the PDF's
sha256 (not enforced: tectonic's bundle decides the bytes).

The author's steps after a deliberate change: `python -m newsaction.figures.paper --write-digests`, then
`python -m newsaction.figures.contract` (registers every NA-14 file in `work/MANIFEST.json`, drops the entries of
NA-14 files that no longer exist, and rewrites the NA-14 section of `docs/DATA_CONTRACT.md`).

## How every number traces

- Each figure reads only its CSV (`render.read`; the figure modules read no file). A figure CSV holds one row per
  plotted value and names its upstream file, row key and column; `tests/test_figures_trace.py` re-reads every one
  of those cells. Intervals are the stored bootstrap bounds, or ±1.96 × a stored standard error (±1 in the
  exploratory monthly figure), or ±1.96 × |value / t| from a stored t statistic, or the Wilson interval of a stored
  share and its stored number of trials.
- Two NA-14 tables are simple aggregations of stored files, each recomputed by a test: t33, numpy's quantiles of
  the Sharpe ratios of NA-13's stored placebo books, and t35, each book's gross mean ÷ turnover from NA-13's
  strategy table.
- Each caption number is `{{table/key/column}}` from `artifacts/NA-14/tables/keys.json`;
  `tests/test_figures_captions.py` checks it against the table cell, and for a copied NA-12 table against NA-12's
  CSV. Every number in the LaTeX tables is likewise a cell of `keys.json`, listed per table in `latex.json`.
  NA-12's tables are copied byte for byte; NA-13's strategy table and the NA-03, NA-06, NA-07 and NA-11 figure
  sources gain only a row key; NA-13b's eight tables (exploratory) are copied with their own key, and its four
  appendix figures (A16 to A19) read only those copies.

## Expected digests

The full list (inputs, outputs, figures) is `artifacts/NA-14/digests.json`. The figure CSVs:

| File | sha256 |
|---|---|
| `fig1_validation_test.csv` | `3d3fa11d672f538f6ffc900ec1cefee5ba48766f7dcdb33b9e3880faff1bb069` |
| `fig2_priced_at_open.csv` | `be9a29497719fce6cd167396fcfe77716c5c41c530648bdae051fb88e4cd92aa` |
| `fig3_convergence.csv` | `c258a042b0e8a856d29f17a253c16ba84642333966b64124ed9bbade3489c4b3` |
| `fig4_over_under.csv` | `57cfc40e379a83ac114969a20f574ae20403ba5481c14b667055043b2a870e4f` |
| `fig5_explaining_moves.csv` | `5efe9ce25a2ae7395425a44042d0cba0f796837907403043ae1e6b2a849ecb8a` |
| `fig6_strategies.csv` | `ebabb993ecb618cb047751e1d1f0dbb8e214f127a558be0d41c6f9490ff23ef9` |
| `fig7_memorisation.csv` | `fc78bcd4f1b424dce43168744864a0d09be7812f0e1b21735039f83f1754cce0` |
| `figA10_ablations.csv` | `951400bc7c3f67d66516900f6de96261621dc6ec0d574fa8aad953b1e24f20b3` |
| `figA11_persistence.csv` | `bb78a31208a735a1c69a952f91371a5076c2a8c98d053a0b7c5e4a39b4074576` |
| `figA12_strategy_paths.csv` | `601fce88020a4811a4e734942efd08e27b11b27e36818c5307c5a6d3fe45b282` |
| `figA13_probes.csv` | `4c00fca0ccfe4fbd8db0a7659f3dbc8a37ccf7e6172fe3e0983e4f0b1d76318a` |
| `figA14_exploratory_d0.csv` | `ab7f013e97bebf90ca1e5454b62e6a0de3f3bf5b58d61d0ca806ff8f13ac62d3` |
| `figA15_exploratory_ma_cross.csv` | `710ccdd6d83adb734a1a1b32b6137b11453657197de7e306deb4f904d19c53c9` |
| `figA16_selective_coverage.csv` | `67ba3e4bf6913bbde6788a862fc20c9700576fe5b9117282ae9276123452ffdc` |
| `figA17_watch_open.csv` | `c8375cc8a034bb8db8b1f45960d6a8a6fc5f941ad3ec43be5d41cdd512503122` |
| `figA18_conditioning_map.csv` | `1f6994f8a098e165ff91f7f5168578315a8ba9c2374c619c84344071c2b5152e` |
| `figA19_output_histograms.csv` | `28e86f8590c55c707fe17fcba26993bab8cca290cd841a6e11d2db9759d82c05` |
| `figA1_tournament.csv` | `8689cbdabe7fa122f75146fccb25c388d186e2cd1924c8a60151fc59bfb66e68` |
| `figA2_filters.csv` | `4b52f9bb5cca493ee95b7f59262a3a9b77efada079d70e883814ba38ab0d152c` |
| `figA3_encoding.csv` | `44deb913fc22da122e458af3daa041213c1b815c2381ec33596284048c37f6ae` |
| `figA4_reliability.csv` | `19622216a30f2b6278083345648ab208a354770a7725cff54eb973bb46ea2e44` |
| `figA5_robustness.csv` | `6e6981f45969cc9a505d42d33b585f42ee73952b060d0b64a86cbaf0027e726f` |
| `figA6_monthly_ic.csv` | `9043d02e29b677b38bb322af39a09acdb942193545b6de77eb839f1e6d6fe32b` |
| `figA7_convergence_detail.csv` | `e34466fb446a83d07e655b06ba9d515f05b5c61c7a7625f48c4601e22659995e` |
| `figA8_drift_laya_fin.csv` | `9ef5f06a1f3e1f6ddb7b28dd0b8a5eed807d79b58526e6828f99c702cd77655d` |
| `figA9_shapley.csv` | `1b5cd0b736710082d02f341607fe5dae145a6199826308c0695242b8bb49a827` |

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
| `t21_release_dates.csv` | `94eca271b36b87df12b77e2d6112cc79e3121c7ce406fd2cc97006ad1c2a05d0` |
| `t22_spend.csv` | `b15734e76493b6922610eff48b9da70360f26169b613654fc7e1a80ef505d5d8` |
| `t23_company_identification.csv` | `37e72f312689045926f0c8330a79c2ecd61ccc41993ad278fe416ba16866cc8c` |
| `t24_exploratory_d0_signal.csv` | `7298e8d5ddc641824f7d1ba97282a4449c6d708254a4ab0911485b905a6f82c7` |
| `t25_ma_cross.csv` | `94b0e2993279bec1040f1bb65c3ad5024249e667d6ca6167ad3aa4858b9d0cca` |
| `t26_sconv_overlap.csv` | `7b38605a14f00a72c356131dd4af5301799a0bee1d67067006d53f333b3f6d62` |
| `t27_tournament.csv` | `0baff402fdc594dbfa2ea6333ce2684c536637771b3a90697f7b389b50545560` |
| `t28_filter_frontier.csv` | `33533b0056ffd67eeb6573d0f158c174229210ce1899276750ae0534c6e93d59` |
| `t29_encoding.csv` | `e7d8605787cb62b341d2758c7a4daf8435b99bb7eeed0cb3b784dc138f7f1855` |
| `t2_h2_over_under.csv` | `8bcb2c11f32a8574b4c70dbd21d211c31f5bf4884c731e4c99b6dafe0fe1306a` |
| `t30_derived.csv` | `37d0df01b47124dc6db9624b982279ad279f4f5dcfd72b191d37f86f6b37477f` |
| `t31_market_replication.csv` | `47e320d34232bd5932908a377f84b9135d627865c2846cb91bcf5e6d6f730cb5` |
| `t32_val_b_ic.csv` | `b2ae900683c016a071001e7285abeb2913eeb5d7db5cd4990110b350237c695a` |
| `t33_placebo_sharpe.csv` | `23f4be70017dead01d6c839cfcdad22fc8d17569105daaf2a3c4d1f9de0dd1a9` |
| `t34_prereg_deviations.csv` | `9fbc3b09165470ced5af69b6aa368326ebef61d0444305d0f08eb78b5e73c36c` |
| `t35_break_even.csv` | `c58d8dd3a89d9fa84cc7118d8bc4aeefe38ccc2799bf0d0404b1181306922470` |
| `t36_selective_coverage.csv` | `16154cc72359b8d414061f7ebb2e22f04c03ba298d85bee274bd6bf445448a27` |
| `t37_watch_open.csv` | `9839242fef8e8a86c9d43ae5f3fbc7dea2b991776f8181aeccb7c3be75899729` |
| `t38_conditioning.csv` | `a3734abb257babb3f0968c104d3d4384482d9083f332026cc564d5893b5c78c4` |
| `t39_conditioning_books.csv` | `98674a442ec7f0fa3c3eb4e715c6156ce15a10f0c52bd7f7789f3bb3620c3854` |
| `t3_ic.csv` | `dae94be5f0635c9f7914619bc1bdb4541729ad29d2e6f2555b9a8ec4c544ef41` |
| `t40_conditioning_detail.csv` | `5d8e9174eb1ff609d25b0cec422d6a03be9dea35afac138c574263dc82231afc` |
| `t41_output_histograms.csv` | `6317987a9ebb8ffb65e0015a85929c5d3b5daa5b737394d1cf134a5f0fa779df` |
| `t42_output_summary.csv` | `a186b3713f04c6882579a2f67b69277442a667f388f5ddaade0cc87a08fc63c7` |
| `t43_band_disclosure.csv` | `ce108532ca82e063a29424137a518bd2bcd898657480546bc1326ea7c1b59d33` |
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

NA-12, NA-13, NA-13b and NA-14 made no API call, Kaggle run or FMP request. The trials ledger holds 1,620 rows (t22):
NA-13's deflated Sharpe ratios used the 545 it held when NA-13 computed them (t20's `n_trials`), NA-13b's the 1,620
after its own rows (t39's). The test-access ledger holds 29 lines, none added by NA-13b or NA-14.
