"""Masking of news text (PREREG §6.3; PRD NA-04 S3).

In this order, on each title and snippet (already scrubbed by NA-02):
1. **Datelines and identifiers.** A leading press-release dateline ("JACKSONVILLE, Fla., Oct. 16, 2025
   /PRNewswire/ --", "NEW YORK (Reuters) -") and ISIN codes are removed: they carry dates and
   headquarters cities. Option contracts ("250703 305.00C (ADI250703C305000)": expiry, strike, ticker)
   become "option".
2. **Company.** The company's names and aliases (``configs/aliases.yaml``; ``CompanyAliases``) become
   "the company", with an optional legal suffix ("Apple Inc." → "the company"). Ticker forms become "the
   company": $T, EXCH:T with any upper-case exchange code (BOATS:NEE), T.O, T.N, T/PR, T.US, T's, bare T; a
   parenthesized ticker ("(NASDAQ: AAPL)", "(COST 0.53%)", "（紐交所：DE）", "（HOOD US）") is removed. A
   stoplisted ticker (an English word: COST, MET, ALL, MS) goes in upper case unless the whole text is in
   capitals, except a clock time ("4:30 PM") and IT before an IT noun ("IT spending"). Chinese, Japanese and
   Korean names harvested before the company's own ticker ("迪爾股份（紐交所：DE）"; ``cjk_company_names``)
   go too.
3. **Dates.** Full dates, day ranges, weekdays and months, in English, French, German, Italian, Spanish,
   Portuguese, Dutch, Polish, Chinese, Japanese and Korean → "recently"; years, also glued to letters or
   CJK ("EHA2025", "2025年") → "the year"; fiscal years → "the fiscal year"; quarter labels in any case
   ("Q3 FY2025", "2025Q2", "Q2-25", "Second Quarter", "3Q25", "3. Quartal", "第二季度") → "the quarter" /
   "quarterly"; half-year labels ("first half", "1H25", "上半年") → "the half-year".
4. **People.** spaCy ``en_core_web_sm`` PERSON entities (not matching any S&P 500 company alias), and every
   capitalized occurrence of a corpus surname (the last word of a multi-word name seen at least
   ``SURNAME_MIN_COUNT`` times; "Trump", "Powell" alone): a name right after a role noun ("CEO Tim Cook",
   "analyst Dan Ives") is dropped; otherwise it becomes "an executive" when an executive title is within six
   words, else "a person". Chinese transliterations of Western names ("薩姆·阿爾特曼") become "a person".
5. **Price talk and price levels.** ``news.detect`` scrub again (after-the-fact and price-path sentences,
   share-price levels); then sentences with a stock / share price move in percent and ticker quotes
   ("MPC-1.32%", "· IP. -0.58%", "FSLR0.00%", "|Price:49.32|Chg%:-0.60") are dropped; price-target amounts
   become a relative change ("raises its price target to $622
   from $600" → "raises its price target up by about 4%") or are dropped, and per-share deal prices become
   "a per-share price". Fundamental figures (EPS, revenue, dividends, guidance) are kept.

A replacement at the start of a sentence is capitalized.
"""

from __future__ import annotations

import functools
import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from newsaction.config import load_yaml
from newsaction.news.detect import load_detector, split_sentences
from newsaction.states import ALIASES_PATH

COMPANY: Final = "the company"
EXECUTIVE: Final = "an executive"
PERSON: Final = "a person"
RECENTLY: Final = "recently"
YEAR: Final = "the year"
FISCAL_YEAR: Final = "the fiscal year"
QUARTER: Final = "the quarter"
HALF_YEAR: Final = "the half-year"
SURNAME_MIN_COUNT: Final = 3
SPACY_MODEL: Final = "en_core_web_sm"
SPACY_EXCLUDE: Final = ("parser", "lemmatizer", "attribute_ruler", "tagger", "senter", "morphologizer")

EXCHANGES: Final = (
    r"NYSE\s?Arca|NYSE\s?American|NYSE\s?MKT|NYSEARCA|NYSEAMERICAN|NYSEMKT|NYSE|NASDAQGS|NASDAQGM|NASDAQCM|"
    r"NasdaqGS|NasdaqGM|NasdaqCM|NASDAQ|Nasdaq|AMEX|BATS|CBOE|Cboe|OTC|OTCMKTS"
)
# any exchange-like code before a colon: NYSE:, BOATS:, OTC:, XETRA:, LSE: (NA-04 verification)
EXCH_PREFIX: Final = (  # ... or a Chinese exchange name: "紐交所:CTRA", "納斯達克：COIN"
    rf"(?:(?<![A-Za-z])(?:{EXCHANGES}|[A-Z][A-Za-z]{{1,11}}|[\u3400-\u9fff]{{2,10}})\s*[:：]\s*)"
)
# a bare ticker starts after a non-word character, after "X/" or "x-" in a list or pair ("WMT/TGT/TJX",
# "Omnicom-IPG", "$NYSE-LYV") or after "x." ("Arista Networks, Inc.ANET"), and may carry digits ("ABBV19",
# "GE9X", "HCA2)")
BARE_BEFORE: Final = r"(?:(?<![A-Za-z0-9$&.\-/])|(?<=[A-Za-z][/\-])|(?<=[a-z]\.))"
# share-class / venue suffixes: AAPL.O, MS.N, COIN.US, NEE/PR, NEE/PT, BRK.B (the class is part of the ticker)
# ... and Reuters' exchange letter: AAPL-Q, NKE-N
TICKER_SUFFIX: Final = r"(?:[./](?:[A-Z]{1,2}|PR[A-Z]?)(?![A-Za-z])|-[A-Z](?![A-Za-z0-9]))?"
# Latin letters and digits: a ticker is a word only between other characters (CJK may touch it:
# "（紐交所：DE）")
LATIN: Final = r"A-Za-z0-9\u00C0-\u024F"
# an upper-case stoplisted ticker that is not the company: a clock time ("4:30 PM"), IT before an IT noun
_CLOCK: Final = re.compile(r"\d\s?$")
_LIST_BEFORE: Final = re.compile(r"\b[A-Z]{2,5},\s*$")  # a list of tickers: "ALC, KEYS, TOL"
_LIST_AFTER: Final = re.compile(r"^,\s*[A-Z]{2,5}\b")
# a ticker right after the company's (masked) name: "MARRIOTT INTERNATIONAL INC /MD/ MAR:"
_COMPANY_BEFORE: Final = re.compile(r"(?i)the company(?:\s*/[A-Z]{2}/)?\s*$")
# a ticker before a period label or an earnings word: "MAR Q2 2025 TRANSCRIPT"
_CUE_AFTER: Final = re.compile(
    r"^\s+(?:Q[1-4]|[1-4]Q|FY|H[12]|EPS|Earnings|EARNINGS|Stock|STOCK|Shares|SHARES)\b"
)
_IT_NOUN: Final = re.compile(
    r"-|\s+(?:[Ss]ervices?|[Ss]pending|[Ss]ector|[Ii]ndustry|[Bb]udgets?|[Ss]ecurity|[Ii]nfrastructure|"
    r"[Dd]epartments?|[Tt]eams?|[Ll]eaders|[Pp]rofessionals|[Ss]ystems|[Ss]upport|[Oo]perations|[Oo]utsourcing|"
    r"[Cc]onsulting|[Ss]olutions|[Mm]odernization|[Ee]nvironments?|[Mm]anagers|[Oo]rganizations|[Ii]nvestments?|"
    r"[Ll]andscape|[Ss]tacks?|[Cc]osts?|[Ss]pend)\b"
)
# option contracts: "250703 305.00C" (expiry yymmdd, strike) → "option"; "(ADI250703C305000)" → removed
_OPTION_TERMS: Final = re.compile(r"\b\d{6}\s+\$?\d+(?:\.\d+)?\s?[CP]\b")
_OPTION_CODE: Final = re.compile(r"\s*\(?\b[A-Z]{1,6}\d{6}[CP]\d{3,9}\b\)?")
# a quote of any ticker with a signed percent change: "MPC-1.32%", "(AAPL +0.87%)", "MSFT -1.19 %"
_NOT_TICKERS: Final = (
    r"(?!(?:EPS|FCF|GDP|CPI|PPI|PCE|ROE|ROI|ROA|YOY|QOQ|EBIT|ARR|NII|NIM|ARPU|AUM|RPO|FY|Q[1-4])\b)"
)
QUOTE: Final = re.compile(
    rf"\s*\(\s*{_NOT_TICKERS}[A-Z]{{1,5}}(?:[.\-][A-Z])?\s*[+\-−–]?\s?\d+(?:\.\d+)?\s?%\s*\)"
    rf"|(?<![A-Za-z0-9]){_NOT_TICKERS}[A-Z]{{1,5}}(?:[.\-][A-Z])?\s?[+\-−–]\s?\d+(?:\.\d+)?\s?%(?:increase|decrease)?"
    rf"|(?<![A-Za-z0-9]){_NOT_TICKERS}[A-Z]{{2,5}}\d+\.\d+\s?%"  # "FSLR0.00%"
    # a quote after the company's masked name: "the company. -0.01%", "the company -1.05%decrease" (quote
    # widgets, "Tesla · TSLA. +3.52%.", go in the lead step: ``_WIDGET``)
    r"|(?<=[Tt]he company)\.?\s*[+\-−–]\s?\d+(?:\.\d+)?\s?%(?:increase|decrease)?\.?"
    r"|\|?\s*Price:\s?\$?[\d.,]+\s*\|\s*Chg%:\s?[+\-−–]?[\d.,]+%?"  # "FE|…|Price:49.320|Chg%:-0.600"
    # "Price: 236.34, Change: +4.08, Percent Change: +2.11"
    r"|\bPrice:\s?\$?\d[\d.,]*(?:,?\s*Change:\s?[+\-−–]?[\d.,]*)?"
    r"(?:,?\s*Percent Change:\s?[+\-−–]?[\d.,]*\s?%?)?"
)
# a quote widget inside a name ("Constellation · CEG. +3.58%. Energy's"): removed before the company step
_WIDGET: Final = re.compile(
    rf"\s*·\s*{_NOT_TICKERS}[A-Z][A-Za-z.\-]{{0,7}}?\.?\s*(?:[+\-−–]?\s?\d+(?:\.\d+)?\s?%|-{{2,}})\.?"
)
# a wire dateline inside the text, after a time: "08:30 AM. CHICAGO --(BUSINESS WIRE)--" (the headquarters
# city)
_WIRE_MID: Final = re.compile(
    r"(?:\b\d{1,2}:\d{2}\s?[AaPp]\.?[Mm]\.?(?:\s?(?:ET|EST|EDT|CET|CEST|PT|PST|PDT|GMT|UTC))?\.?\s*)?"
    r"(?:[A-Z][A-Za-z.'\-]*(?:[ ,]+[A-Z][A-Za-z.'\-]*){0,3}\s*)?-{1,2}\s*\(\s*(?:BUSINESS WIRE|Business Wire|"
    r"PRNewswire|PR Newswire|GLOBE NEWSWIRE|GlobeNewswire|ACCESSWIRE|ACCESS Newswire|Newsfile)\s*\)\s*-{0,2}"
)
# a share-price level ("boosts stock to $102.89", "shares at $120"), not a per-share figure or an amount
_LEVEL: Final = re.compile(
    r"(?i)\b(?:stock|shares?)\s+(?:to|at|closed\s+at|trading\s+at|hits?|reached|reaches)\s+\$\s?\d[\d,]*(?:\.\d+)?"
    r"(?![\d.,]*\s*(?:[MBK]\b|million|billion|bn|trillion))(?!\s*(?:per|a|/)\s*share)"
)
_PER_BEFORE: Final = re.compile(r"(?i)\bper\s+(?:\w+\s+)?$|dividend|distribution")
# a footnote mark after an amount ("a previous target of $49.00.1;")
_FOOTNOTE: Final = re.compile(r"(\$\s?\d[\d,]*\.\d{2})\.\d(?!\d)")
_VERBS: Final = (
    r"rise[sn]?|rose|rising|fall(?:s|en|ing)?|fell|jump(?:s|ed|ing)?|drop(?:s|ped|ping)?|gain(?:s|ed|ing)?|"
    r"slides?|slid|slip(?:s|ped)?|climb(?:s|ed|ing)?|surg(?:e|es|ed|ing)|plung(?:e|es|ed|ing)|soar(?:s|ed|ing)?|"
    r"tumbl(?:e|es|ed|ing)|sinks?|sinking|sank|rall(?:y|ies|ied)|declin(?:e|es|ed|ing)|advanc(?:e|es|ed|ing)|"
    r"edg(?:e|es|ed)\s+(?:up|down|higher|lower)|trad(?:e|es|ed|ing)\s+(?:up|down|higher|lower)"
)
_MOVE_VERB: Final = rf"(?:{_VERBS}|(?:are|is|was|were)\s+(?:up|down)|higher|lower|up|down)"
# a verb glued to a ticker ("DGXjumped 6.4%", NA-04 revision 3): an upper-case letter, then a lower-case verb
_GLUED_VERB: Final = rf"(?-i:(?<=[A-Z])(?=[a-z]))(?:{_VERBS})"
# a stock / share price move in percent (PREREG §6.4), unless a fundamental noun is its subject
_SUBJECT: Final = (
    r"(?:shares?|stocks?|the\s+company(?:['’]s)?|premarket|pre-market|after-hours|extended\s+trading)"
)
_MOVE_SUBJECT: Final = re.compile(rf"(?i)\b{_SUBJECT}\b")
PRICE_MOVE: Final = re.compile(
    rf"(?i)\b{_SUBJECT}\b(?P<mid>[^.!?%]{{0,50}}?)(?:\b{_MOVE_VERB}|{_GLUED_VERB})\b[^.!?]{{0,25}}?"
    r"\d+(?:[.,]\d+)?\s?%"
)
PRICE_MOVE_AFTER: Final = re.compile(
    r"(?i)\b\d+(?:[.,]\d+)?\s?%\s+(?:in\s+)?(?:premarket|pre-market|before\s+the\s+bell|after\s+hours|after-hours)"
)
_FUNDAMENTAL_SUBJECT: Final = re.compile(
    r"(?i)\b(?:revenues?|sales|earnings|eps|income|profits?|margins?|volumes?|orders|shipments|deliveries|guidance|"
    r"dividends?|bookings|subscribers|users|traffic|backlog|cash\s+flow|demand|output|production|compensation|"
    r"buybacks?|repurchases?|outstanding|count|targets?|ratings?|estimates?|forecasts?|outlook|sales|costs?|"
    r"expenses?|spending|capex|debt|assets|deposits|loans|premiums|rates?|unemployment|inflation|gdp|index|"
    r"prices?\s+of\s+(?!the\s+company))\b"
)
_PT: Final = r"(?:price\s+targets?|target\s+prices?|price\s+objectives?|price\s+goals?|PTs?|targets?)"
_AMT: Final = (
    r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?!\d|\.\d|\s*(?:million|billion|trillion|bn|mn|[mbk]\b|%))"
)
PT_FROM_TO: Final = re.compile(
    rf"(?i)\b(?P<label>{_PT})\b(?P<mid>[^$.;!?]{{0,60}}?)\bfrom\s+{_AMT}\s+to\s+{_AMT}"
)
PT_TO_FROM: Final = re.compile(
    rf"(?i)\b(?P<label>{_PT})\b(?P<mid>[^$.;!?]{{0,60}}?)(?:\b(?:to|at)\s+)?{_AMT}\s*,?\s*"
    rf"(?:from|vs\.?|versus|up\s+from|down\s+from)\s+{_AMT}"
)
PT_AMOUNT: Final = re.compile(
    rf"(?i)\b(?P<label>{_PT})\b(?P<mid>[^$.;!?]{{0,80}}?)"
    rf"(?:\b(?:to|at|of|from|is)\s+)?(?:(?:the|a)\s+previous\s+)?{_AMT}"
)
AMOUNT_PT: Final = re.compile(rf"(?i){_AMT}\s+(?P<label>{_PT})\b")
PER_SHARE: Final = re.compile(r"(?i)\$\s?\d[\d,]*(?:\.\d+)?\s+(?:a|per)\s+share\b")
_DEAL: Final = re.compile(
    r"(?i)\b(?:acquir\w*|acquisition|buy(?:out|s|ing)?|bought|offer\w*|deal|merger|merge|takeover|tender|bid|"
    r"valu\w+|purchas\w*|sale|sell\w*|sold|pric(?:ed|ing)|consideration|premium)\b"
)
_FUND_LEFT: Final = re.compile(
    r"(?i)\b(?:earnings|eps|dividends?|income|loss(?:es)?|profits?|revenues?|sales|ffo|affo|book\s+value|"
    r"cash\s+flow|distributions?|payout|nav|net\s+asset|guidance|estimates?|consensus)\b"
)
_MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH: Final = "(?:" + "|".join([*_MONTHS, *(m.upper() for m in _MONTHS)]) + ")"
MON: Final = (
    r"(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\."
)
MONTH_ANY: Final = (
    rf"(?:{MONTH}|{MON}|(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|"
    rf"OCT|NOV|DEC)(?=\s+\d))"
)
WEEKDAY: Final = "(?:" + "|".join([*_WEEKDAYS, *(d.upper() for d in _WEEKDAYS)]) + ")"
YEAR_RE: Final = r"(?:19\d\d|20\d\d)"
APOS: Final = "['’‘]"  # the straight, right and left single quotes of "'25", "FY’25", "Q1 ‘25"
# French, German, Italian, Spanish, Portuguese, Dutch and Polish month and weekday names (NA-04 verification)
F_MONTH: Final = (
    r"(?:janvier|f[ée]vrier|avril|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre|januar|j[äa]nner|"
    r"februar|m[äa]rz|maerz|juni|juli|oktober|dezember|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
    r"settembre|ottobre|dicembre|enero|febrero|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|"
    r"noviembre|diciembre|janeiro|fevereiro|mar[çc]o|junho|julho|setembro|outubro|novembro|dezembro|januari|"
    r"februari|maart|augustus|stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|wrze[śs]nia|"
    r"pa[źz]dziernika|listopada|grudnia)"
)
F_MONTH_DAY_ONLY: Final = r"(?:mars|mai|mei|maio)"  # also ordinary words: only next to a day number or year
F_WEEKDAY: Final = (
    r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|lundi|mardi|mercredi|jeudi|vendredi|samedi|"
    r"dimanche|luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica|lunes|martes|"
    r"mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo|segunda-feira|ter[çc]a-feira|quarta-feira|quinta-feira|sexta-feira|"
    r"maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)"
)
F_PREP: Final = (
    r"(?:(?:am|vom|bis|zum|seit|ab|le|du|au|des|el|del|dal|il|op|de|em|no|na|w|z|ce|cette|diesen|letzten|"
    r"vergangenen|n[äa]chsten|este|ese|questo|scorso)\s+)"
)
# ordinal quarters and halves written out (NA-04 revision 3): "deuxième trimestre", "zweiten Quartal"
ORDINAL_X: Final = (
    r"(?:premi(?:er|ère)|1(?:er|re)|deuxi[eè]me|2(?:e|ème)|seconde?|troisi[eè]me|3(?:e|ème)|quatri[eè]me|"
    r"4(?:e|ème)|primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|prim[oa]|second[oa]|terz[oa]|quart[oa]|"
    r"primeir[oa]|terceir[oa]|erste[nrs]?|zweite[nrs]?|dritte[nrs]?|vierte[nrs]?|eerste|tweede|derde|vierde)"
)
ORDINAL_X_HALF: Final = (
    r"(?:premi(?:er|ère)|1(?:er|re)|seconde?|deuxi[eè]me|2(?:e|ème)|primer[oa]?|segund[oa]|prim[oa]|"
    r"second[oa]|primeir[oa]|erste[nrs]?|zweite[nrs]?|eerste|tweede)"
)
# a bare T1–T4 after a French, Spanish or Portuguese word that announces a period (fixed-width lookbehinds)
_T_WORDS: Final = ("au", "Au", "du", "le", "Le", "el", "El", "del", "no", "do", "em", "ao")
T_CONTEXT: Final = "|".join(
    [rf"(?<=\b{w} )" for w in _T_WORDS] + [rf"(?<={w} )" for w in ("sultats", "sultados", "sultado")]
)  # "(ré)sultats", "resultados": endings, since "é" and "s" have no word boundary between them
DAY: Final = r"(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?"
DAY_RANGE: Final = rf"{DAY}(?:\s?[–\-]\s?{DAY}(?![\d%]))?"  # "July 17-18", "4–5 August"
# Chinese, Japanese and Korean dates and periods (NA-04 verification 2): 2025年8月7日（星期四）, 8月7日, 週一,
# 木曜日, 第二季度, 上半年
CJK_YEAR: Final = rf"{YEAR_RE}\s?(?:[財财]?年度?|년)"
CJK_WEEKDAY: Final = (
    r"(?:(?:星期|週|周|禮拜|礼拜)[一二三四五六日天]|[月火水木金土日]曜日?|[월화수목금토일]요일)"
)
CJK_DAY: Final = (
    rf"\d{{1,2}}\s?[月월]\s?\d{{1,2}}\s?[日号일](?:\s?[（(]\s?(?:{CJK_WEEKDAY}|[月火水木金土日])\s?[）)])?"
)
CJK_QUARTER: Final = r"第\s?[一二三四1-4１-４]\s?[財财]?(?:季度|季|四半期)"
CJK_HALF: Final = r"[上下]半(?:年|期)"
# a year glued to a currency code is an amount ("USD2025")
_NOT_CURRENCY: Final = (
    r"(?<!USD)(?<!EUR)(?<!GBP)(?<!JPY)(?<!CHF)(?<!CAD)(?<!AUD)(?<!HKD)(?<!CNY)(?<!RMB)(?<!Rs)"
)
PREP: Final = (
    r"(?i:(?:as\s+of|earlier\s+in|later\s+in|in|on|at|during|from|since|until|through|by|before|after|around|"
    r"ahead\s+of|starting|beginning|effective|dated)\s+)"
)
ROLE_NOUNS: Final = (
    r"CEO|CFO|COO|CTO|CIO|CMO|President|president|Chairman|chairman|Chairwoman|chairwoman|Chair|chair|"
    r"Founder|founder|co-founder|Co-founder|Co-Founder|Director|director|Executive|executive|Officer|officer|"
    r"Chief|chief|boss|head|Head|analyst|Analyst|analysts|economist|strategist|Strategist|spokesperson|"
    r"spokesman|spokeswoman|investor|Investor|Senator|Sen\.|Rep\.|Representative|Secretary|Governor|Gov\.|"
    r"Judge|judge|Justice|Commissioner|commissioner|Minister|minister|Mayor|lawyer|attorney|partner|Partner"
)
EXEC_TITLES: Final = re.compile(
    r"\b(?:CEO|CFO|COO|CTO|CIO|CMO|[Pp]resident|[Cc]hair(?:man|woman)?|[Ff]ounder|co-founder|[Dd]irector|"
    r"[Ee]xecutive|[Oo]fficer|[Cc]hief|boss|[Hh]ead|EVP|SVP|VP)\b"
)
_ROLE_BEFORE: Final = re.compile(rf"(?:\b(?:{ROLE_NOUNS}))\s*,?\s*$")
_NON_PERSON_LABELS: Final = frozenset({"ORG", "PRODUCT", "GPE", "LOC", "FAC", "NORP", "WORK_OF_ART", "EVENT"})
_NOT_PEOPLE: Final = frozenset({"recently", "the year", "a holiday", "the quarter", "the fiscal year"})
_SPEECH_AFTER: Final = re.compile(
    r"^\s*,?\s*(?:said|says|told|wrote|writes|added|adds|noted|notes|stated|explained|commented|argued|warned|"
    r"predicted|expects|believes|thinks)\b"
)
_ROLE_AFTER: Final = re.compile(r"\s+(?:CEO|CFO|COO|CTO|Chairman|chief|Chief|President|executives?|boss)\b")
_SENT_START: Final = re.compile(r"(?:^|[.!?:]\s+|\n\s*|^[\"“‘(\[]\s*)$")
_DOUBLE_DET: Final = re.compile(r"\b(its|their|our|his|her|the|this|that|a|an|The|Its|Their|Our)\s+the\s+")
_WS: Final = re.compile(r"[ \t]{2,}")
# a placeholder glued to the next word ("2025Principal" → "the yearthe company"): a space
_GLUED_PLACEHOLDER: Final = re.compile(r"\b(the year|recently|the quarter)(?=[A-Za-z])")
# a name next to its ticker: "Apple Inc. AAPL" → "the company the company" → "the company"
_SAME_COMPANY: Final = re.compile(r"\b([Tt]he company)(?:[\s.·:\-]+the company\b)+")
_SPACE_PUNCT: Final = re.compile(r"\s+([,.;:!?)\]])")
_OPEN_SPACE: Final = re.compile(r"([(\[])\s+")
_EMPTY_PARENS: Final = re.compile(r"\(\s*[,;]?\s*\)")
_CAP_WORD: Final = re.compile(r"(?<![A-Za-z])(?P<w>[A-Z][A-Za-z]+)(?:['’]s)?(?![A-Za-z])")
_SEP_RUN: Final = re.compile(r"\s*([;|•])(?:\s*[;|•])+\s*")


def caps_ratio(text: str) -> float:
    """Share of upper-case letters among the letters of ``text`` (CJK characters count as letters)."""
    letters = [ch for ch in text if ch.isalpha()]
    return sum(ch.isupper() for ch in letters) / max(len(letters), 1)


def _cap(word: str, before: str) -> str:
    return word[:1].upper() + word[1:] if _SENT_START.search(before) else word


def _tidy(text: str) -> str:
    out = _GLUED_PLACEHOLDER.sub(r"\1 ", text)
    out = _SAME_COMPANY.sub(r"\1", out)
    out = _DOUBLE_DET.sub(r"\1 ", out)
    out = _EMPTY_PARENS.sub("", out)
    out = _SPACE_PUNCT.sub(r"\1", out)
    out = _OPEN_SPACE.sub(r"\1", out)
    out = _WS.sub(" ", out)
    return out.strip(" ,;-–—")


@dataclass(frozen=True)
class AliasConfig:
    legal_suffixes: tuple[str, ...]
    common_words: frozenset[str]
    bare_ticker_stoplist: frozenset[str]
    companies: Mapping[str, Mapping[str, tuple[str, ...]]]
    person_names: frozenset[str] = frozenset()


@functools.cache
def _load_alias_config(path: Path, mtime_ns: int) -> AliasConfig:
    raw = load_yaml(path)

    def words(values: Iterable[object], where: str) -> tuple[str, ...]:
        """Every entry must be a string: YAML reads a bare ON / NO / YES as a boolean."""
        out = tuple(values)
        bad = [v for v in out if not isinstance(v, str)]
        if bad:
            raise ValueError(f"{path}: {where} has non-string entries {bad}; quote them")
        return tuple(str(v) for v in out)

    comps: dict[str, dict[str, tuple[str, ...]]] = {}
    for ticker, spec in (raw.get("companies") or {}).items():
        (key,) = words([ticker], "companies")
        spec = spec or {}
        comps[key] = {
            "names": words(spec.get("names", []), f"companies.{key}.names"),
            "tickers": words(spec.get("tickers", []), f"companies.{key}.tickers"),
        }
    return AliasConfig(
        legal_suffixes=words(raw["legal_suffixes"], "legal_suffixes"),
        common_words=frozenset(words(raw["common_words"], "common_words")),
        bare_ticker_stoplist=frozenset(words(raw["bare_ticker_stoplist"], "bare_ticker_stoplist")),
        companies=comps,
        person_names=frozenset(words(raw.get("person_names", []), "person_names")),
    )


def load_alias_config(path: Path = ALIASES_PATH) -> AliasConfig:
    return _load_alias_config(path, path.stat().st_mtime_ns)


def normalize_ticker(t: str) -> str:
    return t.strip().upper().replace(".", "-").replace("/", "-")


_CLASS: Final = re.compile(r"\s*\((?:Class|Series)\s+[A-Z0-9]+\)\s*$|\s+(?:Class|Series)\s+[A-Z0-9]+$")
_PAREN_TAIL: Final = re.compile(r"^(?P<base>.+?)\s*\((?P<head>The|Eli|[A-Z][a-z]+)\)\s*$")


def name_variants(name: str, cfg: AliasConfig) -> list[str]:
    """Alias phrases derived from an ATOM name (``configs/aliases.yaml`` header, item 1)."""
    base = _CLASS.sub("", name.strip()).strip()
    out: list[str] = []
    m = _PAREN_TAIL.match(base)
    stems = [f"{m.group('head')} {m.group('base')}", m.group("base")] if m else [base]
    suffix = re.compile(
        r"(?:,?\s+(?:"
        + "|".join(re.escape(s).rstrip(r"\.") + r"\.?" for s in cfg.legal_suffixes)
        + r"))+\s*$"
    )
    for stem in stems:
        core = suffix.sub("", stem).strip().rstrip(",")
        if core.startswith("The ") and len(core.split()) > 1:
            out += [core, core[4:]]
        else:
            out.append(core)
    words = out[-1].split()
    for n in range(len(words) - 1, 1, -1):
        out.append(" ".join(words[:n]))
    first = words[0] if words else ""
    if len(words) > 1 and len(re.sub(r"[^A-Za-z]", "", first)) >= 4 and first not in cfg.common_words:
        out.append(first)
    return [o for o in dict.fromkeys(out) if o]


@dataclass(frozen=True)
class CompanyAliases:
    company_id: int
    names: tuple[str, ...]  # longest first
    tickers: tuple[str, ...]  # normalized (class separator "-")


def build_aliases(
    companies: pd.DataFrame,
    extra_tickers: Iterable[tuple[int, str]] = (),
    cfg: AliasConfig | None = None,
) -> dict[int, CompanyAliases]:
    """Alias sets per company_id. ``companies``: symbol_id, company_id, ticker, name (NA-01).
    ``extra_tickers``: (company_id, ticker) from ATOM ref.symbol_ticker and the NA-02 vendor aliases."""
    cfg = load_alias_config() if cfg is None else cfg
    names: dict[int, list[str]] = {}
    tickers: dict[int, list[str]] = {}
    by_ticker = {
        normalize_ticker(str(t)): int(c)
        for t, c in zip(companies["ticker"], companies["company_id"], strict=True)
    }
    for cid, name, ticker in zip(
        companies["company_id"], companies["name"], companies["ticker"], strict=True
    ):
        names.setdefault(int(cid), []).extend(name_variants(str(name), cfg))
        tickers.setdefault(int(cid), []).append(normalize_ticker(str(ticker)))
    for cid, t in extra_tickers:
        tickers.setdefault(int(cid), []).append(normalize_ticker(t))
    for key, spec in cfg.companies.items():
        cid = by_ticker.get(normalize_ticker(key))
        if cid is None:
            continue  # a curated company outside this universe
        names.setdefault(cid, []).extend(spec["names"])
        tickers.setdefault(cid, []).extend(normalize_ticker(t) for t in spec["tickers"])
    out = {}
    for cid in sorted(names):
        ns = sorted(dict.fromkeys(n for n in names[cid] if n), key=lambda s: (-len(s), s))
        ts = sorted(dict.fromkeys(tickers.get(cid, [])), key=lambda s: (-len(s), s))
        out[cid] = CompanyAliases(cid, tuple(ns), tuple(ts))
    return out


def phrase_regex(phrase: str) -> str:
    """Words of ``phrase`` separated by any run of spaces or hyphens ("Coca-Cola" ~ "Coca Cola"); a period may
    be followed by a space ("J.M. Smucker" ~ "J. M. Smucker")."""
    parts = [p for p in re.split(r"[\s\-–]+", phrase.strip()) if p]
    out = ""
    for i, p in enumerate(parts):
        if i:
            out += r"[\s\-–]*"  # also written together: "MolsonCoors", "HomeDepot"
        if p in ("&", "and"):
            out += r"(?:&|and)"  # "Church & Dwight" ~ "Church and Dwight"
            continue
        out += re.escape(p).replace(r"\.", r"\.\s*") if p.endswith(".") and len(p) > 1 else re.escape(p)
    return re.sub("['’]", "['’]", out.replace(r"\.\s*\.", r"\."))


_LOWER: Final = re.compile(r"(?<![A-Za-z])[a-z]{2,}(?![A-Za-z])")


def lowercase_vocabulary(texts: Iterable[str], min_count: int) -> frozenset[str]:
    """Words written in lower case at least ``min_count`` times in ``texts``: ordinary English words."""
    counts: dict[str, int] = {}
    for t in texts:
        for w in _LOWER.findall(t):
            counts[w] = counts.get(w, 0) + 1
    return frozenset(w for w, n in counts.items() if n >= min_count)


_WORD: Final = re.compile(r"[A-Za-z][A-Za-z&]*(?:['’][A-Za-z]+)?")


def distinctive_words(phrases: Iterable[str], cfg: AliasConfig) -> set[str]:
    """Words of 4+ letters of alias phrases that are neither common words nor legal suffixes ("Grumman")."""
    skip = cfg.common_words | {s.rstrip(".") for s in cfg.legal_suffixes}
    out = set()
    for phrase in phrases:
        for w in _WORD.findall(phrase):
            core = re.sub(r"['’]s$", "", w)
            if (
                len(re.sub(r"[^A-Za-z]", "", core)) >= 4
                and core not in skip
                and core.capitalize() not in skip
            ):
                out.add(core)
    return out


def split_names(a: CompanyAliases, cfg: AliasConfig) -> tuple[list[str], list[str]]:
    """(case-insensitive patterns, case-sensitive patterns) of a company: phrases and distinctive words match
    in any case; a one-word name that is a common word ("Target", "Visa") only as written or in capitals."""
    loose, strict = set(distinctive_words(a.names, cfg)), set()
    for n in a.names:
        if len(re.split(r"[\s\-–]+", n.strip())) == 1 and (n in cfg.common_words or len(n) < 4):
            strict.update({n, n.upper(), n.capitalize()})
        else:
            loose.add(n)
    order = lambda v: (-len(v), v)  # noqa: E731
    return sorted(loose, key=order), sorted(strict, key=order)


CJK: Final = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af"
_HANGUL: Final = re.compile("[\uac00-\ud7af]")
_KANA_TAIL: Final = re.compile(r"[\u30a0-\u30ff・ー]+(?:社)?$")
# Chinese verbs and function words before a company name ("美銀證券維持施貴寶", "我們對家得寶", "爲什麼快扣")
_CJK_LEAD: Final = re.compile(
    r"^.*(?:維持|维持|上調|上调|下調|下调|首予|調整了|调整了|增持了|減持了|减持了|收購了|收购了|批准了|撤銷|撤销|"
    r"速覽|速览|查看|反映了|認爲|認為|认为|關於|关于|對於|对于|什麼|什么|企業|企业|購買|购买|通過|通过|仍然|持有|"
    r"買入|买入|賣出|卖出|[對对的了在與与和及將将讓让把被由從从向爲為为是])"
)
_CJK_SUFFIX: Final = re.compile(
    r"(?:股票|股份有限公司|有限公司|集團公司|集团公司|公司|股份|集團|集团|控股|科技|技術|技术|通信|通訊|通讯|能源|銀行|"
    r"银行|電氣|电气|保險|保险|實驗室|实验室|電腦|电脑|社|・インク|・コーポレーション|・グループ|・カンパニーズ|"
    r"・ホールディングス|・インコーポレイテッド)$"
)
_CJK_GENERIC: Final = frozenset(
    (  # noqa: SIM905
        "公司 股份 集團 集团 控股 科技 技術 技术 通信 通訊 通讯 能源 銀行 银行 電氣 电气 保險 保险 石油 "
        "資源 资源 美國 美国 中國 中国 國際 国际 股票 ホールディングス グループ 그룹 컴퍼니 코퍼레이션 "
        "홀딩스 인크 뱅코프 자원 에너지 주식"
    ).split()
)
CJK_NAME_MAX_LEN: Final = 20  # katakana names are long: エスティ・ローダー・カンパニーズ


def _cjk_variants(run: str) -> list[str]:
    """Name variants in the CJK text right before a company's ticker: Korean, the last word; Japanese, the
    final katakana run; Chinese, the text after the last verb / function word; corporate suffixes removed."""
    run = run.strip().rstrip("的の의")
    last = run.split()[-1] if run.split() else ""
    if _HANGUL.search(last):
        name = last
    elif m := _KANA_TAIL.search(last):
        name = m.group(0)
    else:
        name = _CJK_LEAD.sub("", last)
    out = [name, last] if len(last) <= 5 and last != name else [name]  # "奧的斯" holds a function word
    while (stem := _CJK_SUFFIX.sub("", out[-1])) != out[-1]:
        out.append(stem)
    names = [v.strip("・·") for v in out]
    return [v for v in names if 2 <= len(v) <= CJK_NAME_MAX_LEN and v not in _CJK_GENERIC]


def cjk_company_names(
    articles: pd.DataFrame, aliases: Mapping[int, CompanyAliases]
) -> dict[int, tuple[str, ...]]:
    """Chinese, Japanese and Korean names of each company (second NA-04 verification): the CJK words
    right before its own ticker in parentheses in the unmasked texts ("迪爾股份（紐交所：DE）",
    "アクセンチュア（NYSE：ACN）"; ``articles``: company_id, title, snippet). A Korean candidate must be seen
    twice (its words end in verb endings as often as in names)."""
    counts: dict[int, dict[str, int]] = {}
    patterns: dict[int, re.Pattern[str]] = {}
    has_cjk = re.compile(f"[{CJK}]")
    rows = zip(articles["company_id"], articles["title"], articles["snippet"], strict=True)
    for cid, title, snippet in rows:
        text = f"{title} {snippet}"
        a = aliases.get(int(cid))
        if a is None or not a.tickers or not has_cjk.search(text):
            continue
        rx = patterns.get(int(cid))
        if rx is None:
            tick = "|".join(ticker_regex(t) for t in a.tickers)
            rx = re.compile(
                rf"([{CJK}・·\s]{{2,30}}?)\s*[（(]\s*(?:[^()（）:：\n]{{0,16}}[:：]\s*)?\$?(?:{tick})"
                rf"(?:\.[A-Z]{{1,2}}|\s+US)?\s*[)）]"
            )
            patterns[int(cid)] = rx
        for m in rx.finditer(text):
            for v in _cjk_variants(m.group(1)):
                counts.setdefault(int(cid), {})[v] = counts.setdefault(int(cid), {}).get(v, 0) + 1
    out = {}
    for cid, c in counts.items():
        names = [v for v, n in c.items() if n >= 2 or not _HANGUL.search(v)]
        if names:
            out[cid] = tuple(sorted(names, key=lambda s: (-len(s), s)))
    return out


# Chinese transliterations of Western names: "薩姆·阿爾特曼" (Sam Altman), "丹·艾夫斯"; up to two characters
# before the dot and four after, none of them a title or function character (Chinese has no spaces: "分析師
# 丹·艾夫斯卻" keeps "分析師" and "卻")
_NOT_NAME_CHAR: Final = r"(?![師师官長长家員员者席總总的了在和是與与對对卻却說说稱称表將将])"
CJK_PERSON: Final = re.compile(
    rf"(?:{_NOT_NAME_CHAR}[\u4e00-\u9fff]){{1,2}}[·•](?:{_NOT_NAME_CHAR}[\u4e00-\u9fff]){{1,4}}"
)


def ticker_regex(t: str) -> str:
    """A normalized ticker with any class separator: BRK-B matches BRK.B, BRK/B, BRK-B, BRKB is not."""
    return r"[.\-/]".join(re.escape(p) for p in t.split("-"))


@dataclass
class CompanyPatterns:
    names: re.Pattern[str] | None
    names_strict: re.Pattern[str] | None
    stock_ticker: re.Pattern[str] | None
    paren_ticker: re.Pattern[str] | None
    prefixed_ticker: re.Pattern[str] | None
    bare_ticker: re.Pattern[str] | None
    wide_ticker: re.Pattern[str] | None = None
    caps_ticker: re.Pattern[str] | None = None
    cjk_names: re.Pattern[str] | None = None
    truncated: re.Pattern[str] | None = None
    glued_names: re.Pattern[str] | None = None


Candidate = tuple[int, int, list[str]]  # a PERSON entity: start, end, its words without a possessive


@dataclass
class MaskCounts:
    names: int = 0
    tickers: int = 0
    dates: int = 0
    persons: int = 0

    def add(self, other: MaskCounts) -> None:
        self.names += other.names
        self.tickers += other.tickers
        self.dates += other.dates
        self.persons += other.persons


_DATELINE: Final = re.compile(
    rf"^\s*[A-Z][A-Za-z .'\-]{{1,40}}(?:,\s*[A-Z][A-Za-z.]{{1,15}}(?:\s+[A-Z][A-Za-z.]{{1,15}})?)?\s*,?\s*"
    rf"(?:{WEEKDAY},?\s+)?{MONTH_ANY}\s+{DAY},?\s+{YEAR_RE}\s*(?:/\s*[A-Za-z\- ]{{2,40}}\s*/)?\s*[-–—]+\s*"
)
_WIRE_DATELINE: Final = re.compile(
    r"^\s*[A-Z][A-Z .'\-]{2,40}(?:,\s*[A-Z][A-Za-z.]{1,15})?\s*\((?:Reuters|AP|Bloomberg|Dow Jones|AFP|"
    r"Business Wire|BUSINESS WIRE|PRNewswire|GLOBE NEWSWIRE)\)\s*[-–—]+\s*"
)
_NBSP: Final = re.compile(r"[\u00a0\u2007\u202f]")
_EMAIL_URL: Final = re.compile(r"\S+@\S+\.[A-Za-z]{2,}|\bhttps?://\S+|\bwww\.\S+")  # domains name companies
_ISIN: Final = re.compile(r"\s*\(?\bISIN\b:?\s*[A-Z]{2}[A-Z0-9]{9}\d\)?|\b[A-Z]{2}[A-Z0-9]{9}\d\b")

_I: Final = "(?i)"
_DATE_RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(p[len(_I) :], re.IGNORECASE) if p.startswith(_I) else re.compile(p), r)
    for p, r in (
        (r"\b(?:Black|Cyber|Good)\s+(?:Friday|Monday)\b", "a holiday"),
        (rf"{YEAR_RE}\s?[年년]\s?(?:{CJK_DAY}|\d{{1,2}}\s?[月월])", RECENTLY),
        (rf"(?<!\d){CJK_DAY}", RECENTLY),
        (rf"{CJK_YEAR}\s?(?:{CJK_QUARTER}|Q[1-4](?![A-Za-z0-9]))", QUARTER),
        (rf"{CJK_YEAR}\s?{CJK_HALF}", HALF_YEAR),
        (CJK_YEAR, YEAR),
        (rf"[財财]?(?:年度)?{CJK_QUARTER}", QUARTER),
        (CJK_HALF, HALF_YEAR),
        (r"(?<!\d)\d{1,2}\s?[月월](?:份)?", RECENTLY),
        (r"(?<!\d)\d{1,2}\s?[日号일](?![本元])", RECENTLY),
        (rf"[（(]?\s?{CJK_WEEKDAY}\s?[）)]?", RECENTLY),
        (
            rf"{_I}{F_PREP}?\b\d{{1,2}}\.?\s+(?:de\s+)?(?:{F_MONTH}|{F_MONTH_DAY_ONLY})\b(?:\s+(?:de\s+)?{YEAR_RE})?",
            RECENTLY,
        ),
        (rf"{_I}{F_PREP}?\b(?:{F_MONTH}|{F_MONTH_DAY_ONLY})\s+(?:de\s+)?{YEAR_RE}", RECENTLY),
        (rf"{_I}{F_PREP}?\b{F_MONTH}\b", RECENTLY),
        (rf"{_I}{F_PREP}?\b{F_WEEKDAY}\b", RECENTLY),
        (r"\bam\s+\d{1,2}\.(?=[\s,;]|$)", RECENTLY),
        (
            rf"{_I}\b(?:im\s+)?(?:[1-4]\.\s*Quartal|[1-4](?:er|e|º|°)?\s+trimestre|T[1-4]\s*{APOS}?(?:{YEAR_RE}|\d{{2}}))\b",
            QUARTER,
        ),
        # NA-04 revision 3: ordinal quarters and halves written out, Spanish / Portuguese "3T25", bare T1–T4
        # after a period word, Korean quarters and halves
        (rf"{_I}(?<![A-Za-z\u00C0-\u024F]){ORDINAL_X}\s+(?:trimestre|quartals?|kwartaal)\b", QUARTER),
        (
            rf"{_I}(?<![A-Za-z\u00C0-\u024F]){ORDINAL_X_HALF}\s+(?:semestre|halbjahr(?:e?s)?|halfjaar)\b",
            HALF_YEAR,
        ),
        (rf"(?<![A-Za-z0-9])[1-4]T\s?{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])", QUARTER),
        (rf"(?:{T_CONTEXT})T[1-4](?![A-Za-z0-9/])", QUARTER),
        (r"[1-4１-４]\s?분기", QUARTER),
        (r"[상하]반기", HALF_YEAR),
        (rf"{PREP}?\b\d{{4}}-\d{{2}}-\d{{2}}\b", RECENTLY),
        (  # 2025/08/08, 2025/08
            rf"(?<![0-9.]){YEAR_RE}[/.](?:0?[1-9]|1[0-2])(?:[/.](?:[12]\d|3[01]|0?[1-9]))?(?![\d/])",
            RECENTLY,
        ),
        (rf"{PREP}?\b\d{{1,2}}/\d{{1,2}}/(?:\d{{4}}|\d{{2}})\b", RECENTLY),
        (rf"{PREP}?\b\d{{1,2}}/\d{{1,2}}/(?:{YEAR_RE}|\d{{2}})(?!\d)", RECENTLY),  # glued: "17/09/2025POR"
        (rf"{PREP}?\b\d{{1,2}}\.\d{{1,2}}\.(?:\d{{4}}|\d{{2}})\b", RECENTLY),
        (r"(?<![\d/.$,])\b(?:1[0-2]|0?[1-9])/(?:1[3-9]|2\d|3[01])\b(?![\d/%])", RECENTLY),
        (r"(?<![\d/.$,])\b(?:0[1-9]/(?:[0-2]\d|3[01])|1[0-2]/0[1-9])\b(?![\d/%])", RECENTLY),  # zero padding
        (rf"{PREP}\b(?:1[0-2]|0?[1-9])/(?:[12]?\d|3[01])\b(?![\d/%])", RECENTLY),
        # day first, unambiguous when the day is 13 or more ("depuis 21/04", "31/7"); not "24/7"
        (r"(?<![\d/.$,])\b(?!24/(?:7|5|365)\b)(?:1[3-9]|2\d|3[01])/(?:0?[1-9]|1[0-2])\b(?![\d/%])", RECENTLY),
        (r"(?<!\d)20[0-4]\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)", RECENTLY),  # "dltr-20250909"
        (rf"{PREP}?\b(?:{WEEKDAY},?\s+)?{MONTH_ANY}\s+{DAY_RANGE}(?!\d)(?:,?\s*{YEAR_RE}\b)?", RECENTLY),
        (
            rf"{PREP}?\b(?:{WEEKDAY},?\s+)?(?:the\s+)?{DAY_RANGE}\s+(?:of\s+)?{MONTH_ANY}(?:,?\s*{YEAR_RE}\b)?",
            RECENTLY,
        ),
        # a year and a period glued together: FY2025Q2, 2025Q2, 2025-Q2, 2025H1
        (rf"{_I}(?<![A-Za-z0-9])FY\s?{APOS}?(?:{YEAR_RE}|\d{{2}})[\s\-/]?Q[1-4](?![A-Za-z0-9])", QUARTER),
        (rf"{_I}(?<![A-Za-z0-9]){YEAR_RE}[\s\-/]?Q[1-4](?![A-Za-z0-9])", QUARTER),
        (rf"{_I}(?<![A-Za-z0-9]){YEAR_RE}[\s\-/]?H[12](?![A-Za-z0-9])", HALF_YEAR),
        (
            rf"{_I}(?<![A-Za-z])(?:the\s+)?(?:first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+(?:fiscal\s+)?quarter\s+(?:of\s+)?(?:fiscal\s+(?:year\s+)?)?(?:FY\s?)?{APOS}?(?:{YEAR_RE}|\d{{2}})\b",
            QUARTER,
        ),
        (
            rf"{_I}(?<![A-Za-z])(?:the\s+)?(?:first|second|1st|2nd)[\s-]+half\s+(?:of\s+)?(?:the\s+)?(?:fiscal\s+)?(?:year\s+)?{APOS}?(?:{YEAR_RE}|\d{{2}})\b",
            HALF_YEAR,
        ),
        (rf"{_I}(?<![A-Za-z0-9])[12]H[\s\-/'’‘]*{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])", HALF_YEAR),
        # ASCII boundaries: CJK characters are word characters ("年Q2", "Q2财报")
        (
            rf"{_I}(?<![A-Za-z0-9])(?:fiscal\s+)?Q[1-4][\s\-/'’‘]*(?:of\s+)?(?:fiscal\s+(?:year\s+)?)?"
            rf"(?:FY\s?|CY\s?|F)?{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])",
            QUARTER,
        ),
        (
            rf"{_I}(?<![A-Za-z0-9])(?:fiscal\s+)?[1-4]Q[\s\-/'’‘]*(?:FY|CY)?{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])",
            QUARTER,
        ),
        (
            rf"(?<![A-Za-z0-9])(?:fiscal\s+)?[Hh][12][\s\-/'’‘]*(?:FY|CY)?{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])",
            HALF_YEAR,
        ),
        (rf"{_I}(?<![A-Za-z0-9])(?:fiscal\s+)?(?:Q[1-4]|[1-4]Q)(?![A-Za-z0-9])", QUARTER),
        (  # a bare half-year label, case-sensitive; not hydrogen ("H2 production"), "H1-B" or "</h1>"
            r"(?<![A-Za-z0-9$/<])(?<!green )(?<!Green )(?<!blue )(?:H[12]|[12]H)"
            r"(?![A-Za-z0-9>]|-[A-Z]|\s+(?:[Pp]roduction|[Ff]uel|[Tt]imeframe))",
            HALF_YEAR,
        ),
        (rf"{_I}(?<![A-Za-z])(?:first|second|third|fourth|1st|2nd|3rd|4th)-quarter\b", "quarterly"),
        (
            rf"{_I}(?<![A-Za-z])(?:the\s+)?(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+(?:fiscal\s+)?quarter\b",
            QUARTER,
        ),
        (rf"{_I}(?<![A-Za-z])(?:first|second|1st|2nd)-half\b", "half-year"),
        (
            rf"{_I}(?<![A-Za-z])(?:the\s+)?(?:first|second|1st|2nd)\s+half\s+of\s+(?:the\s+)?(?:fiscal\s+)?year\b",
            HALF_YEAR,
        ),
        (rf"{_I}(?<![A-Za-z])(?:the\s+)?(?:first|second|1st|2nd)\s+(?:fiscal\s+)?half\b", HALF_YEAR),
        (rf"\b(?:the\s+)?fiscal\s+(?:year\s+)?{APOS}?(?:{YEAR_RE}|\d{{2}})\b", FISCAL_YEAR),
        (rf"{_I}(?<![A-Za-z0-9])FY\s?{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])", FISCAL_YEAR),
        (rf"{_I}(?<![A-Za-z0-9])CY\s?{APOS}?(?:{YEAR_RE}|\d{{2}})(?![A-Za-z0-9])", YEAR),
        (rf"(?<![A-Za-z0-9'’‘]){APOS}[12]\d(?![A-Za-z0-9%'’])", YEAR),  # "Raises '25 View", "Feb 18 '25"
        (rf"\b{YEAR_RE}\s*[-–/]\s*(?:{YEAR_RE}|\d{{2}})\b", "the period"),
        (rf"{PREP}?\b(?:early|mid|late)[\s-]+{MONTH_ANY}(?:\s+(?:of\s+)?{YEAR_RE}\b)?", RECENTLY),
        (rf"{PREP}?\b{MONTH_ANY}\s+(?:of\s+)?{YEAR_RE}", RECENTLY),
        (rf"{_I}\bfull[\s-]year\s+{YEAR_RE}\b", "full-year"),
        (rf"\b(?:early|mid|late)[\s-]+{YEAR_RE}\b", YEAR),
        (rf"\bsince\s+{YEAR_RE}\b", "for years"),
        # a year glued to letters ("EHA2025") or after CJK ("於2025") is a year too
        (rf"(?<=[A-Za-z\u00C0-\u024F]){_NOT_CURRENCY}{YEAR_RE}(?!\d|[%,.]\d|\s?%)", " " + YEAR),
        (rf"(?<!\d[.,])(?<![0-9_$€£¥])(?<!Russell\s){YEAR_RE}(?!\d|[%,.]\d|\s?%)", YEAR),
        (rf"{PREP}?\b(?:early|mid|late)[\s-]+{MONTH}\b", RECENTLY),
        (rf"(?:{PREP}|\b(?:last|this|next|early|late)\s+){MONTH}\b", RECENTLY),
        (
            r"\b(?:January|February|March|April|June|July|August|September|October|November|December|JANUARY|"
            r"FEBRUARY|MARCH|APRIL|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b",
            "recent",
        ),
        (rf"(?:{PREP})?(?<![A-Za-z]){MON}(?![A-Za-z0-9])", RECENTLY),  # a lone "Aug.": "on Aug.", "(Sept.)"
        (rf"{_I}(?:{PREP})?\b{WEEKDAY}\s+(?:night|morning|afternoon|evening)\b", RECENTLY),
        (rf"{_I}(?:\bon\s+)?\b{WEEKDAY}(?:'s|’s)", "the recent"),
        (rf"{_I}(?:{PREP}|\b(?:last|this|next|early|late)\s+){WEEKDAY}s?\b", RECENTLY),
        (rf"{_I}\b{WEEKDAY}s?\b", RECENTLY),
        # remnants of a day range or a period whose other end was masked: "recently-18", "17–recently",
        # "the quarter-25"
        (r"(?<=[Rr]ecently)\s?[–\-]\s?(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?(?![\d.,%:/A-Za-z])", ""),
        (r"(?<![\d.,])\b(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?\s?[–\-]\s?(?=[Rr]ecently\b)", ""),
        (
            r"(?:(?<=the quarter)|(?<=the year)|(?<=fiscal year)|(?<=half-year))"
            r"\s?[\-–'’‘/]\s?\d{2}(?![\d%]|[.,]\d)",
            "",
        ),  # "the fiscal year/27" (FY26/27); not "2-year/10-year"
        (
            r"(?:(?<=[Rr]ecent)|(?<=[Rr]ecently))['’‘]\d{2}(?![\d%]|[.,]\d)",
            "",
        ),  # "September’25" -> "recent’25"
    )
)


class Masker:
    """Masks title / snippet text of one company's articles (module docstring)."""

    def __init__(
        self,
        aliases: Mapping[int, CompanyAliases],
        cfg: AliasConfig | None = None,
        nlp: Any = None,
        vocabulary: frozenset[str] = frozenset(),
        surnames: frozenset[str] | None = None,
        cjk_names: Mapping[int, Sequence[str]] | None = None,
    ) -> None:
        """``vocabulary``: ordinary lower-case words (``lowercase_vocabulary``); a PERSON entity made only of
        such words ("Balance Sheet", "Soar") is not a name unless a role noun or a speech verb frames it.
        ``surnames``: corpus surnames masked wherever they appear; None derives them in ``mask_texts``.
        ``cjk_names``: Chinese, Japanese and Korean company names (``cjk_company_names``)."""
        self.cfg = load_alias_config() if cfg is None else cfg
        self.cjk_names: Mapping[int, Sequence[str]] = cjk_names or {}
        self.vocabulary = vocabulary
        self._derive_surnames = surnames is None
        self.surnames: frozenset[str] = frozenset() if surnames is None else surnames
        self.aliases = aliases
        self._nlp = nlp
        self._patterns: dict[int, CompanyPatterns] = {}
        every = {n.lower() for a in aliases.values() for n in a.names} | {
            t.lower() for a in aliases.values() for t in a.tickers
        }
        self._all_names = frozenset(every)
        self._alias_words = frozenset(
            w.lower() for a in aliases.values() for n in a.names for w in re.findall(r"[A-Za-z]+", n)
        )
        self._detector = load_detector()

    # --- company -----------------------------------------------------------------------------------

    def patterns(self, company_id: int) -> CompanyPatterns:
        pat = self._patterns.get(company_id)
        if pat is not None:
            return pat
        a = self.aliases.get(company_id)
        if a is None:
            pat = CompanyPatterns(None, None, None, None, None, None)
        else:
            loose, strict = split_names(a, self.cfg)
            suffix = "|".join(re.escape(s).rstrip(r"\.") + r"\.?" for s in self.cfg.legal_suffixes)

            def names_re(words: list[str], flags: int) -> re.Pattern[str] | None:
                if not words:
                    return None
                alt = "|".join(phrase_regex(v) for v in words)
                return re.compile(
                    rf"(?<![A-Za-z0-9&])(?:[Tt]he\s+)?(?:{alt})(?:,?\s+(?:{suffix}))*(?![A-Za-z0-9&])", flags
                )

            tick = "|".join(ticker_regex(t) for t in a.tickers)
            bare = [t for t in a.tickers if len(t) >= 2 and t not in self.cfg.bare_ticker_stoplist]
            stop = [t for t in a.tickers if t in self.cfg.bare_ticker_stoplist or len(t) < 2]
            caps = [t for t in stop if len(t) >= 2]
            firsts = sorted({w[0] for n in a.names if len(w := n.split()) > 1 and len(w[0]) >= 4})
            # a capitalized name glued to the previous word ("Key TakeawaysHumana"): as written, 5+ letters
            glued = sorted(
                {n for n in a.names if n[:1].isupper() and len(n) >= 5}, key=lambda s: (-len(s), s)
            )
            exch = rf"(?:{EXCH_PREFIX})?\$?"
            bare_alts = []  # bare tickers; a stoplisted (English-word) ticker only as a possessive ("NOW's")
            if bare:
                bare_alts.append(
                    rf"{BARE_BEFORE}(?:{'|'.join(map(ticker_regex, bare))}){TICKER_SUFFIX}"
                    rf"(?![A-Za-z&]|/[A-Z]{{1,2}}\b)"  # "ABBV-400", "AAPL-2.96%" are the company
                )
            if stop:
                bare_alts.append(rf"(?<![A-Za-z0-9$&.\-/])(?:{'|'.join(map(ticker_regex, stop))})(?=['’]s\b)")
            pat = CompanyPatterns(
                names=names_re(loose, re.IGNORECASE),
                names_strict=names_re(strict, 0),
                stock_ticker=re.compile(
                    rf"(?<![A-Za-z0-9$&.\-/])(?:{tick})(?=\s+(?:[Ss]tock|[Ss]hares|[Oo]ptions)\b(?!\s+[Mm]arket))"
                )
                if tick
                else None,
                paren_ticker=re.compile(
                    rf"\s*\(\s*{exch}(?:{tick})(?:\.[A-Z]{{1,2}})?(?!-\d)(?=[\s,;:)–—.\-+/]|$)[^()]{{0,40}}(?:\)|$)"
                )
                if tick
                else None,
                prefixed_ticker=re.compile(rf"(?:{EXCH_PREFIX}\$?|\$)(?:{tick}){TICKER_SUFFIX}(?![A-Za-z])")
                if tick
                else None,
                bare_ticker=re.compile("|".join(bare_alts)) if bare_alts else None,
                wide_ticker=re.compile(
                    rf"\s*[（(]\s*[^()（）:：\n]{{0,16}}[:：]\s*\$?(?:{tick})(?:\.[A-Z]{{1,2}})?\s*[)）]"
                    rf"|\s*[（(]\s*(?:{tick})(?:\.US|\s+U[SNWQA])\s*[)）]"
                )
                if tick
                else None,
                caps_ticker=re.compile(
                    rf"(?<![{LATIN}$&.\-/])(?:{'|'.join(map(ticker_regex, caps))}){TICKER_SUFFIX}"
                    rf"(?![{LATIN}&]|-[{LATIN}])"
                )
                if caps
                else None,
                cjk_names=re.compile("|".join(map(re.escape, self.cjk_names[company_id])))
                if self.cjk_names.get(company_id)
                else None,
                truncated=re.compile(  # a name cut by the vendor at the end of a snippet: "for Warner..."
                    rf"(?<![A-Za-z0-9&])(?:{'|'.join(map(re.escape, firsts))})(?=\s*(?:\.{{2,}}|…)\s*$)"
                )
                if firsts
                else None,
                glued_names=re.compile(
                    rf"(?<=[a-z0-9])(?:{'|'.join(phrase_regex(v) for v in glued)})(?![a-z])"
                )
                if glued
                else None,
            )
        self._patterns[company_id] = pat
        return pat

    def _replace(self, pattern: re.Pattern[str] | None, text: str, word: str) -> tuple[str, int]:
        if pattern is None:
            return text, 0

        def repl(m: re.Match[str]) -> str:
            return _cap(word, text[: m.start()])

        return pattern.subn(repl, text)

    def mask_company(self, text: str, company_id: int) -> tuple[str, MaskCounts]:
        c = MaskCounts()
        pat = self.patterns(company_id)
        for p in (pat.paren_ticker, pat.wide_ticker):
            if p is not None:
                text, n = p.subn("", text)
                c.tickers += n
        for p in (pat.prefixed_ticker, pat.stock_ticker):
            text, n = self._replace(p, text, COMPANY)
            c.tickers += n
        for p in (pat.names, pat.names_strict, pat.cjk_names, pat.truncated, pat.glued_names):
            text, n = self._replace(p, text, COMPANY)
            c.names += n
        text, n = self._replace(pat.bare_ticker, text, COMPANY)
        c.tickers += n
        if pat.caps_ticker is not None:
            text, n = self._mask_caps(pat.caps_ticker, text)
            c.tickers += n
        return text, c

    def _mask_caps(self, pattern: re.Pattern[str], text: str) -> tuple[str, int]:
        """An upper-case stoplisted ticker is the company ("MET earnings per share", "View the latest DASH
        revenue", "MS.N"), except a clock time ("4:30 PM") and IT before an IT noun. In a text mostly in
        capitals only a ticker that is not an ordinary lower-case word ("IR: … ACCELERATES") or that stands in
        a list of tickers ("ALC, KEYS, TOL")."""
        n = 0
        shouting = caps_ratio(text) > 0.6  # the scanner says 0.5: the masker errs on the side of masking

        def repl(m: re.Match[str]) -> str:
            nonlocal n
            word = m.group(0)
            before, after = text[: m.start()], text[m.end() :]
            if (word in ("AM", "PM") and _CLOCK.search(before)) or (word == "IT" and _IT_NOUN.match(after)):
                return word
            listed = bool(
                _LIST_BEFORE.search(before)
                or _LIST_AFTER.match(after)
                or _CUE_AFTER.match(after)
                or _COMPANY_BEFORE.search(before)
            )
            if shouting and word.lower() in self.vocabulary and not listed:
                return word
            n += 1
            return _cap(COMPANY, before)

        return pattern.sub(repl, text), n

    # --- dates -------------------------------------------------------------------------------------

    def mask_lead(self, text: str) -> tuple[str, int]:
        """Step 1: HTML entities decoded ("Microsoft&nbsp;" → "Microsoft "), then datelines, ISIN codes,
        e-mails / URLs, option contracts and quote widgets."""
        text = _NBSP.sub(" ", html.unescape(text))
        total = 0
        for p in (_DATELINE, _WIRE_DATELINE, _WIRE_MID, _ISIN, _EMAIL_URL, _OPTION_CODE, _WIDGET):
            text, n = p.subn("", text)
            total += n
        text, n = _OPTION_TERMS.subn("option", text)
        return text, total + n

    def mask_dates(self, text: str) -> tuple[str, int]:
        """Step 3: dates, weekdays, months, years, fiscal periods."""
        total = 0
        for pattern, word in _DATE_RULES:
            text, n = self._replace(pattern, text, word)
            total += n
        return text, total

    # --- people ------------------------------------------------------------------------------------

    @property
    def nlp(self) -> Any:
        if self._nlp is None:
            self._nlp = load_spacy()
        return self._nlp

    def _persons(self, doc: Any) -> list[Candidate]:
        """PERSON entities that are not a company alias: (start, end, words without a possessive)."""
        out: list[Candidate] = []
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            t = ent.text.strip()
            low = t.lower()
            if not t or low in self._all_names or COMPANY in low or re.search(r"\d", t) or low in _NOT_PEOPLE:
                continue
            words = [w.text for w in ent if w.text not in ("'s", "’s")]
            if not words:
                continue
            after = doc.text[ent.end_char : ent.end_char + 20]
            if len(words) == 1 and _ROLE_AFTER.match(after):
                continue  # "Masimo CEO": an organization before a title, not a person
            out.append((ent.start_char, ent.end_char, words))
        return out

    def _namelike(self, words: Sequence[str]) -> bool:
        return any(w.lower() not in self.vocabulary for w in words)

    def corpus_surnames(
        self,
        candidates: Iterable[Sequence[Candidate]],
        foreign: Sequence[bool] | None = None,
        other_entities: Mapping[str, int] | None = None,
    ) -> frozenset[str]:
        """Last words of multi-word names in English texts seen at least ``SURNAME_MIN_COUNT`` times:
        capitalized, 3+ ASCII letters, not an ordinary lower-case word, not a word of any company alias, and
        tagged inside an organization / product / place entity less than half as often as it ends a name
        ("Powell" from "Jerome Powell"; not "Oppenheimer", a broker spaCy sometimes tags as a person)."""
        counts: dict[str, int] = {}
        for k, cands in enumerate(candidates):
            if foreign is not None and foreign[k]:
                continue
            for _, _, words in cands:
                if len(words) >= 2 and self._namelike(words):
                    last = words[-1]
                    counts[last] = counts.get(last, 0) + 1
        other = other_entities or {}
        return frozenset(
            w
            for w, n in counts.items()
            if n >= SURNAME_MIN_COUNT
            and len(w) >= 3
            and w[:1].isupper()
            and w.isascii()
            and w.isalpha()
            and w.lower() not in self.vocabulary
            and w.lower() not in self._alias_words
            and other.get(w, 0) * 2 < n
        )

    def _person_spans(
        self,
        text: str,
        candidates: Sequence[Candidate],
        surnames: frozenset[str] = frozenset(),
        *,
        foreign: bool = False,
    ) -> list[tuple[int, int]]:
        """Names of two or more words; a one-word name only if it is a known surname (of a longer name in the
        same article, or ``self.surnames`` from the corpus), follows a role noun, or precedes a speech verb
        (title-case headline words such as "Buy" or "Soar" are often tagged PERSON). In a text that looks
        non-English (``foreign``) only names of two or more capitalized words count: the English model tags
        many foreign words as PERSON. Every capitalized occurrence of a known surname is a name too."""
        known = surnames | self.surnames | self.cfg.person_names
        spans: list[tuple[int, int]] = []
        for start, end, words in candidates:
            if foreign:
                if len(words) >= 2 and all(w[:1].isupper() for w in words):
                    spans.append((start, end))
                continue
            framed = bool(_ROLE_BEFORE.search(text[:start]) or _SPEECH_AFTER.match(text[end : end + 30]))
            if framed or (self._namelike(words) and (len(words) >= 2 or words[0] in known)):
                spans.append((start, end))
        for m in _CAP_WORD.finditer(text):  # a surname NER missed: "Elon Musk ... Musk added", "Trump" alone
            name = m.group("w")
            usable = name in self.cfg.person_names or (len(name) >= 3 and name.lower() not in self.vocabulary)
            if name in known and usable and not any(s < m.end() and m.start() < e for s, e in spans):
                spans.append(m.span())
        return sorted(spans)

    def mask_persons(
        self, text: str, candidates: Sequence[Candidate], surnames: frozenset[str] = frozenset()
    ) -> tuple[str, int]:
        spans = self._person_spans(text, candidates, surnames, foreign=self._detector.non_english(text))
        out, pos, n = [], 0, 0
        for start, end in spans:
            if start < pos:
                continue
            before = text[:start]
            if _ROLE_BEFORE.search(before):
                out.append(text[pos:start].rstrip(" ,"))
                out.append("")
            else:
                window = " ".join(
                    [*text[max(0, start - 80) : start].split()[-6:], *text[end : end + 80].split()[:6]]
                )
                word = EXECUTIVE if EXEC_TITLES.search(window) else PERSON
                out.append(text[pos:start])
                out.append(_cap(word, before))
            if text[start:end].endswith(("'s", "’s")) and not _ROLE_BEFORE.search(before):
                out.append(text[end - 2 : end])
            pos = end
            n += 1
        out.append(text[pos:])
        return "".join(out), n

    # --- price talk and price levels ---------------------------------------------------------------

    @staticmethod
    def _relative(label: str, mid: str, old: str, new: str) -> str:
        a, b = float(old.replace(",", "")), float(new.replace(",", ""))
        if a <= 0 or b == a:
            change = "unchanged" if b == a else ""
        else:
            pct = (b / a - 1.0) * 100.0
            change = (
                ("raised slightly" if pct > 0 else "lowered slightly")
                if abs(pct) < 1
                else f"{'raised' if pct > 0 else 'lowered'} by about {round(abs(pct))}%"
            )
        return f"{label}{mid.rstrip()} {change}".rstrip()

    @staticmethod
    def is_price_move(sentence: str) -> bool:
        """A stock / share price move in percent: any subject occurrence whose stretch to the move verb holds
        no fundamental noun ("Earnings Disappoint, Shares Fall 8.3%" is a move; "revenue rose 5%" is not)."""
        if PRICE_MOVE_AFTER.search(sentence):
            return True
        for sm in _MOVE_SUBJECT.finditer(sentence):
            m = PRICE_MOVE.match(sentence, sm.start())
            if m and not _FUNDAMENTAL_SUBJECT.search(m.group("mid") or ""):
                return True
        return False

    @staticmethod
    def is_price_level(sentence: str) -> bool:
        """A share-price level ("boosts stock to $102.89"), not a per-share figure ("per diluted share at
        $0.23") or a dividend."""
        return any(
            not _PER_BEFORE.search(sentence[max(0, m.start() - 40) : m.start()])
            for m in _LEVEL.finditer(sentence)
        )

    def mask_prices(self, text: str) -> tuple[str, int]:
        """Step 5b: drop ticker quotes and price-move sentences; remove price-target and deal-price levels."""
        n = 0
        text = _FOOTNOTE.sub(r"\1", text)
        text, k = QUOTE.subn("", text)
        n += k
        for sentence in split_sentences(text):
            if self.is_price_move(sentence) or self.is_price_level(sentence):
                text = text.replace(sentence, "", 1)
                n += 1
        text = _SEP_RUN.sub(lambda m: m.group(1) + " ", text).strip(" ;|")
        text, k = PT_FROM_TO.subn(
            lambda m: self._relative(m["label"], m["mid"], m.group(3), m.group(4)), text
        )
        n += k
        text, k = PT_TO_FROM.subn(
            lambda m: self._relative(m["label"], m["mid"], m.group(4), m.group(3)), text
        )
        n += k
        for _ in range(3):
            text, k = PT_AMOUNT.subn(lambda m: f"{m['label']}{m['mid'].rstrip()}", text)
            n += k
            if not k:
                break
        text, k = AMOUNT_PT.subn(lambda m: m["label"], text)
        n += k

        def deal(m: re.Match[str]) -> str:
            left = text[max(0, m.start() - 80) : m.start()]
            return "a per-share price" if _DEAL.search(left) and not _FUND_LEFT.search(left) else m.group(0)

        text, k = PER_SHARE.subn(deal, text)
        return text, n

    # --- one text ----------------------------------------------------------------------------------

    def pre_ner(self, text: str, company_id: int | None, *, is_title: bool) -> tuple[str, MaskCounts]:
        """Steps 1–3 (no spaCy)."""
        c = MaskCounts()
        text, n = self.mask_lead(text)
        c.dates += n
        if company_id is not None:
            text, cc = self.mask_company(text, company_id)
            c.add(cc)
        text, n = self.mask_dates(text)
        c.dates += n
        return text, c

    def post_ner(
        self, text: str, candidates: Sequence[Candidate], surnames: frozenset[str] = frozenset()
    ) -> tuple[str, int]:
        """Steps 4–5."""
        text, n = self.mask_persons(text, candidates, surnames)
        text, k = CJK_PERSON.subn(PERSON, text)
        n += k
        text = self._detector.scrub(_tidy(text))
        text, _ = self.mask_prices(text)
        return _tidy(text), n

    def mask_texts(
        self,
        items: Sequence[tuple[str, int | None, bool]],
        *,
        groups: Sequence[object] | None = None,
        n_process: int = 1,
        batch_size: int = 256,
    ) -> list[tuple[str, MaskCounts]]:
        """Mask many (text, company_id, is_title) items; spaCy runs once over all pre-masked texts.

        ``groups`` (one label per item; items of a group are consecutive, e.g. an article's title and snippet)
        lets a surname alone count as a person when the full name appears elsewhere in the group. Without
        ``surnames`` at construction, the corpus surnames are derived from these items (``corpus_surnames``)
        and kept in ``self.surnames``.
        """
        pre = [self.pre_ner(t, cid, is_title=title) for t, cid, title in items]
        labels = list(range(len(items))) if groups is None else list(groups)
        docs = self.nlp.pipe([p[0] for p in pre], batch_size=batch_size, n_process=n_process)
        cands: list[list[Candidate]] = []
        other: dict[str, int] = {}
        for d in docs:
            cands.append(self._persons(d))
            for ent in d.ents:
                if ent.label_ in _NON_PERSON_LABELS:
                    for w in ent:
                        other[w.text] = other.get(w.text, 0) + 1
        if self._derive_surnames:
            foreign = [self._detector.non_english(p[0]) for p in pre]
            self.surnames = self.corpus_surnames(cands, foreign, other)
        out: list[tuple[str, MaskCounts]] = []
        i = 0
        while i < len(pre):
            j = i + 1
            while j < len(pre) and labels[j] == labels[i]:
                j += 1
            local = frozenset(w[-1] for c in cands[i:j] for _, _, w in c if len(w) >= 2 and self._namelike(w))
            for (text, counts), c in zip(pre[i:j], cands[i:j], strict=True):
                masked, n = self.post_ner(text, c, local)
                counts.persons += n
                out.append((masked, counts))
            i = j
        return out

    def mask(self, text: str, company_id: int | None, *, is_title: bool = False) -> str:
        return self.mask_texts([(text, company_id, is_title)])[0][0]


@functools.cache
def load_spacy() -> Any:
    """``en_core_web_sm`` with only the NER pipe (pinned in pyproject.toml)."""
    import spacy

    return spacy.load(SPACY_MODEL, exclude=list(SPACY_EXCLUDE))
