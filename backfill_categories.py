"""One-time backfill: assign browse categories (diagnoses, imaging modalities,
principles of care, …) to every saved abstract and guideline. Categories power the
Browse studies "Browse by category" view; a paper may carry several.

Runs SEQUENTIALLY on purpose: each call is fed the category vocabulary accumulated
so far (db.get_all_categories), so later papers are filed under the names earlier
papers established instead of coining near-duplicates.

Safe to re-run — rows that already have a category are skipped.

Usage:
    python3 backfill_categories.py            # all abstracts + guidelines missing a category
    python3 backfill_categories.py <pmid> ... # only these PMIDs (re-extracts even if set)
"""
import sys

from db import _connect_db, ensure_guidelines_schema, ensure_schema, get_all_categories
from extract import gpt_extract_categories


def _abstract_rows(only_pmids: set[str]) -> list[dict[str, str]]:
    with _connect_db() as conn:
        if only_pmids:
            placeholders = ",".join(["?"] * len(only_pmids))
            rows = conn.execute(
                f"SELECT pmid, title, abstract FROM abstracts WHERE pmid IN ({placeholders}) "
                "ORDER BY uploaded_at ASC;",
                tuple(only_pmids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT pmid, title, abstract FROM abstracts "
                "WHERE COALESCE(TRIM(category),'') = '' "
                "ORDER BY uploaded_at ASC;"
            ).fetchall()
    return [
        {"pmid": r["pmid"] or "", "title": r["title"] or "", "abstract": r["abstract"] or ""}
        for r in rows
    ]


def _guideline_rows() -> list[dict[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT guideline_id,
                   COALESCE(NULLIF(guideline_name,''), filename) AS name,
                   COALESCE(society,'') AS society,
                   COALESCE(specialty,'') AS specialty,
                   COALESCE(recommendations_display_md,'') AS md
            FROM guidelines
            WHERE COALESCE(TRIM(category),'') = ''
            ORDER BY uploaded_at ASC;
            """
        ).fetchall()
    return [
        {
            "guideline_id": r["guideline_id"] or "",
            "name": r["name"] or "",
            "society": r["society"] or "",
            "specialty": r["specialty"] or "",
            "md": r["md"] or "",
        }
        for r in rows
    ]


def _set_abstract_category(pmid: str, category: str) -> None:
    with _connect_db() as conn:
        conn.execute("UPDATE abstracts SET category=? WHERE pmid=?;", (category, pmid))


def _set_guideline_category(gid: str, category: str) -> None:
    with _connect_db() as conn:
        conn.execute("UPDATE guidelines SET category=? WHERE guideline_id=?;", (category, gid))


def main() -> None:
    ensure_schema()
    ensure_guidelines_schema()

    only_pmids = {a.strip() for a in sys.argv[1:] if a.strip()}

    abstracts = _abstract_rows(only_pmids)
    guidelines = [] if only_pmids else _guideline_rows()
    total = len(abstracts) + len(guidelines)
    print(f"Processing {len(abstracts)} abstract(s) + {len(guidelines)} guideline(s)...\n")

    done = 0
    failed = 0

    for r in abstracts:
        done += 1
        pmid = r["pmid"]
        try:
            cat = gpt_extract_categories(r["title"], r["abstract"], get_all_categories())
        except Exception as e:
            failed += 1
            print(f"[{done}/{total}] PMID {pmid}: ERROR ({e}) — skipped", flush=True)
            continue
        if cat:
            _set_abstract_category(pmid, cat)
        print(f"[{done}/{total}] PMID {pmid}: {cat or '(none)'}", flush=True)

    for r in guidelines:
        done += 1
        gid = r["guideline_id"]
        # No abstract for a guideline — give the extractor the name/society plus the
        # start of the recommendations display as topical context.
        context_bits = [b for b in [r["society"], r["specialty"]] if b]
        context = (", ".join(context_bits) + "\n\n" if context_bits else "") + r["md"][:1500]
        try:
            cat = gpt_extract_categories(r["name"], context, get_all_categories())
        except Exception as e:
            failed += 1
            print(f"[{done}/{total}] Guideline {r['name'][:60]}: ERROR ({e}) — skipped", flush=True)
            continue
        if cat:
            _set_guideline_category(gid, cat)
        print(f"[{done}/{total}] Guideline {r['name'][:60]}: {cat or '(none)'}", flush=True)

    vocab = get_all_categories()
    print(f"\nDone. {done - failed}/{total} categorized, {failed} failed.")
    print(f"Vocabulary now has {len(vocab)} categories.")


if __name__ == "__main__":
    main()
