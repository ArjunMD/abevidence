from pathlib import Path

import streamlit as st


def render() -> None:
    st.title("ℹ️ About")

    readme_path_candidates = [
        Path(__file__).resolve().parent.parent / "README.md",
        Path("README.md"),
    ]

    md = ""
    for p in readme_path_candidates:
        try:
            if p.exists() and p.is_file():
                md = p.read_text(encoding="utf-8", errors="ignore")
                break
        except Exception:
            pass

    if not md.strip():
        st.warning(
            "README.md wasn't found next to app.py. "
            "Make sure README.md is committed to the repo root so it can be shown here."
        )
        return

    st.markdown(md)
