from typing import List, Tuple

import streamlit as st

from db import list_abstracts_for_history, list_guidelines
from pages_shared import _format_date_added


def render() -> None:
    st.title("📅 History")
    limit = 500
    abstracts = list_abstracts_for_history(limit=limit)
    guidelines = list_guidelines(limit=limit)

    rows: List[Tuple[str, str, str, str]] = []
    for it in abstracts:
        raw = (it.get("uploaded_at") or "").strip()
        rows.append((raw or "0000", _format_date_added(raw), "Abstract", (it.get("title") or "").strip() or "(no title)"))
    for it in guidelines:
        raw = (it.get("uploaded_at") or "").strip()
        title = (it.get("guideline_name") or it.get("filename") or "").strip() or "(no name)"
        rows.append((raw or "0000", _format_date_added(raw), "Guideline", title))

    rows.sort(key=lambda r: r[0], reverse=True)
    if not rows:
        st.markdown("Nothing added yet.")
        return

    lines = [f"- **{r[1]}** · {r[2]} · {r[3]}" for r in rows]
    st.markdown("\n".join(lines))
