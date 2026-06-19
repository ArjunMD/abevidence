"""One-time backfill: label the recommendations in every guideline's grouped
sections (Medicines, Labs, Imaging, Diagnostic procedures, Therapeutic procedures)
with a short subsection name, used to build the per-entity subsections in the
clinician-friendly display.

Operates only on the already-extracted display markdown ("in post") — it does NOT
re-read any source PDF. Safe to re-run; it replaces a guideline's labels each time.

Usage:
    python3 backfill_guideline_rec_labels.py            # all guidelines
    python3 backfill_guideline_rec_labels.py <gid> ...  # specific guideline ids
"""
import sys

from db import _connect_db, ensure_guidelines_schema
from extract import label_and_store_guideline_subsections


def _all_guidelines() -> list[tuple[str, str]]:
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
    labeled = 0

    for i, (gid, fn) in enumerate(rows, start=1):
        md = _display_md(gid)
        try:
            counts = label_and_store_guideline_subsections(gid, md)
        except Exception as e:
            print(f"[{i}/{total}] {fn}: ERROR labeling ({e}) — skipped")
            continue
        if counts:
            labeled += 1
            summary = ", ".join(f"{sec} ({n})" for sec, n in counts.items())
            print(f"[{i}/{total}] {fn}: {summary}")
        else:
            print(f"[{i}/{total}] {fn}: no grouped sections — cleared")

    print(f"\nDone. Labeled {labeled}/{total} guideline(s) with at least one grouped section.")


if __name__ == "__main__":
    main()
