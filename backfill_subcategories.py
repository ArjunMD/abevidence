"""One-time backfill: split large browse categories into subcategories named
'<Parent> - <Subtopic>' (e.g. 'Atrial fibrillation - Anticoagulation'). One GPT
call per category clusters that category's items by title and reassigns each
item's tag; items that fit no coherent subtopic keep the bare parent tag. New
subcategory names inherit the parent's specialty in category_specialty, so the
browse hierarchy needs no re-classification.

Safe to re-run: a category whose items are already split has too few bare-parent
items left to cross the threshold, and explicit names can always be re-split.

Usage:
    python3 backfill_subcategories.py                 # every category with >= 26 items
    python3 backfill_subcategories.py "Heart failure" # only the named categories
"""
import json
import sys
from collections import Counter

from db import (
    _connect_db,
    ensure_schema,
    get_category_specialties,
    set_category_specialty,
)
from extract import (
    OPENAI_RESPONSES_URL,
    _extract_output_text,
    _openai_api_key,
    _openai_model,
    _post_with_retries,
)

MIN_ITEMS = 26


def _tags(raw: str) -> list[str]:
    return [t.strip() for t in (raw or "").split(",") if t.strip()]


def _all_items() -> list[dict[str, str]]:
    with _connect_db() as conn:
        papers = conn.execute("SELECT pmid, title, category FROM abstracts;").fetchall()
        guides = conn.execute(
            "SELECT guideline_id, COALESCE(NULLIF(guideline_name,''), filename) AS title, category "
            "FROM guidelines;"
        ).fetchall()
    out = [
        {"id": f"p{r['pmid']}", "kind": "p", "key": r["pmid"], "title": r["title"] or "", "category": r["category"] or ""}
        for r in papers
    ]
    out += [
        {"id": f"g{r['guideline_id']}", "kind": "g", "key": r["guideline_id"], "title": r["title"] or "", "category": r["category"] or ""}
        for r in guides
    ]
    return out


def _large_categories(items: list[dict[str, str]]) -> list[str]:
    c: Counter = Counter()
    canon: dict[str, str] = {}
    for it in items:
        for t in _tags(it["category"]):
            key = t.lower()
            canon.setdefault(key, t)
            c[key] += 1
    return sorted(
        (canon[k] for k, n in c.items() if n >= MIN_ITEMS and " - " not in canon[k]),
        key=str.lower,
    )


def gpt_split_category(parent: str, members: list[dict[str, str]]) -> dict[str, str]:
    """Return {item id: '<parent> - <Subtopic>' or ''} for every member."""
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key.")

    listing = "\n".join(f"{m['id']}: {(m['title'] or '')[:150]}" for m in members)
    instructions = (
        "You reorganize one category of a hospital-medicine library into subcategories.\n"
        f"The category is: {parent}. Each input line is 'id: title' of an item in it.\n"
        "Rules:\n"
        f"- Create 3-7 coherent clinical subtopics; name each EXACTLY '{parent} - <Subtopic>' "
        "with <Subtopic> 1-4 words, sentence case (e.g. 'Atrial fibrillation - Anticoagulation', "
        "'Heart failure - Decompensation and diuresis').\n"
        "- Assign every item to the single best subtopic.\n"
        "- Prefer subtopics with at least 3 items; never create a subtopic holding one item.\n"
        '- If an item fits no coherent subtopic, map it to "" (it stays in the parent category).\n'
        "- Output ONLY a JSON object mapping EVERY item id to its subcategory name or \"\"."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": listing + "\n\nReturn the JSON object.",
        "reasoning": {"effort": "low"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 16000,
        "store": False,
    }
    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
        max_attempts=3,
    )
    r.raise_for_status()

    raw = (_extract_output_text(r.json()) or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
        raw = raw.strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object.")

    prefix = f"{parent.lower()} - "
    out: dict[str, str] = {}
    for k, v in data.items():
        v = str(v or "").strip()
        if v and not v.lower().startswith(prefix):
            v = ""  # refuse names that break the '<parent> - X' convention
        out[str(k).strip()] = v
    return out


def _apply(members: list[dict[str, str]], parent: str, mapping: dict[str, str]) -> Counter:
    counts: Counter = Counter()
    with _connect_db() as conn:
        for m in members:
            sub = (mapping.get(m["id"]) or "").strip()
            if not sub:
                counts[f"{parent} (kept)"] += 1
                continue
            # Re-read the CURRENT tags: an earlier category's split in this same run
            # may have already rewritten this item, and applying from the startup
            # snapshot would silently undo that assignment.
            if m["kind"] == "p":
                row = conn.execute("SELECT category FROM abstracts WHERE pmid=?;", (m["key"],)).fetchone()
            else:
                row = conn.execute("SELECT category FROM guidelines WHERE guideline_id=?;", (m["key"],)).fetchone()
            current = (row["category"] if row else m["category"]) or ""
            new_tags = [sub if t.lower() == parent.lower() else t for t in _tags(current)]
            csv = ", ".join(new_tags)
            if m["kind"] == "p":
                conn.execute("UPDATE abstracts SET category=? WHERE pmid=?;", (csv, m["key"]))
            else:
                conn.execute("UPDATE guidelines SET category=? WHERE guideline_id=?;", (csv, m["key"]))
            counts[sub] += 1
    return counts


def main() -> None:
    ensure_schema()
    items = _all_items()

    wanted = [a.strip() for a in sys.argv[1:] if a.strip()]
    targets = wanted or _large_categories(items)
    print(f"Splitting {len(targets)} categories: {targets}\n")

    spec_map = get_category_specialties()

    for parent in targets:
        members = [it for it in items if any(t.lower() == parent.lower() for t in _tags(it["category"]))]
        if not members:
            print(f"== {parent}: no items found — skipped")
            continue
        try:
            mapping = gpt_split_category(parent, members)
        except Exception as e:
            print(f"== {parent}: ERROR ({e}) — skipped")
            continue

        counts = _apply(members, parent, mapping)

        # New subcategories inherit the parent's specialty placement.
        parent_spec = spec_map.get(parent.lower(), "")
        if parent_spec:
            for name in counts:
                if name.lower().startswith(f"{parent.lower()} - "):
                    set_category_specialty(name, parent_spec)

        print(f"== {parent} ({len(members)} items)")
        for name, n in counts.most_common():
            print(f"   {n:3d}  {name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
