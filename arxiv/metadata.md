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
- **License:** [to be chosen by the authors on the form; arXiv's perpetual non-exclusive license keeps every
  journal option open] (the code is MIT: `LICENSE`)
- **Keywords (title page):** large language models (LLMs); financial news; stock return prediction; look-ahead
  bias; memorization; pre-registration; overnight returns; market efficiency
- **Keywords (PDF metadata):** large language models (LLMs); AI decision models; stock return prediction;
  financial news; look-ahead bias; memorization; data contamination; backtest overfitting; deflated Sharpe ratio;
  pre-registration; overnight returns; market efficiency; overreaction and underreaction; calibration
- **JEL codes (in the paper):** G14, G12, C45, C52, C12

## Source bundle

Upload `artifacts/NA-16/arxiv_source.tar.gz` as is: `make paper-arxiv` writes it (deterministically) from the
manuscript sources, and `make paper-arxiv-check` compiles it with pdflatex in Docker's TeX Live 2023 image, as
arXiv does (report: `artifacts/NA-16/arxiv_check.json`; 2026-11-02: 0 errors, 0 overfull or underfull boxes, 0
undefined references, 40 pages, every font embedded). arXiv compiles with pdflatex and does not run BibTeX, so the
bundle holds `main.tex` with `\pdfoutput=1` on its first line and its two path macros (`\figdir`, `\tabdir`) set to
the bundle's own `figures/` and `tables/`, `main.bbl`, `sections/*.tex`, `generated/numbers.tex`, the TikZ source of
Figure 1 (`figures/design_timeline.tex`) and the NA-14 figures and tables the paper uses; nothing else. Check
arXiv's compiled preview before submitting. The page, figure and table counts above are those of the pdflatex
build; update them if the paper changes.

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
