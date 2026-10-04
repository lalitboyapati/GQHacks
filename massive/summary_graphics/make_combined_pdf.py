"""Render the combined two-strategy paper(s) -> A4 PDF, two pages each.

    python make_combined_pdf.py                 # builds both versions
    python make_combined_pdf.py combined_writeup_plain.md

Reuses the HTML/CSS pipeline from make_writeup_pdf.py with a denser type
scale and a two-column helper so both strategies fit side by side.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_writeup_pdf import CSS, find_browser, print_pdf  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCES = ["combined_writeup.md", "combined_writeup_plain.md"]

EXTRA_CSS = r"""
@page { margin: 11mm 13mm 12mm 13mm; }
body { font-size: 8.5pt; line-height: 1.34; }
h1 { font-size: 15pt; margin-bottom: 3pt; }
h1 + p { font-size: 7.3pt; margin-bottom: 6pt; padding-bottom: 5pt; }
h2 { font-size: 10.4pt; margin: 8pt 0 3.5pt 0; padding-top: 3pt; }
p { margin: 0 0 3.5pt 0; }
li { margin-bottom: 1.6pt; }
code { font-size: 7.5pt; }
.glance { gap: 5pt; margin: 6pt 0 7pt 0; }
.glance > div { padding: 5pt 6pt 4pt 6pt; min-height: 40pt; }
.glance b { font-size: 11pt; }
.glance span { font-size: 6.6pt; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 10pt; margin: 2pt 0 4pt 0; }
.two > div { break-inside: avoid; }
table { font-size: 7.3pt; margin: 3pt 0 5pt 0; }
th, td { padding: 2.2pt 4pt; line-height: 1.3; }
table td:first-child { width: 9%; font-weight: 600; white-space: nowrap; color: var(--ink2); }
.row { gap: 8pt; margin: 4pt 0 5pt 0; }
figcaption { font-size: 6.8pt; line-height: 1.28; margin-top: 2.5pt; }
.verdict { padding: 5pt 8pt; margin: 5pt 0 0 0; font-size: 8.1pt; }
"""

# The plain-language version carries more words; tighten slightly so it still fits two pages.
PLAIN_CSS = r"""
body { font-size: 8.15pt; line-height: 1.31; }
h1 { font-size: 14pt; }
table { font-size: 7.05pt; }
table td:first-child { white-space: normal; width: 10%; }
figcaption { font-size: 6.6pt; }
.verdict { font-size: 7.8pt; }
"""


def build_html(md_text: str, plain: bool) -> str:
    body = markdown.markdown(md_text, extensions=["tables", "md_in_html", "attr_list"])
    title = re.search(r"<h1>(.*?)</h1>", body)
    title_txt = re.sub(r"<.*?>", "", title.group(1)) if title else "Write-up"
    css = CSS + EXTRA_CSS + (PLAIN_CSS if plain else "")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{title_txt}</title><style>{css}</style></head>"
        f"<body>{body}</body></html>"
    )


def build(md_path: Path, browser: Path) -> None:
    html_path = md_path.with_suffix(".html")
    pdf_path = md_path.with_suffix(".pdf")
    plain = "plain" in md_path.stem
    html_path.write_text(build_html(md_path.read_text(encoding="utf-8"), plain), encoding="utf-8")
    print_pdf(browser, html_path, pdf_path)
    html_path.unlink(missing_ok=True)
    data = pdf_path.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    flag = "" if pages == 2 else f"   <-- WARNING: expected 2 pages"
    print(f"wrote {pdf_path.name}  ({len(data)/1024:.0f} KB, {pages} pages){flag}")


def main() -> None:
    browser = find_browser()
    names = sys.argv[1:] or DEFAULT_SOURCES
    for name in names:
        build(HERE / name, browser)


if __name__ == "__main__":
    main()
