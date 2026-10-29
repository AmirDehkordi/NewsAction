# arXiv submission metadata (draft)

Fields for the arXiv submission form. The abstract is `arxiv/abstract.txt` (written by `make paper-text` from
`paper/sections/abstract.tex`, so the two never differ). Items in [brackets] are placeholders the authors must fill.

- **Title:** The Market Reads the News First: A Pre-Registered, Look-Ahead-Free Test of AI Decision Models on
  Stock-Price Reactions
- **Authors:** Amir Dehkordi, Arman Khaledian, Alireza Kargarzadeh, Nariman Khaledian, Navid Parvini
  (the corresponding author's spelling to be confirmed)
- **Primary category:** cs.AI
- **Cross-lists:** q-fin.ST, cs.LG, cs.CL
- **Comments:** 41 pages, 11 figures, 12 tables; pre-registered (analysis plan frozen by hash before the test
  period was unblinded); replication package at [URL]
- **MSC / ACM classes:** none
- **Journal reference:** none
- **DOI:** none
- **License:** [to be chosen by the authors]
- **Keywords (in the paper):** large language models; AI decision models; financial news; stock returns; market
  efficiency; look-ahead bias; memorization; pre-registration; overreaction and underreaction
- **JEL codes (in the paper):** G14, G12, C45, C52, C12

## Source bundle

arXiv compiles with pdflatex and does not run BibTeX. The bundle holds `main.tex`, `sections/*.tex`,
`generated/numbers.tex`, `main.bbl` (from `paper/generated/main.bbl`), the figures and tables of
`artifacts/NA-14` that the paper uses (PDF figures, `.tex` tables) in `figures/` and `tables/`, and `main.tex`'s
two path macros set to those folders (`\figdir` and `\tabdir`). Every source file is ASCII and loads no
`fontspec`. The page, figure and table counts above are those of `artifacts/NA-16/paper.pdf`; update them if the
paper changes.
