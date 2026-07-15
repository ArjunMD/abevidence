import os

import streamlit as st

from db import create_note, delete_note, list_notes, update_note

# Curated starting list for the required specialty tag — st.multiselect's
# accept_new_options lets the user add more beyond this list.
NOTES_SPECIALTIES = [
    "General",
    "Hospital Medicine",
    "Internal Medicine",
    "Critical Care",
    "Emergency Medicine",
    "Cardiology",
    "Pulmonology",
    "Gastroenterology",
    "Hepatology",
    "Nephrology",
    "Endocrinology/Diabetes",
    "Hematology",
    "Oncology",
    "Infectious Disease",
    "Neurology",
    "Psychiatry",
    "Rheumatology",
    "Surgery",
    "Palliative Care",
]


def _notes_password() -> str:
    """Checks st.secrets first, then the NOTES_PASSWORD env var. Empty means the
    page hasn't been configured yet, in which case access is refused (not opened)."""
    try:
        if "NOTES_PASSWORD" in st.secrets:
            return str(st.secrets["NOTES_PASSWORD"]).strip()
    except Exception:
        pass
    return os.environ.get("NOTES_PASSWORD", "").strip()


def _render_password_gate(configured: str) -> None:
    st.title("🔒 Notes")
    st.caption("Password-protected — may contain excerpts from copyrighted material for personal reference only.")
    with st.form("notes_password_form"):
        candidate = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock")
    if submitted:
        if candidate and candidate == configured:
            st.session_state["notes_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")


def _split_csv(raw: str) -> list[str]:
    out: list[str] = []
    seen = set()
    for tok in (raw or "").split(","):
        t = tok.strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out


def _bullets_from_text(raw: str) -> list[str]:
    out: list[str] = []
    for line in (raw or "").splitlines():
        b = line.strip().lstrip("-•").strip()
        if b:
            out.append(b)
    return out


def _all_existing_tags(notes: list[dict[str, str]]) -> list[str]:
    seen = set()
    out: list[str] = []
    for n in notes:
        for t in _split_csv(n.get("tags") or ""):
            if t.lower() in seen:
                continue
            seen.add(t.lower())
            out.append(t)
    return sorted(out, key=str.lower)


def _render_add_note_form(notes: list[dict[str, str]]) -> None:
    with st.expander("+ Add note", expanded=False):
        heading = st.text_input("Heading (e.g. article title)", key="notes_add_heading")
        source = st.text_input("Source (e.g. URL) — hidden by default in the display", key="notes_add_source")
        content = st.text_area(
            "Bullet points (one per line)", key="notes_add_content", height=220
        )
        specialties = st.multiselect(
            "Specialty (required, choose one or more)",
            options=NOTES_SPECIALTIES,
            key="notes_add_specialties",
            accept_new_options=True,
        )
        tags = st.multiselect(
            "Other tags (optional, e.g. disease names)",
            options=_all_existing_tags(notes),
            key="notes_add_tags",
            accept_new_options=True,
        )
        if st.button("Add note", type="primary"):
            if not heading.strip():
                st.error("Heading is required.")
            elif not specialties:
                st.error("At least one specialty is required.")
            else:
                create_note(
                    title=heading,
                    source=source,
                    content=content,
                    specialties=", ".join(specialties),
                    tags=", ".join(tags),
                )
                for k in [
                    "notes_add_heading",
                    "notes_add_source",
                    "notes_add_content",
                    "notes_add_specialties",
                    "notes_add_tags",
                ]:
                    st.session_state.pop(k, None)
                st.toast("Note added.")
                st.rerun()


def _render_note_section(note: dict[str, str], all_tags: list[str]) -> None:
    note_id = note["note_id"]
    title = note.get("title") or "(untitled)"
    specialties = _split_csv(note.get("specialties") or "")
    tags = _split_csv(note.get("tags") or "")
    bullets = _bullets_from_text(note.get("content") or "")
    source = (note.get("source") or "").strip()

    st.markdown(f"### {title}")
    meta = " · ".join(specialties + tags)
    if meta:
        st.caption(meta)

    if bullets:
        st.markdown("\n".join(f"- {b}" for b in bullets))
    else:
        st.caption("_No bullet points yet._")

    if source:
        with st.expander("Source", expanded=False):
            st.markdown(source)

    with st.expander("Edit", expanded=False):
        with st.form(f"notes_edit_form_{note_id}"):
            new_title = st.text_input("Heading", value=title)
            new_source = st.text_input("Source", value=source)
            new_content = st.text_area(
                "Bullet points (one per line)", value="\n".join(bullets), height=220
            )
            new_specialties = st.multiselect(
                "Specialty (required)",
                options=sorted(set(NOTES_SPECIALTIES) | set(specialties)),
                default=specialties,
                accept_new_options=True,
            )
            new_tags = st.multiselect(
                "Other tags",
                options=sorted(set(all_tags) | set(tags)),
                default=tags,
                accept_new_options=True,
            )
            save_clicked = st.form_submit_button("Save", type="primary")

        if save_clicked:
            if not new_title.strip():
                st.error("Heading is required.")
            elif not new_specialties:
                st.error("At least one specialty is required.")
            else:
                update_note(
                    note_id,
                    new_title,
                    new_source,
                    new_content,
                    ", ".join(new_specialties),
                    ", ".join(new_tags),
                )
                st.toast("Saved.")
                st.rerun()

        confirm_key = f"notes_confirm_delete_{note_id}"
        if not st.session_state.get(confirm_key):
            if st.button("Delete note", key=f"notes_delete_btn_{note_id}"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning("Delete this note? This can't be undone.")
            c_confirm, c_cancel = st.columns(2)
            with c_confirm:
                if st.button("Confirm delete", type="primary", key=f"notes_confirm_btn_{note_id}", use_container_width=True):
                    delete_note(note_id)
                    st.session_state.pop(confirm_key, None)
                    st.toast("Deleted.")
                    st.rerun()
            with c_cancel:
                if st.button("Cancel", key=f"notes_cancel_btn_{note_id}", use_container_width=True):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()

    st.markdown("---")


def render() -> None:
    configured = _notes_password()
    if not configured:
        st.title("🔒 Notes")
        st.warning(
            "No password configured. Add `NOTES_PASSWORD` to `.streamlit/secrets.toml` "
            "(local) or your hosting provider's secrets (deployed) to enable this page."
        )
        return

    if not st.session_state.get("notes_authed"):
        _render_password_gate(configured)
        return

    c_title, c_lock = st.columns([6, 1])
    with c_title:
        st.title("🔒 Notes")
    with c_lock:
        if st.button("Lock", use_container_width=True):
            st.session_state.pop("notes_authed", None)
            st.rerun()

    notes = list_notes()

    search = st.text_input(
        "Search",
        key="notes_search",
        placeholder="Search bullet points… (matching notes are shown in full)",
        label_visibility="collapsed",
    )

    _render_add_note_form(notes)

    q = (search or "").strip().lower()
    if q:
        visible = [
            n for n in notes
            if any(q in b.lower() for b in _bullets_from_text(n.get("content") or ""))
        ]
    else:
        visible = notes

    if not notes:
        st.info("No notes yet. Add one above.")
        return
    if q and not visible:
        st.info(f"No bullet points match “{search}”.")
        return

    all_tags = _all_existing_tags(notes)
    for note in visible:
        _render_note_section(note, all_tags)
