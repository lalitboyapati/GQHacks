"""Render writeup.md -> writeup.pdf (A4) via styled HTML + headless Chrome/Edge.

- Figure paths in the markdown point at ``figures/<name>.png``; the PNGs live in
  this folder, so the paths are rewritten.
- Additional figures that exist in this folder are slotted into the sections
  they illustrate (classifier, strategy-vs-placebo, hedge cost).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
MD = HERE / "writeup.md"
HTML = HERE / "writeup.html"
PDF = HERE / "writeup.pdf"

BROWSERS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]

CSS = r"""
@page { size: A4; margin: 14mm 15mm 15mm 15mm; }
:root {
  --ink: #1b2430; --ink2: #2f3a48; --muted: #66727f; --rule: #d9dfe6;
  --panel: #f4f6f9; --accent: #1f6f9f; --accent2: #c2571a; --good: #2e7d5b; --bad: #a33a3a;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  color: var(--ink); font-size: 9.1pt; line-height: 1.38;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 { font-size: 17pt; line-height: 1.2; margin: 0 0 4pt 0; letter-spacing: -0.01em; color: var(--ink); }
h1 + p { color: var(--muted); font-size: 7.9pt; line-height: 1.35; margin: 0 0 8pt 0;
         padding-bottom: 7pt; border-bottom: 2px solid var(--accent2); }
h2 { font-size: 11.6pt; margin: 12pt 0 5pt 0; padding-top: 4pt; color: var(--ink);
     border-top: 1px solid var(--rule); break-after: avoid; }
h2:first-of-type { border-top: none; }
h3 { font-size: 9.8pt; margin: 9pt 0 3pt 0; color: var(--accent); break-after: avoid; }
p { margin: 0 0 5pt 0; }
ul, ol { margin: 0 0 5pt 0; padding-left: 15pt; }
li { margin: 0 0 2.4pt 0; }
li::marker { color: var(--accent2); }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.2pt; background: var(--panel);
       padding: 0 2.5pt; border-radius: 2pt; color: var(--ink2); }
b, strong { color: var(--ink); }
em { color: var(--ink2); }

/* glance chips */
.glance { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6pt; margin: 8pt 0 10pt 0; }
.glance > div { background: var(--panel); border: 1px solid var(--rule); border-radius: 4pt;
                padding: 6pt 7pt 5pt 7pt; min-height: 44pt; }
.glance b { display: block; font-size: 12.5pt; color: var(--accent2); line-height: 1.1; margin-bottom: 2pt; }
.glance span { display: block; font-size: 7.1pt; color: var(--muted); line-height: 1.25; }

/* tables */
table { border-collapse: collapse; width: 100%; margin: 4pt 0 6pt 0; font-size: 7.9pt; break-inside: avoid; }
th, td { padding: 2.6pt 4.5pt; vertical-align: top; border-bottom: 1px solid var(--rule); text-align: left; }
th { background: var(--panel); color: var(--ink2); font-weight: 600; border-bottom: 1.5px solid #c3ccd6; }
tr:last-child td { border-bottom: 1.5px solid #c3ccd6; }
table td:first-child { color: var(--ink2); }
/* method table: two columns, first narrow */
table.kv td:first-child { width: 14%; font-weight: 600; white-space: nowrap; }
/* numeric result table */
table.num th, table.num td { text-align: right; white-space: nowrap; }
table.num th:first-child, table.num td:first-child { text-align: left; white-space: normal; width: 34%; }

/* figures */
figure { margin: 0; break-inside: avoid; }
figure img { width: 100%; height: auto; display: block; border: 1px solid var(--rule); border-radius: 3pt; }
figcaption { font-size: 7.3pt; color: var(--muted); line-height: 1.3; margin-top: 3pt; }
figcaption b { color: var(--ink); }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 9pt; margin: 6pt 0 8pt 0; break-inside: avoid; }
.row.wide-left { grid-template-columns: 1.25fr 1fr; }
.row.wide-right { grid-template-columns: 1fr 1.4fr; }
figure.solo { width: 84%; margin: 6pt auto 8pt auto; }

/* verdict */
.verdict { border-left: 4px solid var(--accent2); background: #fff7f1; padding: 6pt 9pt; margin: 6pt 0 8pt 0;
           border-radius: 0 4pt 4pt 0; break-inside: avoid; }
.verdict p { margin: 0; }

.note { font-size: 7.6pt; color: var(--muted); }
"""

EXTRA_FIGS = {
    # end of §3.1
    "### 3.2": """
<div class="row wide-right">
<figure><img src="sentiment_vs_r0.png"><figcaption><b>Fig. A · Classifier vs tape.</b> Jev's five-level sentiment against the day-0 move (pre-news close → entry close), 586 new readouts, LOWESS overlaid. Monotone, with the extremes doing most of the work.</figcaption></figure>
<figure><img src="paths_by_size.png"><figcaption><b>Fig. B · Dose-response.</b> Cumulative paths by sentiment for micro-, small- and mid+-cap readouts, plus stale readouts as the placebo arm: the jump scales with concentration and vanishes when the data were already public.</figcaption></figure>
</div>
""",
    # end of §3.2
    "### 3.3": """
<div class="row">
<figure><img src="trade_layer_vs_placebo.png"><figcaption><b>Fig. C · Trade layer vs ordinary days.</b> Mean P&amp;L of the directional book, unhedged and hedged, against placebo sessions on the same names (95% bands). Nothing separates from placebo before the hedge expires.</figcaption></figure>
<figure><img src="portfolio_equity.png"><figcaption><b>Fig. D · Calendar-time equity.</b> The hedged in-sample book under the time stop and the rule exit, with open positions shaded. A handful of concurrent names drives the path.</figcaption></figure>
</div>
""",
    # end of §3.3
    "### 3.4": """
<figure class="solo"><img src="iv_crush.png"><figcaption><b>Fig. E · The hedge is cheaper after the news.</b> Left: percentage change in ATM implied vol from <code>t_pre</code> to <code>t_0</code> (down in 65% of readouts). Right: same-strike ATM straddle as a share of spot before vs after; points below the diagonal are cheaper hedges once the result is out.</figcaption></figure>
""",
}


def find_browser() -> Path:
    for p in BROWSERS:
        if p.exists():
            return p
    sys.exit("No Chrome/Edge found for PDF printing.")


def build_html(md_text: str) -> str:
    # figures live beside the markdown, not under figures/
    md_text = md_text.replace('src="figures/', 'src="')

    # drop extra figure blocks in just before the next section heading
    for heading, block in EXTRA_FIGS.items():
        idx = md_text.find(heading)
        if idx != -1:
            md_text = md_text[:idx] + block + "\n" + md_text[idx:]

    html_body = markdown.markdown(md_text, extensions=["tables", "md_in_html", "attr_list"])

    # tag the two tables so CSS can lay them out differently
    tables = re.findall(r"<table>", html_body)
    if len(tables) >= 1:
        html_body = html_body.replace("<table>", '<table class="kv">', 1)
    if len(tables) >= 2:
        html_body = html_body.replace("<table>", '<table class="num">', 1)

    title = re.search(r"<h1>(.*?)</h1>", html_body)
    title_txt = re.sub(r"<.*?>", "", title.group(1)) if title else "Write-up"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title_txt}</title>
<style>{CSS}</style></head>
<body>{html_body}</body></html>"""


def print_pdf(browser: Path, html_path: Path, pdf_path: Path) -> None:
    url = html_path.resolve().as_uri()
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def main() -> None:
    browser = find_browser()
    HTML.write_text(build_html(MD.read_text(encoding="utf-8")), encoding="utf-8")
    print_pdf(browser, HTML, PDF)
    data = PDF.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    print(f"wrote {PDF}  ({len(data)/1024:.0f} KB, {pages} pages)  via {browser.name}")


if __name__ == "__main__":
    main()
