"""One-time backfill: build the acronym legend for every guideline by detecting
acronyms in the recommendation text and expanding them with medical knowledge.

Operates only on the already-extracted display markdown ("in post") — it does NOT
re-read any source PDF. Safe to re-run; it replaces a guideline's legend each time.

Usage:
    python3 backfill_guideline_acronyms.py            # all guidelines
    python3 backfill_guideline_acronyms.py <gid> ...  # specific guideline ids
"""
import sys
from typing import List, Tuple

from db import _connect_db, ensure_guidelines_schema
from extract import label_and_store_guideline_acronyms


def _all_guidelines() -> List[Tuple[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            "SELECT guideline_id, filename FROM guidelines "
            "WHERE recommendations_display_md IS NOT NULL "
            "AND TRIM(recommendations_display_md) <> '' "
            "ORDER BY uploaded_at DESC;"
        ).fetchall()
    return [(r["guideline_id"], r["filename"] or "") for r in rows]


def _display_md(gid: str) -> str:
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT recommendations_display_md AS md FROM guidelines WHERE guideline_id=?;",
            (gid,),
        ).fetchone()
    return (row["md"] if row else "") or ""


def main() -> None:
    ensure_guidelines_schema()

    wanted = {a.strip() for a in sys.argv[1:] if a.strip()}
    rows = _all_guidelines()
    if wanted:
        rows = [r for r in rows if r[0] in wanted]

    total = len(rows)
    print(f"Processing {total} guideline(s)...\n")
    grand = 0

    for i, (gid, fn) in enumerate(rows, start=1):
        try:
            n = label_and_store_guideline_acronyms(gid, _display_md(gid))
        except Exception as e:
            print(f"[{i}/{total}] {fn}: ERROR ({e}) — skipped")
            continue
        grand += n
        print(f"[{i}/{total}] {fn}: {n} abbreviation(s)")

    print(f"\nDone. {grand} abbreviation(s) across {total} guideline(s).")


if __name__ == "__main__":
    main()
