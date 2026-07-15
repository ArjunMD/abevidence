# db.py

import os
import re
import sqlite3
import hashlib
import uuid
from datetime import datetime, timezone

DB_PATH = "data/papers.db"

# ---------------- Local DB paths / connection ----------------

def _db_path() -> str:
    return DB_PATH

def _connect_db() -> sqlite3.Connection:
    path = _db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _utc_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b or b"")
    return h.hexdigest()


# ---------------- Abstracts schema + CRUD ----------------

def _migrate_abstracts_columns(conn: sqlite3.Connection) -> None:
    """In-place schema migration for the abstracts table.

    Renames the legacy `results` column to `outcomes` and adds `evidence_base`.
    Uses ALTER TABLE (no table rebuild), so the pmid primary key and all rows are
    preserved — the saved/hidden detection that SearchPubMed relies on is untouched.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(abstracts);").fetchall()}
    if "results" in cols and "outcomes" not in cols:
        conn.execute("ALTER TABLE abstracts RENAME COLUMN results TO outcomes;")
        cols.discard("results")
        cols.add("outcomes")
    if "outcomes" not in cols:
        conn.execute("ALTER TABLE abstracts ADD COLUMN outcomes TEXT;")
    if "evidence_base" not in cols:
        conn.execute("ALTER TABLE abstracts ADD COLUMN evidence_base TEXT;")


def ensure_schema() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS abstracts (
                pmid TEXT PRIMARY KEY,
                title TEXT,
                abstract TEXT NOT NULL,
                year TEXT,
                pub_month TEXT,
                journal TEXT,
                patient_n INTEGER,
                study_design TEXT,
                patient_details TEXT,
                intervention_comparison TEXT,
                authors_conclusions TEXT,
                outcomes TEXT,
                evidence_base TEXT,
                specialty TEXT,
                uploaded_at TEXT
            );
            """
        )
        _migrate_abstracts_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hidden_pubmed_pmids (
                pmid TEXT PRIMARY KEY,
                hidden_at TEXT NOT NULL,
                journal TEXT,
                year TEXT,
                pub_month TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_pubmed_ledger (
                year_month TEXT NOT NULL,
                specialty_label TEXT NOT NULL DEFAULT '',
                journal_label TEXT NOT NULL,
                study_type_label TEXT NOT NULL,
                total_matches INTEGER NOT NULL,
                visible_matches INTEGER NOT NULL,
                hidden_matches INTEGER NOT NULL,
                is_cleared INTEGER NOT NULL,
                is_verified INTEGER NOT NULL,
                last_checked_at TEXT NOT NULL,
                PRIMARY KEY (year_month, journal_label, study_type_label)
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_search_pubmed_ledger_checked
            ON search_pubmed_ledger(last_checked_at DESC);
            """
        )


def save_record(
    pmid: str,
    title: str,
    abstract: str,
    year: str,
    pub_month: str,
    journal: str,
    patient_n: int | None,
    study_design: str | None,
    patient_details: str | None,
    intervention_comparison: str | None,
    authors_conclusions: str | None,
    outcomes: str | None,
    evidence_base: str | None,
    specialty: str | None,
) -> None:
    uploaded_at = _utc_iso_z()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO abstracts (
                pmid, title, abstract, year, pub_month, journal, patient_n, study_design,
                patient_details, intervention_comparison, authors_conclusions, outcomes,
                evidence_base, specialty, uploaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                pmid,
                title,
                abstract,
                year,
                pub_month,
                journal,
                patient_n,
                study_design,
                patient_details,
                intervention_comparison,
                authors_conclusions,
                outcomes,
                evidence_base,
                specialty,
                uploaded_at,
            ),
        )


def is_saved(pmid: str) -> bool:
    with _connect_db() as conn:
        row = conn.execute("SELECT 1 FROM abstracts WHERE pmid=? LIMIT 1;", (pmid,)).fetchone()
        return row is not None


def get_saved_pmids(pmids: list[str]) -> set[str]:
    vals: list[str] = []
    seen = set()
    for raw in (pmids or []):
        p = str(raw or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        vals.append(p)
    if not vals:
        return set()

    placeholders = ",".join(["?"] * len(vals))
    with _connect_db() as conn:
        rows = conn.execute(
            f"SELECT pmid FROM abstracts WHERE pmid IN ({placeholders});",
            tuple(vals),
        ).fetchall()
    return {(r["pmid"] or "").strip() for r in rows if (r["pmid"] or "").strip()}


def hide_pubmed_pmid(
    pmid: str,
    journal: str | None = None,
    year: str | None = None,
    pub_month: str | None = None,
) -> None:
    p = (pmid or "").strip()
    if not p:
        return
    j = (journal or "").strip() or None
    y = (year or "").strip() or None
    m = (pub_month or "").strip() or None
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO hidden_pubmed_pmids (pmid, hidden_at, journal, year, pub_month)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pmid) DO UPDATE SET
                journal=COALESCE(excluded.journal, hidden_pubmed_pmids.journal),
                year=COALESCE(excluded.year, hidden_pubmed_pmids.year),
                pub_month=COALESCE(excluded.pub_month, hidden_pubmed_pmids.pub_month);
            """,
            (p, _utc_iso_z(), j, y, m),
        )


def unhide_pubmed_pmid(pmid: str) -> None:
    p = (pmid or "").strip()
    if not p:
        return
    with _connect_db() as conn:
        conn.execute("DELETE FROM hidden_pubmed_pmids WHERE pmid = ?;", (p,))


def get_hidden_pubmed_pmids(pmids: list[str]) -> set[str]:
    vals: list[str] = []
    seen = set()
    for raw in (pmids or []):
        p = str(raw or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        vals.append(p)
    if not vals:
        return set()

    placeholders = ",".join(["?"] * len(vals))
    with _connect_db() as conn:
        rows = conn.execute(
            f"SELECT pmid FROM hidden_pubmed_pmids WHERE pmid IN ({placeholders});",
            tuple(vals),
        ).fetchall()
    return {(r["pmid"] or "").strip() for r in rows if (r["pmid"] or "").strip()}


def upsert_search_pubmed_ledger(
    year_month: str,
    specialty_label: str,
    journal_label: str,
    study_type_label: str,
    total_matches: int,
    visible_matches: int,
    hidden_matches: int,
    is_cleared: bool,
    is_verified: bool,
) -> None:
    ym = (year_month or "").strip()
    spec = (specialty_label or "").strip()
    jl = (journal_label or "").strip()
    stype = (study_type_label or "").strip()
    if not ym or not jl or not stype:
        return

    total_i = max(0, int(total_matches or 0))
    visible_i = max(0, int(visible_matches or 0))
    hidden_i = max(0, int(hidden_matches or 0))
    now = _utc_iso_z()

    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO search_pubmed_ledger (
                year_month, specialty_label, journal_label, study_type_label,
                total_matches, visible_matches, hidden_matches,
                is_cleared, is_verified, last_checked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(year_month, journal_label, study_type_label) DO UPDATE SET
                specialty_label=excluded.specialty_label,
                total_matches=excluded.total_matches,
                visible_matches=excluded.visible_matches,
                hidden_matches=excluded.hidden_matches,
                is_cleared=excluded.is_cleared,
                is_verified=excluded.is_verified,
                last_checked_at=excluded.last_checked_at;
            """,
            (
                ym,
                spec,
                jl,
                stype,
                total_i,
                visible_i,
                hidden_i,
                1 if bool(is_cleared) else 0,
                1 if bool(is_verified) else 0,
                now,
            ),
        )


def list_search_pubmed_ledger(limit: int | None = None) -> list[dict[str, str]]:
    with _connect_db() as conn:
        query = """
            SELECT
                year_month,
                specialty_label,
                journal_label,
                study_type_label,
                total_matches,
                visible_matches,
                hidden_matches,
                is_cleared,
                is_verified,
                last_checked_at
            FROM search_pubmed_ledger
            ORDER BY
                specialty_label COLLATE NOCASE ASC,
                journal_label COLLATE NOCASE ASC,
                study_type_label COLLATE NOCASE ASC,
                CAST(SUBSTR(year_month, 1, 4) AS INTEGER) DESC,
                CAST(SUBSTR(year_month, 6, 2) AS INTEGER) ASC
        """
        params: tuple[object, ...] = ()
        try:
            lim = int(limit) if limit is not None else 0
        except Exception:
            lim = 0
        if lim > 0:
            query += "\n            LIMIT ?"
            params = (lim,)
        query += ";"
        rows = conn.execute(query, params).fetchall()

    out: list[dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "year_month": (r["year_month"] or "").strip(),
                "specialty_label": (r["specialty_label"] or "").strip(),
                "journal_label": (r["journal_label"] or "").strip(),
                "study_type_label": (r["study_type_label"] or "").strip(),
                "total_matches": str(int(r["total_matches"] or 0)),
                "visible_matches": str(int(r["visible_matches"] or 0)),
                "hidden_matches": str(int(r["hidden_matches"] or 0)),
                "is_cleared": "1" if int(r["is_cleared"] or 0) == 1 else "0",
                "is_verified": "1" if int(r["is_verified"] or 0) == 1 else "0",
                "last_checked_at": (r["last_checked_at"] or "").strip(),
            }
        )
    return out


def db_count() -> int:
    with _connect_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM abstracts;").fetchone()
        return int(row["c"]) if row else 0


def guidelines_count() -> int:
    with _connect_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM guidelines;").fetchone()
        return int(row["c"]) if row else 0


def db_count_all() -> int:
    with _connect_db() as conn:
        row_p = conn.execute("SELECT COUNT(*) AS c FROM abstracts;").fetchone()
        row_g = conn.execute("SELECT COUNT(*) AS c FROM guidelines;").fetchone()
    papers = int(row_p["c"]) if row_p else 0
    guidelines = int(row_g["c"]) if row_g else 0
    return papers + guidelines


def _parse_search_query_groups(raw: str) -> list[list[str]]:
    """
    Parse a free-text query into OR-groups of AND-terms.
    Supported syntax:
    - AND / OR operators (case-insensitive)
    - quoted phrases for exact substring terms
    - implicit AND between adjacent terms
    """
    s = (raw or "").strip()
    if not s:
        return []

    lex: list[tuple[str, str]] = []
    for m in re.finditer(r'"([^"]+)"|(\S+)', s):
        phrase = m.group(1)
        token = m.group(2)

        if phrase is not None:
            t = re.sub(r"\s+", " ", phrase).strip()
            if t:
                lex.append(("TERM", t))
            continue

        w = (token or "").strip()
        if not w:
            continue
        if re.fullmatch(r"(?i)and|or", w):
            lex.append(("OP", w.upper()))
            continue

        # Keep legacy behavior for unquoted text: split punctuation into terms.
        parts = re.findall(r"[A-Za-z0-9]+", w)
        for p in parts:
            t = (p or "").strip()
            if t:
                lex.append(("TERM", t))

    if not lex:
        return []

    groups: list[list[str]] = []
    current: list[str] = []
    pending_op = "AND"
    for kind, val in lex:
        if kind == "OP":
            pending_op = val
            continue

        if not current:
            current = [val]
        elif pending_op == "OR":
            groups.append(current)
            current = [val]
        else:
            current.append(val)
        pending_op = "AND"

    if current:
        groups.append(current)

    cleaned: list[list[str]] = []
    for g in groups:
        seen = set()
        out: list[str] = []
        for raw_t in g:
            t = (raw_t or "").strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
        if out:
            cleaned.append(out)
    return cleaned


def _build_search_where_sql(groups: list[list[str]], cols: list[str]) -> tuple[str, list[str]]:
    where_parts: list[str] = []
    params: list[str] = []

    for group in (groups or []):
        and_parts: list[str] = []
        for term in (group or []):
            like = f"%{term}%"
            ors = " OR ".join([f"{c} LIKE ?" for c in cols])
            and_parts.append(f"({ors})")
            params.extend([like] * len(cols))
        if and_parts:
            where_parts.append("(" + " AND ".join(and_parts) + ")")

    return " OR ".join(where_parts), params

def search_records(limit: int, q: str) -> list[dict[str, str]]:
    raw = (q or "").strip()
    if not raw:
        return []

    groups = _parse_search_query_groups(raw)
    if not groups:
        return []

    cols = [
        "COALESCE(pmid,'')",
        "COALESCE(title,'')",
        "COALESCE(abstract,'')",
        "COALESCE(year,'')",
        "COALESCE(journal,'')",
        "COALESCE(study_design,'')",
        "COALESCE(patient_details,'')",
        "COALESCE(intervention_comparison,'')",
        "COALESCE(authors_conclusions,'')",
        "COALESCE(outcomes,'')",
        "COALESCE(evidence_base,'')",
        "COALESCE(specialty,'')",
        "COALESCE(CAST(patient_n AS TEXT),'')",
    ]

    where_sql, params = _build_search_where_sql(groups, cols)
    if not where_sql:
        return []

    with _connect_db() as conn:
        rows = conn.execute(
            f"""
            SELECT pmid, title, year, journal, patient_n, study_design, specialty
            FROM abstracts
            WHERE {where_sql}
            ORDER BY
                CASE WHEN year GLOB '[0-9][0-9][0-9][0-9]' THEN year END DESC,
                title COLLATE NOCASE ASC
            LIMIT ?;
            """,
            (*params, int(limit)),
        ).fetchall()

    out: list[dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "pmid": (r["pmid"] or "").strip(),
                "title": (r["title"] or "").strip(),
                "year": (r["year"] or "").strip(),
                "journal": (r["journal"] or "").strip(),
                "patient_n": "" if r["patient_n"] is None else str(int(r["patient_n"])),
                "study_design": (r["study_design"] or "").strip(),
                "specialty": (r["specialty"] or "").strip(),
            }
        )
    return out


def list_browse_items(limit: int) -> list[dict[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT pmid, title, year, pub_month, journal, patient_n, specialty, authors_conclusions, uploaded_at
            FROM abstracts
            ORDER BY
                specialty COLLATE NOCASE ASC,
                CASE WHEN year GLOB '[0-9][0-9][0-9][0-9]' THEN year END DESC,
                title COLLATE NOCASE ASC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()

    out: list[dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "pmid": (r["pmid"] or "").strip(),
                "title": (r["title"] or "").strip(),
                "year": (r["year"] or "").strip(),
                "pub_month": (r["pub_month"] or "").strip(),
                "journal": (r["journal"] or "").strip(),
                "patient_n": str(r["patient_n"] or "").strip(),
                "specialty": (r["specialty"] or "").strip(),
                "authors_conclusions": (r["authors_conclusions"] or "").strip(),
                "uploaded_at": (r["uploaded_at"] or "").strip(),
            }
        )
    return out


def get_record(pmid: str) -> dict[str, str]:
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT pmid, title, abstract, year, pub_month, journal, patient_n, study_design,
                   patient_details, intervention_comparison, authors_conclusions, outcomes,
                   evidence_base, specialty
            FROM abstracts
            WHERE pmid=? LIMIT 1;
            """,
            (pmid,),
        ).fetchone()
        if not row:
            return {}
        return {
            "pmid": (row["pmid"] or "").strip(),
            "title": (row["title"] or "").strip(),
            "abstract": (row["abstract"] or "").strip(),
            "year": (row["year"] or "").strip(),
            "pub_month": (row["pub_month"] or "").strip(),
            "journal": (row["journal"] or "").strip(),
            "patient_n": "" if row["patient_n"] is None else str(int(row["patient_n"])),
            "study_design": (row["study_design"] or "").strip(),
            "patient_details": (row["patient_details"] or "").strip(),
            "intervention_comparison": (row["intervention_comparison"] or "").strip(),
            "authors_conclusions": (row["authors_conclusions"] or "").strip(),
            "outcomes": (row["outcomes"] or "").strip(),
            "evidence_base": (row["evidence_base"] or "").strip(),
            "specialty": (row["specialty"] or "").strip(),
        }


def update_record(
    pmid: str,
    patient_n: int | None,
    study_design: str | None,
    patient_details: str | None,
    intervention_comparison: str | None,
    authors_conclusions: str | None,
    outcomes: str | None,
    evidence_base: str | None,
    specialty: str | None,
) -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            UPDATE abstracts
            SET patient_n = ?,
                study_design = ?,
                patient_details = ?,
                intervention_comparison = ?,
                authors_conclusions = ?,
                outcomes = ?,
                evidence_base = ?,
                specialty = ?
            WHERE pmid = ?;
            """,
            (
                patient_n,
                study_design,
                patient_details,
                intervention_comparison,
                authors_conclusions,
                outcomes,
                evidence_base,
                specialty,
                pmid,
            ),
        )


def delete_record(pmid: str) -> None:
    with _connect_db() as conn:
        conn.execute("DELETE FROM abstracts WHERE pmid=?;", (pmid,))


def list_recent_records(limit: int) -> list[dict[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT pmid, title, year, journal, patient_n, study_design, specialty
            FROM abstracts
            ORDER BY
                CASE WHEN year GLOB '[0-9][0-9][0-9][0-9]' THEN year END DESC,
                title COLLATE NOCASE ASC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()

    out: list[dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "pmid": (r["pmid"] or "").strip(),
                "title": (r["title"] or "").strip(),
                "year": (r["year"] or "").strip(),
                "journal": (r["journal"] or "").strip(),
                "patient_n": "" if r["patient_n"] is None else str(int(r["patient_n"])),
                "study_design": (r["study_design"] or "").strip(),
                "specialty": (r["specialty"] or "").strip(),
            }
        )
    return out


# ---------------- Guidelines storage + schema ----------------

def ensure_guidelines_schema() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guidelines (
                guideline_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL DEFAULT '',
                sha256 TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                guideline_name TEXT,
                pub_year TEXT,
                specialty TEXT,
                society TEXT,
                meta_extracted_at TEXT,
                recommendations_display_md TEXT,
                recommendations_display_updated_at TEXT
            );
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guidelines_sha256_uq ON guidelines(sha256);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_guidelines_uploaded_at ON guidelines(uploaded_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_guidelines_pub_year ON guidelines(pub_year);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_guidelines_specialty ON guidelines(specialty);")
        # Per-recommendation subsection labels for grouped sections (Medicines, Labs,
        # Imaging, Diagnostic procedures, Therapeutic procedures). rec_num is the original
        # (stored) recommendation number in the display markdown, which is globally unique
        # within a guideline and stable across edits/deletes, so it's a durable key.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guideline_rec_labels (
                guideline_id TEXT NOT NULL,
                rec_num INTEGER NOT NULL,
                section TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guideline_id, rec_num)
            );
            """
        )
        # Migrate the legacy medicine-only table into the generic one, then drop it.
        _tbls = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()}
        if "guideline_med_labels" in _tbls:
            conn.execute(
                "INSERT OR IGNORE INTO guideline_rec_labels "
                "(guideline_id, rec_num, section, label, updated_at) "
                "SELECT guideline_id, rec_num, 'Medicines', medicine, updated_at "
                "FROM guideline_med_labels;"
            )
            conn.execute("DROP TABLE guideline_med_labels;")
        # Acronym legend for each guideline's recommendations display.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guideline_acronyms (
                guideline_id TEXT NOT NULL,
                acronym TEXT NOT NULL,
                expansion TEXT NOT NULL,
                uncertain INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guideline_id, acronym)
            );
            """
        )


def find_guideline_by_hash(sha256: str) -> dict[str, str] | None:
    s = (sha256 or "").strip()
    if not s:
        return None
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT guideline_id, filename, sha256, bytes, uploaded_at,
                   guideline_name, pub_year, specialty, society, meta_extracted_at,
                   recommendations_display_md, recommendations_display_updated_at
            FROM guidelines
            WHERE sha256=?
            LIMIT 1;
            """,
            (s,),
        ).fetchone()
        if not row:
            return None
        return {
            "guideline_id": (row["guideline_id"] or "").strip(),
            "filename": (row["filename"] or "").strip(),
            "sha256": (row["sha256"] or "").strip(),
            "bytes": str(int(row["bytes"])) if row["bytes"] is not None else "0",
            "uploaded_at": (row["uploaded_at"] or "").strip(),
            "guideline_name": (row["guideline_name"] or "").strip(),
            "pub_year": (row["pub_year"] or "").strip(),
            "specialty": (row["specialty"] or "").strip(),
            "society": (row["society"] or "").strip(),
            "meta_extracted_at": (row["meta_extracted_at"] or "").strip(),
            "recommendations_display_md": (row["recommendations_display_md"] or "").strip(),
            "recommendations_display_updated_at": (row["recommendations_display_updated_at"] or "").strip(),
        }

def save_guideline_pdf(filename: str, pdf_bytes: bytes) -> dict[str, str]:
    if not pdf_bytes:
        raise ValueError("Empty PDF bytes.")
    fn = (filename or "").strip() or "guideline.pdf"

    sha = _sha256_bytes(pdf_bytes)
    existing = find_guideline_by_hash(sha)
    if existing:
        return existing

    gid = uuid.uuid4().hex
    uploaded_at = _utc_iso_z()
    nbytes = len(pdf_bytes)

    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO guidelines (guideline_id, filename, stored_path, sha256, bytes, uploaded_at)
            VALUES (?, ?, '', ?, ?, ?);
            """,
            (gid, fn, sha, nbytes, uploaded_at),
        )

    return {
        "guideline_id": gid,
        "filename": fn,
        "sha256": sha,
        "bytes": str(nbytes),
        "uploaded_at": uploaded_at,
        "guideline_name": "",
        "pub_year": "",
        "specialty": "",
        "society": "",
        "meta_extracted_at": "",
        "recommendations_display_md": "",
        "recommendations_display_updated_at": "",
    }


def list_guidelines(limit: int) -> list[dict[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT guideline_id, filename, sha256, bytes, uploaded_at,
                   guideline_name, pub_year, specialty, society, meta_extracted_at
            FROM guidelines
            ORDER BY uploaded_at DESC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()

    out: list[dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "guideline_id": (r["guideline_id"] or "").strip(),
                "filename": (r["filename"] or "").strip(),
                "sha256": (r["sha256"] or "").strip(),
                "bytes": str(int(r["bytes"])) if r["bytes"] is not None else "0",
                "uploaded_at": (r["uploaded_at"] or "").strip(),
                "guideline_name": (r["guideline_name"] or "").strip(),
                "pub_year": (r["pub_year"] or "").strip(),
                "specialty": (r["specialty"] or "").strip(),
                "society": (r["society"] or "").strip(),
                "meta_extracted_at": (r["meta_extracted_at"] or "").strip(),
            }
        )
    return out

def delete_guideline(guideline_id: str) -> None:
    gid = (guideline_id or "").strip()
    if not gid:
        return
    with _connect_db() as conn:
        conn.execute("DELETE FROM guidelines WHERE guideline_id=?;", (gid,))


# ---------------- Guideline layout markdown cache ----------------

def get_guideline_meta(guideline_id: str) -> dict[str, str]:
    gid = (guideline_id or "").strip()
    if not gid:
        return {}
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT guideline_id, filename, sha256, uploaded_at, bytes,
                   guideline_name, pub_year, specialty, society, meta_extracted_at
            FROM guidelines
            WHERE guideline_id=? LIMIT 1;
            """,
            (gid,),
        ).fetchone()
        if not row:
            return {}
        return {
            "guideline_id": (row["guideline_id"] or "").strip(),
            "filename": (row["filename"] or "").strip(),
            "sha256": (row["sha256"] or "").strip(),
            "uploaded_at": (row["uploaded_at"] or "").strip(),
            "bytes": str(int(row["bytes"])) if row["bytes"] is not None else "0",
            "guideline_name": (row["guideline_name"] or "").strip(),
            "pub_year": (row["pub_year"] or "").strip(),
            "specialty": (row["specialty"] or "").strip(),
            "society": (row["society"] or "").strip(),
            "meta_extracted_at": (row["meta_extracted_at"] or "").strip(),
        }


def get_guideline_recommendations_display(guideline_id: str) -> str:
    gid = (guideline_id or "").strip()
    if not gid:
        return ""
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT recommendations_display_md FROM guidelines WHERE guideline_id=? LIMIT 1;",
            (gid,),
        ).fetchone()
        if not row:
            return ""
        return (row["recommendations_display_md"] or "").strip()


def update_guideline_recommendations_display(guideline_id: str, markdown: str) -> None:
    gid = (guideline_id or "").strip()
    if not gid:
        return
    md = (markdown or "").strip()
    now = _utc_iso_z()
    with _connect_db() as conn:
        conn.execute(
            """
            UPDATE guidelines
            SET recommendations_display_md=?, recommendations_display_updated_at=?
            WHERE guideline_id=?;
            """,
            (md, now, gid),
        )


def get_guideline_rec_labels(guideline_id: str) -> dict[int, str]:
    """Return {rec_num: label} for the guideline's grouped-section subsection labels.
    rec_num is globally unique within a guideline, so the flat map is unambiguous."""
    gid = (guideline_id or "").strip()
    if not gid:
        return {}
    with _connect_db() as conn:
        rows = conn.execute(
            "SELECT rec_num, label FROM guideline_rec_labels WHERE guideline_id=?;",
            (gid,),
        ).fetchall()
    out: dict[int, str] = {}
    for r in rows:
        lab = (r["label"] or "").strip()
        if lab:
            out[int(r["rec_num"])] = lab
    return out


def set_guideline_rec_labels(guideline_id: str, rows: list[tuple[int, str, str]]) -> None:
    """Replace all subsection labels for a guideline.
    rows: iterable of (rec_num, section, label)."""
    gid = (guideline_id or "").strip()
    if not gid:
        return
    now = _utc_iso_z()
    cleaned = [
        (gid, int(n), (section or "").strip(), str(label).strip(), now)
        for (n, section, label) in (rows or [])
        if str(label or "").strip()
    ]
    with _connect_db() as conn:
        conn.execute("DELETE FROM guideline_rec_labels WHERE guideline_id=?;", (gid,))
        if cleaned:
            conn.executemany(
                "INSERT OR REPLACE INTO guideline_rec_labels "
                "(guideline_id, rec_num, section, label, updated_at) VALUES (?, ?, ?, ?, ?);",
                cleaned,
            )


def get_guideline_acronyms(guideline_id: str) -> list[tuple[str, str, bool]]:
    """Return [(acronym, expansion, uncertain)] for a guideline's legend,
    sorted case-insensitively by acronym."""
    gid = (guideline_id or "").strip()
    if not gid:
        return []
    with _connect_db() as conn:
        rows = conn.execute(
            "SELECT acronym, expansion, uncertain FROM guideline_acronyms WHERE guideline_id=?;",
            (gid,),
        ).fetchall()
    out = [
        ((r["acronym"] or "").strip(), (r["expansion"] or "").strip(), bool(r["uncertain"]))
        for r in rows
        if (r["acronym"] or "").strip() and (r["expansion"] or "").strip()
    ]
    out.sort(key=lambda t: t[0].lower())
    return out


def set_guideline_acronyms(guideline_id: str, rows: list[tuple[str, str, bool]]) -> None:
    """Replace all acronym entries for a guideline.
    rows: iterable of (acronym, expansion, uncertain)."""
    gid = (guideline_id or "").strip()
    if not gid:
        return
    now = _utc_iso_z()
    cleaned = [
        (gid, (acr or "").strip(), str(exp).strip(), 1 if uncertain else 0, now)
        for (acr, exp, uncertain) in (rows or [])
        if (acr or "").strip() and str(exp or "").strip()
    ]
    with _connect_db() as conn:
        conn.execute("DELETE FROM guideline_acronyms WHERE guideline_id=?;", (gid,))
        if cleaned:
            conn.executemany(
                "INSERT OR REPLACE INTO guideline_acronyms "
                "(guideline_id, acronym, expansion, uncertain, updated_at) VALUES (?, ?, ?, ?, ?);",
                cleaned,
            )


# ---------------- Guideline recommendations + review state ----------------

def update_guideline_metadata(
    guideline_id: str,
    guideline_name: str | None,
    pub_year: str | None,
    specialty: str | None,
    society: str | None = None,
) -> None:
    gid = (guideline_id or "").strip()
    if not gid:
        return
    now = _utc_iso_z()

    name = (guideline_name or "").strip() or None
    year = (pub_year or "").strip() or None
    spec = (specialty or "").strip() or None
    soc = (society or "").strip() or None

    with _connect_db() as conn:
        conn.execute(
            """
            UPDATE guidelines
            SET guideline_name=?, pub_year=?, specialty=?, society=?, meta_extracted_at=?
            WHERE guideline_id=?;
            """,
            (name, year, spec, soc, now, gid),
        )


# ---------------- Guideline browse/search ----------------

def list_browse_guideline_items(limit: int) -> list[dict[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT
                guideline_id,
                COALESCE(NULLIF(guideline_name,''), filename) AS title,
                COALESCE(pub_year,'') AS year,
                COALESCE(specialty,'') AS specialty,
                COALESCE(society,'') AS society,
                COALESCE(uploaded_at,'') AS uploaded_at
            FROM guidelines
            ORDER BY
                specialty COLLATE NOCASE ASC,
                CASE WHEN pub_year GLOB '[0-9][0-9][0-9][0-9]' THEN pub_year END DESC,
                title COLLATE NOCASE ASC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()

    out: list[dict[str, str]] = []
    for r in rows:
        out.append(
            {
                "type": "guideline",
                "guideline_id": (r["guideline_id"] or "").strip(),
                "title": (r["title"] or "").strip(),
                "year": (r["year"] or "").strip(),
                "specialty": (r["specialty"] or "").strip(),
                "society": (r["society"] or "").strip(),
                "uploaded_at": (r["uploaded_at"] or "").strip(),
            }
        )
    return out

def search_guidelines(limit: int, q: str) -> list[dict[str, str]]:
    raw = (q or "").strip()
    if not raw:
        return []

    groups = _parse_search_query_groups(raw)
    if not groups:
        return []

    gcols = [
        "COALESCE(g.guideline_name,'')",
        "COALESCE(g.filename,'')",
        "COALESCE(g.pub_year,'')",
        "COALESCE(g.specialty,'')",
        "COALESCE(g.society,'')",
        "COALESCE(g.recommendations_display_md,'')",
    ]

    where_sql, params = _build_search_where_sql(groups, gcols)
    if not where_sql:
        return []

    with _connect_db() as conn:
        rows = conn.execute(
            f"""
            SELECT
                g.guideline_id,
                COALESCE(NULLIF(g.guideline_name,''), g.filename) AS title,
                COALESCE(g.pub_year,'') AS year,
                COALESCE(g.specialty,'') AS specialty,
                COALESCE(g.society,'') AS society
            FROM guidelines g
            WHERE {where_sql}
            ORDER BY
                CASE WHEN g.pub_year GLOB '[0-9][0-9][0-9][0-9]' THEN g.pub_year END DESC,
                title COLLATE NOCASE ASC
            LIMIT ?;
            """,
            (*params, int(limit)),
        ).fetchall()

    gout: list[dict[str, str]] = []
    for r in rows:
        gout.append(
            {
                "type": "guideline",
                "guideline_id": (r["guideline_id"] or "").strip(),
                "title": (r["title"] or "").strip(),
                "year": (r["year"] or "").strip(),
                "specialty": (r["specialty"] or "").strip(),
                "society": (r["society"] or "").strip(),
            }
        )
    return gout


# ---------------- Dashboard queries ----------------

def dashboard_saved_per_journal() -> list[dict[str, object]]:
    with _connect_db() as conn:
        rows = conn.execute(
            "SELECT journal, COUNT(*) AS cnt FROM abstracts GROUP BY journal ORDER BY cnt DESC;"
        ).fetchall()
    return [{"journal": (r["journal"] or "").strip() or "Unknown", "count": int(r["cnt"])} for r in rows]


def dashboard_hidden_per_journal() -> list[dict[str, object]]:
    with _connect_db() as conn:
        rows = conn.execute(
            "SELECT journal, COUNT(*) AS cnt FROM hidden_pubmed_pmids GROUP BY journal ORDER BY cnt DESC;"
        ).fetchall()
    return [{"journal": (r["journal"] or "").strip() or "Unknown", "count": int(r["cnt"])} for r in rows]


def dashboard_study_design_distribution() -> list[dict[str, object]]:
    with _connect_db() as conn:
        rows = conn.execute(
            "SELECT study_design, COUNT(*) AS cnt FROM abstracts GROUP BY study_design ORDER BY cnt DESC;"
        ).fetchall()
    return [{"study_design": (r["study_design"] or "").strip() or "Not specified", "count": int(r["cnt"])} for r in rows]


def dashboard_saved_specialties() -> list[dict[str, object]]:
    with _connect_db() as conn:
        rows = conn.execute("SELECT specialty FROM abstracts;").fetchall()
    return [{"specialty": (r["specialty"] or "").strip()} for r in rows]


# ---------------- Notes schema + CRUD ----------------
# Password-gated personal notes page (see ui_pages/page_notes.py) — may contain
# excerpts pasted from copyrighted material, so this table is never exposed
# through any public-mode page or query-param deep link.

def _migrate_notes_columns(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(notes);").fetchall()}
    if "source" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN source TEXT NOT NULL DEFAULT '';")
    if "specialties" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN specialties TEXT NOT NULL DEFAULT '';")
    if "tags" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN tags TEXT NOT NULL DEFAULT '';")


def ensure_notes_schema() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _migrate_notes_columns(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at);")


def _note_row_to_dict(r: sqlite3.Row) -> dict[str, str]:
    return {
        "note_id": (r["note_id"] or "").strip(),
        "title": (r["title"] or "").strip(),
        "source": (r["source"] or "").strip(),
        "content": r["content"] or "",
        "specialties": (r["specialties"] or "").strip(),
        "tags": (r["tags"] or "").strip(),
        "created_at": (r["created_at"] or "").strip(),
        "updated_at": (r["updated_at"] or "").strip(),
    }


_NOTES_SELECT_COLS = "note_id, title, source, content, specialties, tags, created_at, updated_at"


def list_notes() -> list[dict[str, str]]:
    with _connect_db() as conn:
        rows = conn.execute(
            f"SELECT {_NOTES_SELECT_COLS} FROM notes ORDER BY updated_at DESC;"
        ).fetchall()
    return [_note_row_to_dict(r) for r in rows]


def get_note(note_id: str) -> dict[str, str]:
    nid = (note_id or "").strip()
    if not nid:
        return {}
    with _connect_db() as conn:
        row = conn.execute(
            f"SELECT {_NOTES_SELECT_COLS} FROM notes WHERE note_id=? LIMIT 1;",
            (nid,),
        ).fetchone()
    if not row:
        return {}
    return _note_row_to_dict(row)


def create_note(
    title: str = "", source: str = "", content: str = "", specialties: str = "", tags: str = ""
) -> dict[str, str]:
    nid = uuid.uuid4().hex
    now = _utc_iso_z()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO notes (note_id, title, source, content, specialties, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (nid, (title or "").strip(), (source or "").strip(), content or "", specialties or "", tags or "", now, now),
        )
    return {
        "note_id": nid,
        "title": (title or "").strip(),
        "source": (source or "").strip(),
        "content": content or "",
        "specialties": specialties or "",
        "tags": tags or "",
        "created_at": now,
        "updated_at": now,
    }


def update_note(note_id: str, title: str, source: str, content: str, specialties: str, tags: str) -> None:
    nid = (note_id or "").strip()
    if not nid:
        return
    with _connect_db() as conn:
        conn.execute(
            """
            UPDATE notes SET title=?, source=?, content=?, specialties=?, tags=?, updated_at=?
            WHERE note_id=?;
            """,
            ((title or "").strip(), (source or "").strip(), content or "", specialties or "", tags or "", _utc_iso_z(), nid),
        )


def delete_note(note_id: str) -> None:
    nid = (note_id or "").strip()
    if not nid:
        return
    with _connect_db() as conn:
        conn.execute("DELETE FROM notes WHERE note_id=?;", (nid,))


