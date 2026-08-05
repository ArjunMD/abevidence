"""Convert the Word references under References/ into markdown.

This runs as a build step, not at request time: `python references.py` freezes the
converted text into references_data.py, which is what the app imports. The .docx
files are not deployed, so the app must ship the text with the code.

Re-run it after editing a source document.

Only the constructs these references actually use are supported: heading styles,
bullets, simple tables, and bold/italic runs.
"""

import os
import re
import xml.etree.ElementTree as ET
import zipfile

_ROOT = os.path.dirname(os.path.abspath(__file__))
REFERENCES_DIR = os.path.join(_ROOT, "References")

EMPIRIC_ABX_DOC = os.path.join(REFERENCES_DIR, "EmpiricAbx.docx")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Word heading levels sit under a page that already has its own title and
# subheader, so everything is demoted a couple of levels.
_HEADING_MD = {"Title": "###", "Heading1": "###", "Heading2": "####", "Heading3": "#####"}


def _toggled_on(el) -> bool:
    """A <w:b/>-style toggle is on when present unless explicitly switched off."""
    return el is not None and el.get(f"{_W}val") not in ("0", "false")


def _run_text(run) -> str:
    text = "".join(node.text or "" for node in run.iter(f"{_W}t"))
    if run.find(f"{_W}tab") is not None:
        text += " "
    return text


def _run_format(run) -> tuple[bool, bool]:
    rpr = run.find(f"{_W}rPr")
    if rpr is None:
        return (False, False)
    return (_toggled_on(rpr.find(f"{_W}b")), _toggled_on(rpr.find(f"{_W}i")))


def _emphasize(text: str, bold: bool, italic: bool) -> str:
    body = text.strip()
    if not body or not (bold or italic):
        return text
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    if bold:
        body = f"**{body}**"
    if italic:
        body = f"*{body}*"
    return f"{lead}{body}{trail}"


def _para_text(para, plain: bool = False) -> str:
    """Paragraph as markdown. `plain` drops emphasis — headings are already styled,
    and wrapping them puts '**' inside the '###'.

    Word splits a styled phrase across many runs (revision ids, spell-check marks),
    so runs sharing a format are coalesced first. Emphasising each fragment instead
    yields '*Local antibiogram overrides* *all of* *the above.*'.
    """
    runs = para.findall(f"{_W}r")
    if plain:
        return "".join(_run_text(r) for r in runs).strip()

    groups: list[list] = []
    for run in runs:
        text = _run_text(run)
        if not text:
            continue
        bold, italic = _run_format(run)
        if groups and groups[-1][0] == (bold, italic):
            groups[-1][1] += text
        else:
            groups.append([(bold, italic), text])

    return "".join(_emphasize(text, *fmt) for fmt, text in groups).strip()


# A paragraph starting with one of these reads as a block construct in markdown
# rather than as text. The allergy section opens with ">90% of reported penicillin
# allergies", which would otherwise render as a blockquote.
_BLOCK_STARTERS = (">", "#", "-", "+", "|")


def _escape_block_start(text: str) -> str:
    return f"\\{text}" if text.startswith(_BLOCK_STARTERS) else text


def _para_style(para) -> str:
    ppr = para.find(f"{_W}pPr")
    if ppr is None:
        return ""
    style = ppr.find(f"{_W}pStyle")
    return style.get(f"{_W}val", "") if style is not None else ""


def _list_level(para) -> int | None:
    """Indent level for a numbered/bulleted paragraph, or None if not a list."""
    ppr = para.find(f"{_W}pPr")
    numpr = ppr.find(f"{_W}numPr") if ppr is not None else None
    if numpr is None:
        return None
    ilvl = numpr.find(f"{_W}ilvl")
    try:
        return int(ilvl.get(f"{_W}val", "0")) if ilvl is not None else 0
    except ValueError:
        return 0


def _cell_text(cell) -> str:
    """A table cell flattened to one line — markdown tables cannot hold blocks.
    Pipes would break the row, so they are escaped."""
    parts = [_para_text(p) for p in cell.findall(f"{_W}p")]
    return " ".join(p for p in parts if p).replace("|", "\\|")


def _table_md(table) -> list[str]:
    rows = [[_cell_text(c) for c in tr.findall(f"{_W}tc")] for tr in table.findall(f"{_W}tr")]
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join([" --- "] * width) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return out


def docx_to_markdown(path: str) -> str:
    """Convert a .docx to markdown. Raises FileNotFoundError if it is missing and
    ValueError if the file is not a readable Word document."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        with zipfile.ZipFile(path) as z:
            body_xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError(f"{os.path.basename(path)} is not a readable .docx ({e})") from e

    body = ET.fromstring(body_xml).find(f"{_W}body")
    if body is None:
        return ""

    lines: list[str] = []

    def _gap() -> None:
        """Markdown needs a blank line between blocks; never start with one."""
        if lines and lines[-1] != "":
            lines.append("")

    for child in body:
        if child.tag == f"{_W}tbl":
            _gap()
            lines += _table_md(child)
            _gap()
        elif child.tag == f"{_W}p":
            style = _para_style(child)
            heading = _HEADING_MD.get(style)
            level = _list_level(child)
            if heading:
                _gap()
                text = _para_text(child, plain=True)
                if text:
                    lines.append(f"{heading} {text}")
                    lines.append("")
            elif level is not None:
                text = _para_text(child)
                if text:
                    # Consecutive bullets must stay adjacent to read as one list.
                    if lines and lines[-1] != "" and not lines[-1].lstrip().startswith("- "):
                        lines.append("")
                    lines.append(f"{'  ' * level}- {text}")
            else:
                text = _para_text(child)
                if text:
                    _gap()
                    lines.append(_escape_block_start(text))
                    lines.append("")

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


FROZEN_PATH = os.path.join(_ROOT, "references_data.py")

_FROZEN_HEADER = '''"""Frozen reference text — generated by `python references.py`.

Do not edit by hand. The source of truth is the Word document under References/;
edit that and re-run the command. The text lives here rather than being parsed at
runtime because the .docx files are not deployed with the app.
"""

'''


def _as_literal(text: str) -> str:
    """A triple-quoted literal, kept readable so the generated file still diffs."""
    escaped = text.replace("\\", "\\\\").replace('"""', r"\"\"\"")
    # Line continuations at both ends keep the closing quotes on their own line
    # without adding a leading or trailing newline to the value.
    return f'"""\\\n{escaped}\\\n"""'


def freeze() -> str:
    """Regenerate references_data.py from the Word sources. Returns its path."""
    empiric = docx_to_markdown(EMPIRIC_ABX_DOC)
    with open(FROZEN_PATH, "w", encoding="utf-8") as fh:
        fh.write(_FROZEN_HEADER)
        fh.write(f"EMPIRIC_ABX_MD = {_as_literal(empiric)}\n")
    return FROZEN_PATH


if __name__ == "__main__":
    path = freeze()
    print(f"wrote {path}")
