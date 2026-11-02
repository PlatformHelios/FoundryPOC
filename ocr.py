"""OCR a document with Azure Content Understanding.

Usage:
    python ocr.py <path-or-url> [analyzer]

    analyzer defaults to prebuilt-read (plain text OCR). Use prebuilt-layout
    to also get tables, headings and reading order as markdown.

Output: markdown is printed and saved to output/<name>.md, the raw result to output/<name>.json.
"""
import json
import mimetypes
import os
import sys
from pathlib import Path

from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisInput
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

client = ContentUnderstandingClient(
    endpoint=os.environ["CONTENTUNDERSTANDING_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["CONTENTUNDERSTANDING_KEY"]),
)


def ocr_bytes(data: bytes, content_type: str, analyzer: str = "prebuilt-layout"):
    """OCR a file's bytes. Returns (markdown, raw result)."""
    result = client.begin_analyze_binary(analyzer, data, content_type=content_type).result()
    return "\n\n".join(c.markdown or "" for c in result.contents), result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    source = sys.argv[1]
    analyzer = sys.argv[2] if len(sys.argv) > 2 else "prebuilt-read"

    if source.startswith(("http://", "https://")):
        result = client.begin_analyze(analyzer, inputs=[AnalysisInput(url=source)]).result()
        markdown = "\n\n".join(c.markdown or "" for c in result.contents)
        name = Path(source.split("?")[0]).stem
    else:
        content_type = mimetypes.guess_type(source)[0] or "application/octet-stream"
        markdown, result = ocr_bytes(Path(source).read_bytes(), content_type, analyzer)
        name = Path(source).stem

    print(markdown)

    out = Path("output")
    out.mkdir(exist_ok=True)
    (out / f"{name}.md").write_text(markdown, encoding="utf-8")
    (out / f"{name}.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
    print(f"\nSaved output/{name}.md and output/{name}.json", file=sys.stderr)
