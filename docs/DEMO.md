# 2–3 minute demo

## Before the call

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`. Keep [examples/companies.csv](../examples/companies.csv) ready. An LLM key improves interpretation but is not required.

## 1. Frame the problem — 20 seconds

“Account research is repetitive, and a score generated entirely by an LLM is difficult to trust. SignalForge collects public evidence, uses AI only to structure and interpret it, and applies a deterministic ICP policy.”

## 2. Analyze one company — 60 seconds

Expand `POST /companies/analyze`, choose **Try it out**, and submit:

```json
{
  "name": "Close",
  "website": "https://www.close.com"
}
```

Point out the structured company fields, five score components, plain-language explanation, and each signal's evidence and source URL. Mention that the score comes from `config/default_icp.json`, not from the LLM.

## 3. Show persistence and batch workflow — 50 seconds

Run `GET /companies`, then `GET /companies/{id}/signals` with the returned ID. This demonstrates data ready for CRM or outbound automation.

Open `POST /companies/batch`, upload `examples/companies.csv`, and execute it. Point out the processed/succeeded/failed summary and row-specific results.

## 4. Close on engineering choices — 30 seconds

Open `GET /health` and mention the optional LLM flag. Close with three implementation choices: SSRF checks and fetch limits at the network boundary, Pydantic validation around AI output, and deterministic scoring with source evidence. These make the workflow useful for GTM operations rather than a prompt wrapper.
