# arXiv submission metadata (draft)

Fields for the arXiv submission form. The abstract is `arxiv/abstract.txt` (written by `make paper-text` from
`paper/sections/abstract.tex`, so the two never differ). Items in [brackets] are placeholders the authors must fill.

- **Title:** The Market Reads the News First: A Pre-Registered, Blinded Test of AI Decision Models on
  Stock-Price Reactions
- **Authors:** Amir Dehkordi (Independent Researcher), Alireza Kargarzadeh (TailState Intelligence Ltd),
  Nariman Khaledian (Independent Researcher), Navid Parvini (Zanista AI Ltd), Sid Ghatak (Increase Alpha, LLC),
  Arman Khaledian (Zanista AI Ltd)
- **Primary category:** cs.AI
- **Cross-lists:** q-fin.ST, cs.LG, cs.CL
- **Comments:** 40 pages, 12 figures, 12 tables; pre-registered (analysis plan frozen by hash before the test
  period was unblinded); code at https://github.com/AmirDehkordi/NewsAction
- **MSC / ACM classes:** none
- **Journal reference:** none
- **DOI:** none
- **License:** [to be chosen by the authors]
- **Keywords (title page):** large language models (LLMs); financial news; stock return prediction; look-ahead
  bias; memorization; pre-registration; overnight returns; market efficiency
- **Keywords (PDF metadata):** large language models (LLMs); AI decision models; stock return prediction;
  financial news; look-ahead bias; memorization; data contamination; backtest overfitting; deflated Sharpe ratio;
  pre-registration; overnight returns; market efficiency; overreaction and underreaction; calibration
- **JEL codes (in the paper):** G14, G12, C45, C52, C12

## Source bundle

arXiv compiles with pdflatex and does not run BibTeX. The bundle holds `main.tex`, `sections/*.tex`,
`generated/numbers.tex`, `main.bbl` (from `paper/generated/main.bbl`), the figures and tables of
`artifacts/NA-14` that the paper uses (PDF figures, `.tex` tables) in `figures/` and `tables/`, the TikZ source of
Figure 1 (`paper/figures/design_timeline.tex`, which `sections/design.tex` inputs as `figures/design_timeline`, so it
goes into the same `figures/` folder), and `main.tex`'s two path macros set to those folders (`\figdir` and
`\tabdir`). Every source file is ASCII and loads no `fontspec`; TikZ (`arrows.meta`, `decorations.pathreplacing`,
`patterns`) is in every TeX Live. The page, figure and table counts above are those of `artifacts/NA-16/paper.pdf`;
update them if the paper changes.

## SSRN submission (ready to paste)

SSRN's form takes the same title, authors and abstract as arXiv. Post the arXiv PDF once arXiv has assigned its
identifier, so that the SSRN record can cite it.

- **Title:** as above.
- **Abstract:** `arxiv/abstract.txt` (222 words, plain text).
- **Keywords:** large language models; financial news; stock return prediction; look-ahead bias; memorization;
  pre-registration; overnight returns; market efficiency
- **JEL classification:** G14, G12, C45, C52, C12
- **Date written:** November 2026
- **Paper link:** the arXiv abstract page, once assigned; code at https://github.com/AmirDehkordi/NewsAction
