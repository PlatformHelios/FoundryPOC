"""Step 6 smoke test: confirms your Foundry endpoint, login and model deployment work.
 
Setup:
    cp .env.example .env      # then fill in your values
    az login
    pip install -r requirements.txt
    python smoke_test.py
"""
import os
import sys
 
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
 
load_dotenv()  # reads .env into environment variables
 
endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
model = os.getenv("FOUNDRY_MODEL", "gpt-5-mini")
 
if not endpoint or "<" in endpoint:
    sys.exit("Set FOUNDRY_PROJECT_ENDPOINT in your .env file (see .env.example).")
 
project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
openai = project.get_openai_client()
 
response = openai.responses.create(model=model, input="Say hello in five words.")
print(response.output_text)