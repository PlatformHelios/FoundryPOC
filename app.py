"""Web app: upload a document and review it against POC/rules.yaml.

Run:
    pip install -r requirements.txt
    az login
    python -m uvicorn app:app --reload        # then open http://127.0.0.1:8000

Each upload costs one OCR call (Content Understanding) plus one model call per rule.
"""
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from ocr import ocr_bytes
from review import load_rules, number_pages, review_rule

RULES_FOLDER = Path("POC")
MAX_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

app = FastAPI(title="Document Review POC")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Document Review</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
  th, td {{ border: 1px solid #ddd; padding: .5rem; text-align: left; vertical-align: top; }}
  th {{ background: #f4f4f4; }}
  .pass {{ color: #1a7f37; font-weight: 600; }} .fail {{ color: #cf222e; font-weight: 600; }} .unsure {{ color: #9a6700; font-weight: 600; }}
  blockquote {{ margin: 0 0 .4rem; color: #555; font-style: italic; }}
  button {{ padding: .5rem 1rem; }}
</style></head>
<body>
<h1>Document Review</h1>
<form action="/review" method="post" enctype="multipart/form-data"
      onsubmit="this.querySelector('button').disabled=true; this.querySelector('button').textContent='Reviewing… (about a minute)';">
  <input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff" required>
  <button type="submit">Review</button>
</form>
{body}
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    rules = load_rules(RULES_FOLDER)
    items = "".join(f"<li><b>{escape(r['id'])}</b> {escape(r['name'])}</li>" for r in rules)
    return PAGE.format(body=f"<h2>Rules checked</h2><ul>{items}</ul>")


@app.post("/review", response_class=HTMLResponse)
def review(file: UploadFile):
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0]
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {content_type}. Upload a PDF or image.")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "File is larger than 20 MB.")

    markdown, _ = ocr_bytes(data, content_type)
    document = number_pages(markdown)
    rules = load_rules(RULES_FOLDER)
    with ThreadPoolExecutor(max_workers=5) as pool:
        answers = list(pool.map(lambda rule: review_rule(rule, document), rules))

    counts = {v: sum(a["verdict"] == v for a in answers) for v in ("pass", "fail", "unsure")}
    rows = "".join(
        f"<tr><td><b>{escape(r['id'])}</b> {escape(r['name'])}</td>"
        f"<td class='{a['verdict']}'>{a['verdict'].upper()}</td>"
        f"<td>{a['page']}</td>"
        f"<td><blockquote>“{escape(a['evidence'])}”</blockquote>{escape(a['reasoning'])}</td></tr>"
        for r, a in zip(rules, answers)
    )
    body = (
        f"<h2>{escape(file.filename or 'Document')}</h2>"
        f"<p>{counts['pass']} pass · {counts['fail']} fail · {counts['unsure']} unsure</p>"
        f"<table><tr><th>Rule</th><th>Verdict</th><th>Page</th><th>Evidence &amp; reasoning</th></tr>{rows}</table>"
    )
    return PAGE.format(body=body)
