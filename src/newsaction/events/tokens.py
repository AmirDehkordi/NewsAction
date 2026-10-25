"""News-block token counting and the 600-token cap (PREREG §6.9; PRD NA-03 S5).

**Tokenizer.** The tokenizer of ``answerdotai/ModernBERT-large``, at the revision pinned in
``configs/events.yaml``. It is downloaded from the Hugging Face Hub once and read from the local cache
afterwards.

**Block.** An event's news block is the text of its articles in list order. Each article is its title
and its snippet joined by a line break (an empty part is left out: NA-02 scrubbing can empty either).
Articles are separated by a blank line. The
block's token count is ``len(encode(block))`` without special tokens. The verifier re-tokenizes
``render_block`` of the stored list.

**Cap.** Articles come in order of filter score, then t_avail. While the block exceeds the cap and
more than one article remains, the last (lowest-score) article is dropped. If the single remaining
article still exceeds the cap, its snippet is cut at a token boundary (its title too, if the title
alone exceeds the cap). Only the last snippet is ever truncated.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from newsaction.events import EventsConfig, load_events_config

TITLE_SEP: Final = "\n"
ARTICLE_SEP: Final = "\n\n"

Encode = Callable[[str], list[int]]
Offsets = Callable[[str], list[tuple[int, int]]]


@dataclass(frozen=True)
class ArticleText:
    title: str
    snippet: str
    snippet_truncated: bool = False
    title_truncated: bool = False


def render(a: ArticleText) -> str:
    return TITLE_SEP.join(part for part in (a.title, a.snippet) if part)


def render_block(articles: Sequence[ArticleText]) -> str:
    return ARTICLE_SEP.join(render(a) for a in articles)


@functools.cache
def tokenizer(cfg: EventsConfig | None = None) -> Any:
    """The pinned ModernBERT-large tokenizer (local cache first; Hub download once)."""
    from transformers import AutoTokenizer

    cfg = load_events_config().events if cfg is None else cfg
    try:
        return AutoTokenizer.from_pretrained(
            cfg.tokenizer, revision=cfg.tokenizer_revision, local_files_only=True
        )
    except OSError:
        return AutoTokenizer.from_pretrained(cfg.tokenizer, revision=cfg.tokenizer_revision)


def hf_encode(tok: Any) -> Encode:
    def enc(text: str) -> list[int]:
        return list(tok(text, add_special_tokens=False)["input_ids"])

    return enc


def hf_offsets(tok: Any) -> Offsets:
    def off(text: str) -> list[tuple[int, int]]:
        return [
            tuple(o)
            for o in tok(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
        ]

    return off


def count_batch(tok: Any, texts: Sequence[str]) -> list[int]:
    """Token counts of many texts in one fast-tokenizer call."""
    if not texts:
        return []
    ids = tok(list(texts), add_special_tokens=False, return_attention_mask=False)["input_ids"]
    return [len(x) for x in ids]


def _cut(text: str, keep_tokens: int, offsets: Offsets) -> str:
    if keep_tokens <= 0:
        return ""
    off = offsets(text)
    if keep_tokens >= len(off):
        return text
    return text[: off[keep_tokens - 1][1]].rstrip()


def _shrink(
    articles: list[ArticleText], field: str, encode: Encode, offsets: Offsets, cap: int
) -> list[ArticleText]:
    """Cut ``field`` of the last article to the longest token prefix that fits the cap."""
    last = articles[-1]
    text = getattr(last, field)
    lo, hi = 0, len(offsets(text))  # invariant: lo fits (checked below), hi+1 does not

    def with_k(k: int) -> list[ArticleText]:
        cut = _cut(text, k, offsets)
        flag = f"{field}_truncated"
        return [*articles[:-1], replace(last, **{field: cut, flag: cut != text})]

    if len(encode(render_block(with_k(0)))) > cap:
        return with_k(0)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(encode(render_block(with_k(mid)))) <= cap:
            lo = mid
        else:
            hi = mid - 1
    return with_k(lo)


@dataclass(frozen=True)
class Capped:
    articles: list[ArticleText]
    n_tokens: int
    n_dropped: int


def cap_articles(articles: Sequence[ArticleText], cap: int, encode: Encode, offsets: Offsets) -> Capped:
    """Apply the cap (module docstring); ``articles`` are in list order (highest score first)."""
    if not articles:
        raise ValueError("an event needs at least one article")
    kept = list(articles)
    n = len(encode(render_block(kept)))
    while n > cap and len(kept) > 1:
        kept.pop()
        n = len(encode(render_block(kept)))
    if n > cap:
        kept = _shrink(kept, "snippet", encode, offsets, cap)
        n = len(encode(render_block(kept)))
    if n > cap:
        kept = _shrink(kept, "title", encode, offsets, cap)
        n = len(encode(render_block(kept)))
    if n > cap:
        raise ValueError(f"cannot fit one article into {cap} tokens")
    return Capped(kept, n, len(articles) - len(kept))
