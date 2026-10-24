"""PRD NA-02 S9: domain -> source class (``configs/sources.yaml``).

Classes: press_wire_primary, major_outlet, aggregator, retail_analysis, auto_generated, other.

A domain (lower case, ``www.`` stripped) is matched, in order, against
1. ``domains``: exact names per class (the top domains by member-article volume are listed explicitly);
2. ``suffixes``: a class for every subdomain of a name (``it.marketscreener.com``, ``uk.investing.com``);
3. ``prefixes``: a class for hosts starting with a label such as ``investor.`` or ``ir.`` (company IR);
otherwise ``other``.

``source_class_domain`` uses the domain only (a static property of the article, usable in states).
``source_class`` additionally sets ``press_wire_primary`` when the vendor flag ``tag_primary_source`` is
True (PRD S9); it depends on a vendor label, so it is ``selection_only`` (CLAUDE.md A6).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Final, Literal, get_args

import pandas as pd

from newsaction.config import ConfigError, load_yaml
from newsaction.paths import CONFIGS

SourceClass = Literal[
    "press_wire_primary", "major_outlet", "aggregator", "retail_analysis", "auto_generated", "other"
]
SOURCE_CLASSES: Final[tuple[str, ...]] = get_args(SourceClass)
PRIMARY: Final = "press_wire_primary"
OTHER: Final = "other"
SOURCES_PATH: Final = CONFIGS / "sources.yaml"


def normalize_domain(domain: object) -> str:
    if domain is None or (isinstance(domain, float) and domain != domain) or domain is pd.NA:
        return ""
    d = str(domain).strip().lower()
    return d[4:] if d.startswith("www.") else d


class SourceMap:
    def __init__(self, domains: dict[str, str], suffixes: dict[str, str], prefixes: dict[str, str]) -> None:
        for table in (domains, suffixes, prefixes):
            bad = {k: v for k, v in table.items() if v not in SOURCE_CLASSES}
            if bad:
                raise ConfigError(f"sources.yaml: unknown source classes {bad}")
        self.domains, self.suffixes, self.prefixes = domains, suffixes, prefixes

    @classmethod
    def from_yaml(cls, path: Path = SOURCES_PATH) -> SourceMap:
        raw = load_yaml(path)

        def invert(section: str) -> dict[str, str]:
            out: dict[str, str] = {}
            for klass, names in (raw.get(section) or {}).items():
                for name in names or []:
                    key = normalize_domain(name)
                    if key in out:
                        raise ConfigError(f"sources.yaml: {section} entry {key!r} is listed twice")
                    out[key] = str(klass)
            return out

        return cls(invert("domains"), invert("suffixes"), invert("prefixes"))

    def classify(self, domain: object) -> str:
        d = normalize_domain(domain)
        if not d:
            return OTHER
        if d in self.domains:
            return self.domains[d]
        labels = d.split(".")
        for i in range(1, len(labels) - 1):
            parent = ".".join(labels[i:])
            if parent in self.suffixes:
                return self.suffixes[parent]
        for prefix, klass in self.prefixes.items():
            if d.startswith(prefix):
                return klass
        return OTHER


@functools.cache
def _load(path: Path, mtime_ns: int) -> SourceMap:
    return SourceMap.from_yaml(path)


def load_source_map(path: Path = SOURCES_PATH) -> SourceMap:
    return _load(path, path.stat().st_mtime_ns)


def source_class_domain(domains: pd.Series) -> pd.Series:
    sm = load_source_map()
    lookup = {d: sm.classify(d) for d in domains.dropna().unique()}
    return domains.map(lookup).fillna(OTHER).astype("str")


def source_class(domains: pd.Series, tag_primary_source: pd.Series) -> pd.Series:
    """Domain class, overridden to press_wire_primary where the vendor marks a primary source."""
    base = source_class_domain(domains)
    primary = tag_primary_source.astype("boolean").fillna(False).astype(bool)
    return base.where(~primary, PRIMARY)
