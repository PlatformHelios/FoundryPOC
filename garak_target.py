"""Lets NVIDIA garak (LLM vulnerability scanner) attack your Foundry model deployment.

garak sends attack prompts (jailbreaks, prompt injection, encoding tricks, ...) to the
generate() function below and checks whether the model's replies were "hits".

Setup (garak is heavy, so it lives in its own virtual environment):
    python -m venv .venv-garak
    .venv-garak\\Scripts\\pip install -r requirements-garak.txt
    az login

Run from this folder:
    .venv-garak\\Scripts\\python -m garak --target_type function --target_name garak_target#generate --probes promptinject --generations 1
    .venv-garak\\Scripts\\python -m garak --list_probes      # see every probe

Cost: always pass --probes (omitting it runs all ~230 probes) and --generations 1
(the default of 5 sends every prompt five times). One probe is up to 256 calls, roughly $0.25-$2 on gpt-5-mini.

Reports (.jsonl and .html) are written to the folder garak prints at the end of the run.
"""
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import BadRequestError

load_dotenv()

project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential())
openai = project.get_openai_client()
model = os.getenv("FOUNDRY_MODEL", "gpt-5-mini")


def generate(prompt: str, **kwargs) -> list[str]:
    try:
        response = openai.responses.create(model=model, input=prompt)
        return [response.output_text]
    except BadRequestError as e:
        # Azure's content filter rejects some attack prompts outright; that counts as the model being protected.
        if "content_filter" in str(e) or "content_management_policy" in str(e):
            return ["[Blocked by Azure content filter]"]
        raise
