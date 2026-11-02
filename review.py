"""Review a document against rules.yaml with a Foundry model, then score against answer_key.yaml.

Usage:
    python review.py [folder]      # folder defaults to POC

The folder must contain rules.yaml, answer_key.yaml and the document named in the answer key.
OCR output is cached in output/<name>.md so re-runs only call the model.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

INSTRUCTIONS = """You review loan documents against a single rule.
Decide whether the document passes or fails the rule, or answer "unsure" if the document does not give enough information.
Check every place the rule applies; do arithmetic yourself rather than trusting stated totals.
Evidence must be an exact quote copied from the document, and page is the PAGE number the quote is on."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail", "unsure"]},
        "evidence": {"type": "string"},
        "page": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["verdict", "evidence", "page", "reasoning"],
    "additionalProperties": False,
}

project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential())
openai = project.get_openai_client()
model = os.getenv("FOUNDRY_MODEL", "gpt-5-mini")


def load_rules(folder: Path) -> list[dict]:
    return yaml.safe_load((folder / "rules.yaml").read_text(encoding="utf-8"))["rules"]


def number_pages(markdown: str) -> str:
    """Label each OCR page so the model can cite page numbers."""
    pages = markdown.split("<!-- PageBreak -->")
    return "\n\n".join(f"===== PAGE {i} =====\n{text.strip()}" for i, text in enumerate(pages, start=1))


def review_rule(rule: dict, document: str) -> dict:
    """Ask the model for a verdict on one rule. Returns verdict, evidence, page, reasoning."""
    response = openai.responses.create(
        model=model,
        instructions=INSTRUCTIONS,
        input=f"RULE {rule['id']} - {rule['name']}:\n{rule['rule']}\n\nDOCUMENT:\n{document}",
        text={"format": {"type": "json_schema", "name": "rule_verdict", "schema": SCHEMA, "strict": True}},
    )
    return json.loads(response.output_text)


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "POC")
    rules = load_rules(folder)
    answer_key = yaml.safe_load((folder / "answer_key.yaml").read_text(encoding="utf-8"))
    doc_path = folder / answer_key["document"]

    # OCR (cached)
    ocr_path = Path("output") / f"{doc_path.stem}.md"
    if not ocr_path.exists():
        subprocess.run([sys.executable, "ocr.py", str(doc_path), "prebuilt-layout"], check=True, stdout=subprocess.DEVNULL)
    document = number_pages(ocr_path.read_text(encoding="utf-8"))

    results = []
    correct = 0
    for rule in rules:
        answer = review_rule(rule, document)
        expected = answer_key["answers"][rule["id"]]
        ok = answer["verdict"] == expected["expected"]
        correct += ok
        results.append({"rule": rule["id"], "name": rule["name"], **answer, "expected": expected["expected"], "correct": ok})

        print(f"{'OK  ' if ok else 'MISS'} {rule['id']} {rule['name']}: {answer['verdict']} (expected {expected['expected']}), page {answer['page']}")
        print(f"       \"{answer['evidence'][:120]}\"")
        if not ok:
            print(f"       model: {answer['reasoning']}")
            print(f"       key:   {expected['note']}")

    print(f"\nAccuracy: {correct}/{len(rules)}")
    Path("output").mkdir(exist_ok=True)
    (Path("output") / f"{doc_path.stem}.review.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
