"""Residual-leak scanner for masked states (PREREG §6.3 target < 0.5%; PRD NA-04 S3, S7, AC2).

The scanner is **independent of the masker**: it imports nothing from ``states.mask`` and does not read
``configs/aliases.yaml`` (tests/test_states_mask.py checks the imports). Its references are:
- **names**: the company's ATOM names (every share class; legal suffixes and class designations removed by
  its own rule), their distinctive words, and the names **harvested** from the unmasked event texts, i.e. the
  words right before the company's own "(TICKER)" / "(EXCH: TICKER)" (``harvest_names``, seen ≥ 3 times),
  and the Chinese / Japanese / Korean strings that end the CJK text right before it (``harvest_cjk_names``:
  every 2–6 character ending seen ≥ 2 times; a different rule from the masker's);
- **tickers**: the company's tickers in any form: $T, any upper-case code + ":" + T (NYSE:, BOATS:), "(T",
  "（紐交所：T）", T US, T.US, T's, option codes (T250703C305000), and **bare T in upper case** in any text
  that is not mostly in capitals, whatever the ticker (COST, MET, MS, IT), except a clock time ("4:30 PM");
  in a text mostly in capitals, bare T only if T is not an ordinary word of the corpus;
- **dates**: English, French, German, Italian, Spanish, Portuguese, Dutch, Polish, Chinese, Japanese and
  Korean month and weekday names and dates, numeric dates, option expiries, period labels in any case and
  glued to text (Q3, 3Q25, H1 25, FY25, fiscal 2025, "second quarter", "first half", "3. Quartal", 第二季度,
  "yearQ2", "quarter-25") and the remnants of masked day ranges ("recently-18"); since the third verification
  also written-out ordinal quarters and halves ("deuxième trimestre", "zweiten Quartal"), "3T25", "du T2",
  Korean 분기 / 반기, two-digit years after an apostrophe ("'25", "FY’25"), a lone "Aug.", bare H1 / 2H,
  glued yyyymmdd and day-first dates ("21/04"); **years**: 1900–2099 not inside a larger number ("CY2025",
  "EHA2025", "2025年" count; "Russell 2000" excepted).

AC2 counts names + tickers and years + dates. The scanner also counts, for the REPORT and the price-talk test,
price-move sentences, ticker quotes ("MPC-1.32%", "· IP. -0.58%", "Chg%"), price levels (price targets,
"shares at $X", "Price:49.32") and public figures (a sentinel list and Chinese transliterated names,
"薩姆·阿爾特曼"). Since the fourth verification, price levels also count any amount within reach of a share
word unless a per-share, fundamental, trade-size or deal cue is near ("shares closed yesterday at $242.66"),
price targets in any currency notation ("at USD 220", "€151.88 / share") and per-share deal prices; price
moves also count the direction after the number ("Trading 2.4% Higher") and moves as nouns ("1.95% Stock
Rise"). It reads the ``news`` items of a state (the only free text), one headline or snippet at a time.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from typing import Final

import pandas as pd

# words that never make a company name on their own (the scanner's own list)
GENERIC: Final = frozenset(
    """the of and for in on by to at as with from a an inc incorporated corp corporation co company companies
    ltd limited plc llc lp group holdings holding international global american america national united
    general first capital financial services service bank bancorp trust partners technologies technology
    systems solutions industries resources energy power electric health healthcare medical pharmaceuticals
    sciences scientific laboratories labs networks communications media entertainment software data digital
    realty properties residential brands foods products materials chemicals motors motor auto automotive
    parts insurance life markets exchange management new york north south east west southern western
    northern pacific texas royal universal stock stocks shares share news report reports update analyst
    rating price target class series earnings flash unusually large options volume sees bancshares
    bancorporation""".split()  # noqa: SIM905
)
# CJK words that never make a company name on their own (the scanner's own list)
CJK_GENERIC: Final = frozenset(
    (  # noqa: SIM905
        "公司 股份 集團 集团 控股 有限 銀行 银行 科技 能源 美國 美国 中國 中国 股票 그룹 회사 "
        "ホールディングス グループ コーポレーション カンパニー インク"
    ).split()
)
LATIN: Final = r"A-Za-z0-9\u00C0-\u024F"
CJK: Final = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af"
PEOPLE: Final = re.compile(
    r"\b(?:Trump|Powell|Biden|Bessent|Lutnick|Yellen|Lagarde|Musk|Buffett|Zuckerberg|Bezos|Dimon|Altman|Nadella|"
    r"Pichai|Jassy|Huang|Putin|Zelensky|Harris|Vance|Xi)\b"
    r"|[\u4e00-\u9fff]{1,4}[·•][\u4e00-\u9fff]{1,6}"
)
_SUFFIX: Final = re.compile(
    r"(?:,?\s+(?:&\s*Co\.?|&\s*Company|Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?|Company|Companies|Ltd\.?|"
    r"Limited|plc|PLC|N\.V\.|S\.A\.|SE|AG|LLC|L\.P\.|LP))+\s*$"
)
_CLASS: Final = re.compile(r"\s*\((?:Class|Series)\s+[A-Z0-9]+\)\s*$|\s+(?:Class|Series)\s+[A-Z0-9]+$")
_PAREN: Final = re.compile(r"^(?P<base>.+?)\s*\((?P<head>[A-Z][a-z]+)\)\s*$")

_YEAR: Final = re.compile(r"(?<!\d[.,])(?<![0-9$€£¥])(?<!Russell\s)(?:19\d\d|20\d\d)(?![\d%]|[.,]\d)")
_EN_MONTHS: Final = "January|February|March|April|June|July|August|September|October|November|December"
_F_MONTHS: Final = (
    "janvier|février|fevrier|avril|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|januar|"
    "jänner|februar|märz|maerz|juni|juli|oktober|dezember|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
    "settembre|ottobre|dicembre|enero|febrero|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|"
    "diciembre|janeiro|fevereiro|março|marco|junho|julho|setembro|outubro|novembro|dezembro|januari|februari|"
    "maart|augustus|stycznia|lutego|marca|kwietnia|czerwca|lipca|sierpnia|września|wrzesnia|października|"
    "listopada|grudnia"
)
_F_WEEKDAYS: Final = (
    "montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|lundi|mardi|mercredi|jeudi|vendredi|samedi|"
    "dimanche|lunedì|lunedi|martedì|martedi|mercoledì|mercoledi|giovedì|giovedi|venerdì|venerdi|lunes|martes|"
    "miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|sabato|domenica|segunda-feira|terça-feira|"
    "terca-feira|quarta-feira|quinta-feira|sexta-feira|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag"
)
# written-out ordinal quarters and halves (third verification): "deuxième trimestre", "zweiten Quartal"
_ORDINALS: Final = (
    "premier|première|1er|1re|deuxième|deuxieme|2e|2ème|second|seconde|troisième|troisieme|3e|3ème|quatrième|"
    "quatrieme|4e|4ème|primer|primero|primera|segundo|segunda|tercer|tercero|tercera|cuarto|cuarta|primo|prima|"
    "secondo|seconda|terzo|terza|quarto|quarta|primeiro|primeira|terceiro|terceira|erste|ersten|erstes|zweite|"
    "zweiten|zweites|dritte|dritten|drittes|vierte|vierten|viertes|eerste|tweede|derde|vierde"
)
_DATE: Final = re.compile(
    rf"\b(?:{_EN_MONTHS}|{_EN_MONTHS.upper()})\b|\b(?:May|MAY)\s+\d"
    r"|\b(?i:(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2})\b"
    r"|\b(?i:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?)\b"
    rf"|\b(?i:{_F_MONTHS}|{_F_WEEKDAYS})\b|\b\d{{1,2}}\.?\s+(?i:mai|mars|mei)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"
    r"|(?<![\d/.$,])\b(?:1[0-2]|0?[1-9])/(?:1[3-9]|2\d|3[01])\b(?![\d/%])"
    # period labels with ASCII boundaries (CJK characters are word characters: "年Q2"), and glued ("yearQ2")
    r"|(?<![A-Za-z0-9])(?i:Q[1-4]|[1-4]Q\d{2}|FY\s?'?\d{2,4}|fiscal\s+(?:year\s+)?\d{4}|[1-4]\.\s*Quartal)"
    r"(?![A-Za-z0-9])|(?<=[a-z])Q[1-4](?![A-Za-z0-9])"
    r"|\b(?i:(?:first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter|(?:first|second|1st|2nd)[\s-]+half)\b"
    r"|\b[Hh][12]\s?'?\d{2,4}\b|\b[12]H\s?'?\d{2}\b|\b(?i:quarter|half|year)\s?[-–'’/]\s?\d{2}\b"
    # third verification: ordinals with trimestre / Quartal / semestre, "3T25", "du T2", Korean 분기 / 반기,
    # "'25" / "FY’25" / "Q1 ‘25", a lone "Aug.", bare H1 / 2H, glued yyyymmdd, day-first "21/04"
    rf"|\b(?i:(?:{_ORDINALS})\s+(?:trimestre|quartals?|kwartaal|semestre|halbjahr(?:e?s)?|halfjaar))\b"
    r"|(?<![A-Za-z0-9])[1-4]T\s?['’‘]?\d{2}(?:\d{2})?(?![A-Za-z0-9])"
    r"|\b(?:au|Au|du|le|Le|el|El|del|no|do|em|ao|résultats|resultados?)\s+T[1-4](?![A-Za-z0-9/])"
    r"|[1-4１-４]\s?분기|[상하]반기"
    r"|(?<![A-Za-z0-9'’‘])['’‘][12]\d(?![A-Za-z0-9%'’])|(?i:\b[FC]Y\s?['’‘]\d{2}\b)|\b(?i:Q[1-4])\s?['’‘]\d{2}\b"
    r"|(?<![A-Za-z])(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9$/<])(?<!green )(?<!Green )(?<!blue )(?:H[12]|[12]H)"
    r"(?![A-Za-z0-9>]|-[A-Z]|\s+(?:[Pp]roduction|[Ff]uel|[Tt]imeframe))"
    r"|(?<!\d)20[0-4]\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)"
    r"|(?<![\d/.$,])\b(?!24/(?:7|5|365)\b)(?:1[3-9]|2\d|3[01])/(?:0?[1-9]|1[0-2])\b(?![\d/%])"
    # Chinese, Japanese, Korean
    r"|\d{1,2}\s?[月월]|(?<!\d)\d{1,2}\s?[日号일](?![本元])"
    r"|(?:星期|週|周|禮拜|礼拜)[一二三四五六日天]|[月火水木金土日]曜|[월화수목금토일]요일"
    r"|第\s?[一二三四1-4１-４]\s?[財财]?(?:季度|季|四半期)|[上下]半(?:年|期)"
    # option expiries and masked day ranges
    r"|\b\d{6}\s+\$?\d+(?:\.\d+)?\s?[CP]\b|\b[A-Z]{1,6}\d{6}[CP]\d{3,9}\b"
    r"|\b(?i:recently)\s?[–\-]\s?\d{1,2}\b(?!:)"  # not a time: "Recently - 08:30 AM"
    r"|\b\d{1,2}\s?[–\-]\s?(?i:recently)\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[-’'/]\d{2}\b(?![-/.]\d)"  # "Sep-25 puts"
)
_PRICE_MOVE: Final = re.compile(
    r"(?i)\b(?:shares?|stock|premarket|pre-market|after-hours|extended trading)\b[^.!?]{0,50}?"
    r"\b(?:rise[sn]?|rose|rising|fall(?:s|en|ing)?|fell|jump(?:s|ed|ing)?|drop(?:s|ped|ping)?|gain(?:s|ed|ing)?|"
    r"slides?|slid|slip(?:s|ped)?|climb(?:s|ed|ing)?|surg(?:e|es|ed|ing)|plung(?:e|es|ed|ing)|soar(?:s|ed|ing)?|"
    r"tumbl(?:e|es|ed|ing)|sinks?|sank|rall(?:y|ies|ied)|declin(?:e|es|ed|ing)|advanc(?:e|es|ed|ing)|up|down|"
    r"higher|lower)\b[^.!?]{0,25}?\d+(?:[.,]\d+)?\s?%"
    r"|\b\d+(?:[.,]\d+)?\s?%\s+(?:premarket|pre-market|in premarket|before the bell|after hours)"
)
# fundamental acronyms are not tickers ("EPS -59%", "AUM +14%"): the scanner's own list
_NOT_QUOTED: Final = (
    r"(?!(?:EPS|FFO|AFFO|AUM|FRE|ARR|NII|NIM|GDP|CPI|PPI|YOY|QOQ|EBIT|EBITDA|ROE|ROI|ROA|FCF|RPO)\b)"
)
_QUOTE: Final = re.compile(
    rf"(?<![A-Za-z0-9]){_NOT_QUOTED}[A-Z]{{2,5}}\s?[+\-−–]\s?\d+(?:\.\d+)?\s?%"
    rf"|(?<![A-Za-z0-9]){_NOT_QUOTED}[A-Z]{{2,5}}\d+\.\d+\s?%"
    r"|(?:·\s*\S{1,8}?|[Tt]he company)\.?\s+[+\-−–]\s?\d+(?:\.\d+)?\s?%|Chg%"
)
_NOT_AMOUNT: Final = r"(?![\d,.]*\s*(?:[MBK]\b|million|billion|bn|trillion))"  # "$35 Billion" is no price
_PRICE_LEVEL: Final = re.compile(
    rf"(?i)(?:price\s+target|target\s+price|price\s+objective|\bPT\b)[^.!?]{{0,60}}?\$\s?\d{_NOT_AMOUNT}"
    r"|\$\s?\d[\d,]*(?:\.\d+)?\s+(?:price\s+target|PT)\b"
    rf"|(?<!per\s)(?<!diluted\s)(?<!basic\s)\b(?:shares?|stock)\s+(?:at|to|closed\s+at|trading\s+at)\s+\$\s?\d"
    rf"{_NOT_AMOUNT}"
    r"|\bPrice:\s?\$?\d"
)
# since the fourth verification (the scanner's own forms): the direction after the number ("Trading
# 2.4% Higher") and moves as nouns ("1.95% Stock Rise", "a 3% rise in shares", "closed at a 1.18% decline")
_MOVE_AFTER_NUMBER: Final = re.compile(
    r"(?i)\b(?:shares?|stocks?|the company)\b(?P<stretch>[^.!?%]{0,50}?)\b\d+(?:[.,]\d+)?\s?%\s+"
    r"(?:higher|lower)\b"
)
_MOVE_NOUN: Final = re.compile(
    r"(?i)\btrad(?:e|es|ed|ing)\s+\d+(?:[.,]\d+)?\s?%\s+(?:higher|lower)\b"
    r"|\b\d+(?:[.,]\d+)?\s?%\s+(?:stock|share)\s+(?:rise|drop|gain|decline|jump|fall|surge|plunge|slide|rally)"
    r"|\ban?\s+\d+(?:[.,]\d+)?\s?%\s+(?:rise|drop|gain|decline|jump|fall|surge|plunge|slide|rally|loss)\s+"
    r"(?:in|for)\s+(?:the\s+company['’]s\s+|the\s+)?(?:shares?|stock)\b"
    r"|\b(?:company['’]s|stock['’]s)\s+\d+(?:[.,]\d+)?\s?%\s+(?:gains?|rises?|drops?|declines?|jumps?|falls?|"
    r"surges?|losses|slides?)\b(?!\s+(?:in|of)\s+(?:revenue|sales|earnings|profit|income))"
    r"|\bclosed\s+(?:at|with)\s+an?\s+\d+(?:[.,]\d+)?\s?%\s+(?:decline|gain|rise|drop|loss)\b"
)
# any amount within reach of a share word, unless a per-share, fundamental, trade-size or deal cue is near
_SHARE_AMOUNT: Final = re.compile(
    r"(?i)\b(?:shares?|stock(?:\s+price)?)\b(?!\s+markets?\b)(?P<stretch>[^.!?]{0,70}?)(?:C\$|US\$|\$|USD\s?|GBX\s?|€\s?|£\s?)"
    r"\d[\d,]*(?:\.\d+)?(?P<after>[^.!?]{0,25})"
)
_AMOUNT_CUES: Final = re.compile(
    r"(?i)per\s+(?:\w+\s+)?share|a\s+share|/\s?share|dividend|distribution|eps|earnings|income|loss|revenue|profit|"
    r"worth|valued|value|offering|proceeds|purchase|repurchase|buyback|"
    r"volume|million|billion|trillion|\d\s?[mbk]\b|bn\b|market\s+cap|capitali[sz]ation|stake|holding|position|"
    r"invest|fund|plan|program|award|grant|option|compensation|salary|fee|fine|settlement|cost|for\s+\$|"
    r"would\s+(?:have|be\s+worth)|gold|silver|crude|oil|bitcoin"
)
# a price target, estimate or fair value in any currency notation; a per-share deal price
_TARGET_ANY: Final = re.compile(  # "$" after the base labels is counted by _PRICE_LEVEL
    r"(?i)(?:price\s+targets?|target\s+prices?|price\s+objectives?|price\s+goals?|price\s+estimates?|"
    r"fair\s+values?|targeting\s+a\s+price)[^.!?]{0,60}?(?:(?:US\$|C\$|USD|GBX|GBp|EUR|€|£)\s?\d|"
    r"\d[\d.,]*\s?(?:USD|EUR|€|GBX|pence)\b)(?![\d,.]*\s*(?:[MBK]\b|million|billion|bn|trillion))"
    r"|(?:price\s+goals?|price\s+estimates?|fair\s+values?|targeting\s+a\s+price)[^.!?$]{0,60}?\$\s?\d"
    r"(?![\d,.]*\s*(?:[MBK]\b|million|billion|bn|trillion))"
    r"|\$\s?\d[\d,]*(?:\.\d+)?\s+(?:price\s+estimate|fair\s+value)\b"
)
# a level after a trading verb counts whatever words sit between ("shares, part of the earnings season rally,
# closed at $242.66")
_SHARE_VERB_LEVEL: Final = re.compile(
    r"(?i)\b(?:shares?|stock(?:\s+price)?)\b[^.!?]{0,50}?\b(?:closed|closing|opened|opening|traded|trading|trades?|"
    r"stood|stands?|settled|settling|ended|finished|hit|touched|reached)\b[^.!?$]{0,20}?\b(?:at|to|near|around|"
    r"as\s+(?:high|low)\s+as)\s+(?:C\$|US\$|\$|USD\s?|€\s?|£\s?)\d[\d,]*(?:\.\d+)?(?!\s*(?:per|a|/)\s*share)"
)
# since the fourth verification's second pass: any cents-precision amount in a sentence without a per-share
# fundamental word is a level (MarketBeat's "The company traded as high as $155.51", "Receives $49.11 Average
# Price Target", "a one-year high of $66.44"); options-flow chatter; moves written "an increase of 2.4%" or
# "added 16%"
_CENTS_ANY: Final = re.compile(
    r"(?i)(?:C\$|US\$|A\$|\$|USD\s?|GBX\s?|€\s?|£\s?)\d[\d,]*\.\d{2}(?!\d)"
    r"(?!\s*(?:[MBKT]\b|mn\b|mln\b|bn\b|bln\b|million|billion|trillion))"
)
_TARGET_WORDS: Final = re.compile(r"(?i)\b(?:price\s+targets?|target\s+prices?|price\s+objectives?|PTs?)\b")
_PCT_IN_PARENS: Final = re.compile(r"\s*\(\s*[+\-−–]?\d+(?:[.,]\d+)?\s?%\s*\)")
_FUNDAMENTAL_WORDS: Final = re.compile(
    r"(?i)\b(?:eps|earnings|per[\s-]+(?:\w+\s+)?share|dividends?|distributions?|payouts?|ffo|affo|consensus|"
    r"estimates?|expected|expects?|guidance|book\s+value|nav|coupons?|notes|bonds?)\b|/\s?share|\ba\s+share\b"
)
_PRICE_BEFORE: Final = re.compile(
    r"(?i)\b(?:price|prices|trading|traded|trades|closed|closing|opened|ended|rall(?:y|ies|ied)|jump(?:s|ed)?|"
    r"plung(?:e|es|ed)|surg(?:e|es|ed)|sank|soar(?:s|ed)?|climb(?:s|ed)?|fell|rose|hits?|reach(?:es|ed)?|"
    r"touch(?:es|ed)?|stands?|stood|settl(?:es|ed|ing))\b[^$€£.;!?]{0,25}$"
)
_OPTIONS_CHATTER: Final = re.compile(
    r"(?i)\b(?:lifted|hit|paid)\s+the\s+\$\d|\bunderlying\s+shares\s+were\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}\s+\$?\d[\d.]*\s+(?:puts?|calls?)\b"
    r"|\bweekly\s+\$?\d[\d.]*\s+(?:puts?|calls?)\b"
)
_MOVE_OF: Final = re.compile(
    r"(?i)\b(?:shares?|stocks?|stock\s+price|the\s+company(?:['’]s)?)\b(?P<stretch>[^.!?%]{0,60}?)\b(?:increase|"
    r"decrease|decline|rise|drop|gain|downturn|dip|loss|surge|jump|uptick|advance|slide|fall)\s+of\s+"
    r"(?:about\s+|nearly\s+|almost\s+|over\s+|more\s+than\s+)?\d+(?:[.,]\d+)?\s?%"
    r"|\b(?:shares?|stocks?)\b(?P<stretch2>[^.!?%]{0,30}?)\b(?:add(?:s|ed|ing)?|shed(?:s|ding)?)\s+\d+(?:[.,]\d+)?\s?%"
    r"|\b\d+(?:[.,]\d+)?\s?%\s+during\s+(?:after-hours|after\s+hours|premarket|pre-market|extended)"
)
# a sentence break, not after an abbreviation ("EPS $2.47, vs. FactSet Est. of $2.44", "Chase & Co. from")
_SENTENCES: Final = re.compile(
    r"(?<=[.!?])(?<![Vv]s\.)(?<!Est\.)(?<!Inc\.)(?<!Co\.)(?<!Corp\.)(?<!Ltd\.)(?<!Mr\.)(?<!Ms\.)(?<!Dr\.)(?<!St\.)"
    r"(?<!\b[A-Z]\.)\s+(?=[A-Z\"“(])"
)
_AMOUNT_THEN_PRICE: Final = re.compile(
    r"(?i)(?:C\$|US\$|\$|USD\s?|€\s?|£\s?)\d[\d,]*(?:\.\d+)?\s+(?:stock|share)\s+price"
)
_LEFT_CUES: Final = re.compile(r"(?i)(?:\bper|\ba|earnings|eps|loss|income|dividends?|\d)[\s-]+(?:\w+\s+)?$")
_FOR_END: Final = re.compile(r"(?i)\bfor\s*$")
_SIZE_AFTER: Final = re.compile(r"(?i)\s?(?:[MBKT]\b|mn\b|mln|bn|bln|million|billion|trillion)")
_PER_SHARE_AFTER: Final = re.compile(r"(?i)\s*(?:per[\s-]+(?:\w+\s+)?share|a\s+share|/\s?share)")
_DEAL_PER_SHARE: Final = re.compile(  # "$47.50 in cash a share", "$4.04 cash + CVR per share"
    r"(?i)\b(?:acquir\w*|buyout|offer\w*|deal|merger|takeover|tender|bid|pay(?:s|ing)?|paid)\b[^.!?]{0,60}?"
    r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s+(?:in\s+)?cash)?(?:\s*\+\s*(?:a\s+|one\s+)?CVR)?"
    r"\s*(?:/\s?|per\s+(?:common\s+)?|a\s+)share\b(?![^.!?]{0,30}\b(?:dividends?|distributions?|eps|earnings)\b)"
)
# "30% higher revenue", "26% lower the quarter net income" (not "2% higher after earnings")
_FUND_AFTER: Final = re.compile(
    r"(?i)\s*(?:(?:the\s+)?(?:quarter|half-year|year|fiscal\s+year)\s+|quarterly\s+|annual\s+|net\s+|"
    r"adjusted\s+|comparable\s+|same-store\s+)*(?:revenues?|sales|earnings|eps|income|profits?|margins?|orders|"
    r"bookings|volume|traffic|costs?|deliveries|guidance)\b"
)
_PER_LEFT: Final = re.compile(r"(?i)\bper[\s-]$")  # "earnings per share (EPS) surged 78%" is no price move
_FUNDAMENTAL: Final = re.compile(
    r"(?i)\b(?:revenues?|sales|earnings|eps|income|profits?|margins?|outstanding|dividends?|guidance|orders|"
    r"volume|traffic|bookings|costs?)\b"
)
_CLOCK: Final = re.compile(r"\d\s?$")
_SEGMENTS: Final = re.compile(r"\n| \|\| ")


def cents_level(sentence: str) -> bool:
    """A cents amount that is a price: after a price word or move verb, or in a sentence with no per-share
    fundamental; not when "per share" follows or a fundamental word is within 45 characters before it."""
    has_fund = _FUNDAMENTAL_WORDS.search(sentence) is not None
    for m in _CENTS_ANY.finditer(sentence):
        if _PCT_IN_PARENS.match(sentence, m.end()):
            return True
        before = sentence[max(0, m.start() - 45) : m.start()]
        if _PER_SHARE_AFTER.match(sentence, m.end()) or _FUNDAMENTAL_WORDS.search(before):
            continue
        if _TARGET_WORDS.search(sentence) or _PRICE_BEFORE.search(before) or not has_fund:
            return True
    return False


def price_level_count(text: str) -> int:
    """Dollar levels of the base pattern, plus share-price levels, price targets in any notation and per-share
    deal prices (fourth verification)."""
    n = len(_PRICE_LEVEL.findall(text)) + len(_TARGET_ANY.findall(text)) + len(_DEAL_PER_SHARE.findall(text))
    n += len(_AMOUNT_THEN_PRICE.findall(text))
    for sentence in _SENTENCES.split(text):
        if _OPTIONS_CHATTER.search(sentence) or cents_level(sentence):
            n += 1
    verb = [m.span() for m in _SHARE_VERB_LEVEL.finditer(text) if not _SIZE_AFTER.match(text, m.end())]
    n += len(verb)
    for m in _SHARE_AMOUNT.finditer(text):
        left = text[max(0, m.start() - 30) : m.start()]
        if (
            any(a < m.end() and m.start() < b for a, b in verb)  # counted as a level after a verb
            or _LEFT_CUES.search(left)
            or _AMOUNT_CUES.search(m.group("stretch"))
            or _FOR_END.search(m.group("stretch"))
            or _SIZE_AFTER.match(m.group("after"))
            or _PER_SHARE_AFTER.match(m.group("after"))
        ):
            continue
        n += 1
    return n


def price_move_count(text: str) -> int:
    """Percent price moves: verb before the number, direction after it, or a move as a noun."""
    n = sum(
        1
        for m in _PRICE_MOVE.finditer(text)
        if "volume" not in m.group(0).lower()
        and not _PER_LEFT.search(text[max(0, m.start() - 12) : m.start()])
    )
    n += sum(
        1
        for m in _MOVE_AFTER_NUMBER.finditer(text)
        if not _FUNDAMENTAL.search(m.group("stretch")) and not _FUND_AFTER.match(text, m.end())
    )
    for m in _MOVE_OF.finditer(text):
        stretch = m.group("stretch") or m.group("stretch2") or ""
        if not _FUNDAMENTAL.search(stretch) and not _PER_LEFT.search(text[max(0, m.start() - 5) : m.start()]):
            n += 1
    return n + len(_MOVE_NOUN.findall(text))


@dataclass(frozen=True)
class LeakCounts:
    names: int
    tickers: int
    years: int
    dates: int
    price_moves: int = 0
    quotes: int = 0
    price_levels: int = 0
    people: int = 0

    @property
    def name_or_ticker(self) -> bool:
        return self.names + self.tickers > 0

    @property
    def year_or_date(self) -> bool:
        return self.years + self.dates > 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    def __add__(self, other: LeakCounts) -> LeakCounts:
        return LeakCounts(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})


def caps_share(text: str) -> float:
    """Share of upper-case letters among the letters of ``text`` (CJK characters count as letters)."""
    letters = [ch for ch in text if ch.isalpha()]
    return sum(ch.isupper() for ch in letters) / max(len(letters), 1)


def core_name(name: str) -> list[str]:
    """Name phrases of an ATOM name: class and legal suffixes removed; "X (The)" gives "The X" and "X"."""
    base = _CLASS.sub("", name.strip()).strip()
    m = _PAREN.match(base)
    stems = [f"{m['head']} {m['base']}", m["base"]] if m else [base]
    out = []
    for stem in stems:
        core = _SUFFIX.sub("", stem).strip().rstrip(",")
        out.append(core)
        if core.lower().startswith("the "):
            out.append(core[4:])
    return [o for o in dict.fromkeys(out) if len(o) >= 3]


_LOWER: Final = re.compile(r"(?<![A-Za-z])[a-z]{2,}(?![A-Za-z])")


def ordinary_words(texts: Iterable[str], min_count: int = 20) -> frozenset[str]:
    """Words written in lower case at least ``min_count`` times in ``texts``: the scanner's vocabulary."""
    counts: Counter[str] = Counter()
    for t in texts:
        counts.update(_LOWER.findall(t))
    return frozenset(w for w, n in counts.items() if n >= min_count)


def _ticker_alt(t: str) -> str:
    return r"[.\-/]".join(re.escape(p) for p in re.split(r"[.\-/]", t.upper()))


def harvest_names(
    articles: pd.DataFrame, tickers: Mapping[int, Sequence[str]], min_count: int = 3
) -> dict[int, list[str]]:
    """Per company: phrases of up to four capitalized words written right before its own "(TICKER)" or
    "(EXCH: TICKER)" in the unmasked texts (``articles``: company_id, title, snippet), seen ≥ ``min_count``
    times, legal suffix and leading generic words removed, with at least one non-generic word."""
    counts: dict[int, Counter[str]] = {}
    patterns: dict[int, re.Pattern[str]] = {}
    for cid, ts in tickers.items():
        alt = "|".join(_ticker_alt(t) for t in ts)
        patterns[int(cid)] = re.compile(
            rf"((?:[A-Z][\w&.'’\-]*\s+){{0,3}}[A-Z][\w&.'’\-]*)\s*\(\s*(?:[A-Z][A-Za-z]{{1,11}}\s?:\s?)?"
            rf"(?:{alt})\s*\)"
        )
    for cid, title, snippet in zip(
        articles["company_id"], articles["title"], articles["snippet"], strict=True
    ):
        rx = patterns.get(int(cid))
        if rx is None:
            continue
        for m in rx.finditer(f"{title} {snippet}"):
            words = _SUFFIX.sub("", re.split(r"[.:!?|]\s+", m.group(1).strip())[-1]).split()
            while words and words[0].lower().strip(".,'’") in GENERIC:
                words = words[1:]
            phrase = re.sub(r"['’]s$", "", " ".join(words).strip(" ,.'’"))
            if len(phrase) >= 3 and any(w.lower().strip(".,'’") not in GENERIC for w in phrase.split()):
                counts.setdefault(int(cid), Counter())[phrase] += 1
    return {cid: sorted(p for p, n in c.items() if n >= min_count) for cid, c in counts.items()}


def harvest_cjk_names(
    articles: pd.DataFrame, tickers: Mapping[int, Sequence[str]], min_count: int = 2
) -> dict[int, list[str]]:
    """Per company: every 2–6 character CJK ending of the CJK word right before its own ticker in
    parentheses ("迪爾股份（紐交所：DE）" gives 迪爾股份, 爾股份, …) in the unmasked texts, seen ≥
    ``min_count`` times, generic words (``CJK_GENERIC``) excepted."""
    has_cjk = re.compile(f"[{CJK}]")
    counts: dict[int, Counter[str]] = {}
    patterns: dict[int, re.Pattern[str]] = {}
    for cid, title, snippet in zip(
        articles["company_id"], articles["title"], articles["snippet"], strict=True
    ):
        text = f"{title} {snippet}"
        if int(cid) not in tickers or not has_cjk.search(text):
            continue
        rx = patterns.get(int(cid))
        if rx is None:
            alt = "|".join(_ticker_alt(t) for t in tickers[int(cid)])
            rx = patterns[int(cid)] = re.compile(
                rf"([{CJK}]+)\s*[（(][^()（）\n]{{0,20}}?(?<![A-Za-z])(?:{alt})(?![A-Za-z])[^()（）\n]{{0,6}}[)）]"
            )
        for m in rx.finditer(text):
            word = m.group(1).rstrip("的の의")
            for k in range(2, min(6, len(word)) + 1):
                counts.setdefault(int(cid), Counter())[word[-k:]] += 1

    def keep(w: str) -> bool:  # not a fragment: no small-kana / long-vowel start, not a generic word's end
        return w[0] not in "ァィゥェォッャュョヮーヶ・" and not any(g.endswith(w) for g in CJK_GENERIC)

    return {cid: sorted(w for w, n in c.items() if n >= min_count and keep(w)) for cid, c in counts.items()}


class LeakScanner:
    """Residual leaks of one company's state (module docstring)."""

    def __init__(
        self,
        companies: pd.DataFrame,
        extra_tickers: Iterable[tuple[int, str]] = (),
        harvested: Mapping[int, Sequence[str]] | None = None,
        ordinary: frozenset[str] = frozenset(),
        cjk: Mapping[int, Sequence[str]] | None = None,
    ) -> None:
        """``companies``: company_id, ticker, name (NA-01 ``companies.parquet``); ``extra_tickers``:
        (company_id, ticker) of former / vendor tickers; ``harvested``: ``harvest_names`` output;
        ``ordinary``: ``ordinary_words`` of the unmasked texts; ``cjk``: ``harvest_cjk_names`` output. A
        one-word name counts as written or in capitals: a whole ATOM name always ("Target"), a word of a
        longer name or a harvested word only if it is not an ordinary word ("Grumman" counts, "Research" does
        not)."""
        self.ordinary = ordinary
        self.atom: dict[int, set[str]] = {}
        self.names: dict[int, set[str]] = {}
        self.tickers: dict[int, set[str]] = {}
        self.cjk = {int(c): sorted(v, key=lambda s: (-len(s), s)) for c, v in (cjk or {}).items() if v}
        rows = zip(companies["company_id"], companies["ticker"], companies["name"], strict=True)
        for cid, ticker, name in rows:
            self.names.setdefault(int(cid), set()).update(core_name(str(name)))
            self.atom.setdefault(int(cid), set()).update(core_name(str(name)))
            self.tickers.setdefault(int(cid), set()).add(str(ticker).upper())
        for cid, t in extra_tickers:
            self.tickers.setdefault(int(cid), set()).add(t.upper())
        for cid, phrases in (harvested or {}).items():
            self.names.setdefault(int(cid), set()).update(phrases)
        self._cache: dict[int, tuple[re.Pattern[str] | None, ...]] = {}

    def _patterns(self, cid: int) -> tuple[re.Pattern[str] | None, ...]:
        """(names, ticker forms, bare upper-case tickers) of a company."""
        hit = self._cache.get(cid)
        if hit is not None:
            return hit
        phrases = self.names.get(cid, set())
        atom = self.atom.get(cid, set())

        def distinctive(w: str) -> bool:
            return w.lower() not in GENERIC and w.lower() not in self.ordinary

        multi = {  # a harvested phrase of ordinary words is not a name ("Customer Relationship Management")
            p
            for p in phrases
            if len(p.split()) > 1 and (p in atom or any(distinctive(w) for w in re.findall(r"[A-Za-z]+", p)))
        }
        single = {
            p for p in phrases if len(p.split()) == 1 and ((p in atom and len(p) >= 3) or distinctive(p))
        }
        for p in (
            q for q in atom if len(q.split()) > 1
        ):  # words of a longer ATOM name ("Grumman"), 5+ letters
            single.update(
                w for w in re.findall(r"[A-Za-z][A-Za-z'’\-]*", p) if len(w) >= 5 and distinctive(w)
            )
        parts = []
        if multi:
            alt = "|".join(r"[\s\-–]*".join(map(re.escape, re.split(r"[\s\-–]+", p))) for p in sorted(multi))
            parts.append(rf"(?i:(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9]))")
        if single:
            words = sorted(single | {w.upper() for w in single})
            parts.append(rf"(?<![A-Za-z0-9])(?:{'|'.join(map(re.escape, words))})(?![A-Za-z0-9])")
        if self.cjk.get(cid):
            parts.append("|".join(map(re.escape, self.cjk[cid])))
        glued = sorted(p for p in multi | single if p[:1].isupper() and len(p) >= 5)
        if glued:  # a capitalized name glued to the previous word: "Key TakeawaysHumana aims"
            parts.append(rf"(?<=[a-z0-9])(?:{'|'.join(map(re.escape, glued))})(?![a-z])")
        names = re.compile("|".join(parts)) if parts else None
        ts = sorted(self.tickers.get(cid, set()))
        forms = bare = None
        if ts:
            alt = "|".join(_ticker_alt(t) for t in ts)
            several = "|".join(_ticker_alt(t) for t in ts if len(t) >= 2)
            one = "|".join(_ticker_alt(t) for t in ts if len(t) == 1)
            prefixed = [  # a one-letter ticker only after an upper-case exchange ("Erden: A person" is none)
                rf"(?:\$|(?<![A-Za-z])[A-Z][A-Za-z]{{1,11}}\s?:\s?|\(\s*)(?:{several})(?![A-Za-z0-9])"
                if several
                else "",
                rf"(?:\$|(?<![A-Za-z])[A-Z]{{2,12}}\s?:\s?|\(\s*)(?:{one})(?![A-Za-z0-9])" if one else "",
            ]
            forms = re.compile(
                "|".join(
                    [
                        *(f for f in prefixed if f),
                        rf"(?<![{LATIN}$&.\-/:(])(?:{alt})(?=['’]s\b)",
                        rf"[（(][^()（）:：\n]{{0,16}}[:：]\s*(?:{alt})(?![A-Za-z0-9])",
                        rf"[\u3400-\u9fff][:：]\s*(?:{alt})(?![A-Za-z])",  # "紐交所:CTRA1年"
                        rf"(?<![A-Za-z0-9])(?:{alt})(?:\.US|\s+U[SNWQA])(?![A-Za-z])",
                        rf"(?<![A-Za-z])(?:{alt})\d{{6}}[CP]\d{{3,9}}",
                    ]
                )
            )
            long = [t for t in ts if len(t) >= 2]
            if long:
                bare = re.compile(  # also "WMT/TGT", "Omnicom-IPG", "Inc.ANET", "ABBV19"
                    rf"(?:(?<![{LATIN}$&.\-/:(])|(?<=[A-Za-z][/\-])|(?<=[a-z]\.))"
                    rf"(?:{'|'.join(_ticker_alt(t) for t in long)})(?![A-Za-z\u00C0-\u024F&'’])"
                )
        self._cache[cid] = (names, forms, bare)
        return self._cache[cid]

    def _bare(self, pattern: re.Pattern[str], text: str) -> int:
        """Bare upper-case tickers: in mixed-case text any, but not a clock time ("4:30 PM"); in a text
        mostly in capitals only one that is not an ordinary word."""
        shouting = caps_share(text) > 0.5
        n = 0
        for m in pattern.finditer(text):
            word = m.group(0)
            if word in ("AM", "PM") and _CLOCK.search(text[: m.start()]):
                continue
            if shouting and word.lower() in self.ordinary:
                continue
            n += 1
        return n

    def scan_text(self, text: str, company_id: int | None) -> LeakCounts:
        """Leaks of a text; a headline or snippet at a time (split at newlines and " || ")."""
        total = LeakCounts(0, 0, 0, 0)
        for segment in _SEGMENTS.split(text):
            total = total + self._scan_segment(segment, company_id)
        return total

    def _scan_segment(self, text: str, company_id: int | None) -> LeakCounts:
        names = tickers = 0
        if company_id is not None and company_id >= 0:
            n_re, f_re, b_re = self._patterns(company_id)
            names = len(n_re.findall(text)) if n_re is not None else 0
            tickers = len(f_re.findall(text)) if f_re is not None else 0
            tickers += self._bare(b_re, text) if b_re is not None else 0
        return LeakCounts(
            names=names,
            tickers=tickers,
            years=len(_YEAR.findall(text)),
            dates=len(_DATE.findall(text)),
            price_moves=price_move_count(text),
            quotes=len(_QUOTE.findall(text)),
            price_levels=price_level_count(text),
            people=len(PEOPLE.findall(text)),
        )

    def residual_leaks(self, state_json: str, company_id: int | None) -> LeakCounts:
        """Leaks in the ``news`` items of a state (headline and snippet)."""
        items = json.loads(state_json).get("news", [])
        text = "\n".join(f"{n['headline']} || {n['snippet']}" for n in items)
        return self.scan_text(text, company_id)
