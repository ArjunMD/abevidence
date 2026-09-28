"""Official ICD-10-CM code table for the imaging → ICD-10 tool.

data/icd10cm_2026.tsv.gz is the CMS FY2026 "order" file reduced to
code <tab> billable-flag <tab> long description (98k codes, 75k billable).
Everything the model proposes is checked here: a code that isn't in this
table is not a code, and a category header (billable flag 0, e.g. I63) is
not a problem-list entry until it has its remaining characters.
"""

import gzip
import os
from functools import lru_cache

TABLE_PATH = os.path.join("data", "icd10cm_2026.tsv.gz")
FISCAL_YEAR = "FY2026"


@lru_cache(maxsize=1)
def _table() -> dict[str, tuple[bool, str]]:
    codes: dict[str, tuple[bool, str]] = {}
    with gzip.open(TABLE_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            code, flag, desc = line.rstrip("\n").split("\t", 2)
            codes[code] = (flag == "1", desc)
    return codes


def normalize(code: str) -> str:
    """'i63.412 ' → 'I63412' (the table stores codes without the dot)."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def display(code: str) -> str:
    """'I63412' → 'I63.412'."""
    c = normalize(code)
    return f"{c[:3]}.{c[3:]}" if len(c) > 3 else c


def lookup(code: str) -> dict | None:
    """{"code": "I63.412", "billable": True, "description": ...} or None if the
    code does not exist in the table."""
    c = normalize(code)
    hit = _table().get(c)
    if not hit:
        return None
    return {"code": display(c), "billable": hit[0], "description": hit[1]}


def children(code: str, limit: int = 12) -> list[dict]:
    """Billable codes beneath a category header, in table order."""
    c = normalize(code)
    out = []
    for k, (billable, desc) in _table().items():
        if billable and k.startswith(c) and k != c:
            out.append({"code": display(k), "billable": True, "description": desc})
            if len(out) >= limit:
                break
    return out


def search(terms: list[str], limit: int = 15) -> list[dict]:
    """Billable codes whose description contains every term (case-insensitive
    substrings); falls back to the codes matching the most terms when nothing
    matches all of them."""
    toks = [t.strip().lower() for t in terms if t and t.strip()]
    if not toks:
        return []
    scored = []
    for k, (billable, desc) in _table().items():
        if not billable:
            continue
        d = desc.lower()
        n = sum(1 for t in toks if t in d)
        if n:
            scored.append((n, len(desc), k, desc))
    if not scored:
        return []
    best = max(s[0] for s in scored)
    need = best if best == len(toks) else max(1, best)
    keep = [s for s in scored if s[0] >= need]
    # Most terms matched, then the shortest (most general) description first.
    keep.sort(key=lambda s: (-s[0], s[1]))
    return [{"code": display(k), "billable": True, "description": desc} for _, _, k, desc in keep[:limit]]
