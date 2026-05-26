# Omazz release checklist

Use this before sending SmartVoice to Omazz or running a live demo.
**Delivery target:** 2026-05-23

## Must do before sharing

- Remove real customer audio from `data/raw_audio/`.
- Remove local databases such as `data/smartvoice.db` unless fully anonymized.
- Remove temporary reports such as `_anomaly_report.txt` and any `_*.py` / `_*.txt` scratch files.
- Confirm `.env` is excluded from the ZIP/commit.
- Confirm `data/models`, `data/logs`, `.venv`, `.git`, `smartvoice.egg-info`, and `.claude/` are excluded from the handoff package.
- Run the test suite:

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

Expected current baseline: `190 passed` as of 2026-05-27 (warnings about `.pytest_cache` permissions are non-blocking if all tests pass; if you hit `PermissionError` on the pytest tmp dir, pass `--basetemp="$env:TEMP\pytest-clean"`).

- Open Home and verify `Deployment readiness`.
- Create demo users with hashed passwords:

```bash
python scripts/make_password_hash.py admin Admin
```

Paste the output into `.env`:

```env
SMARTVOICE_USERS=admin|Admin|pbkdf2_sha256$...
```

## Recommended demo settings

For a laptop without GPU or HuggingFace access:

1. Log in as `Admin` or `Supervisor`.
2. Open `Settings`.
3. Click `Use Demo Laptop Mode`.
4. Restart the app.

For a realistic Omazz demo:

```env
MOCK_STT=false
HF_TOKEN=hf_your_token_here
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
```

Install the Ollama model once:

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
```

## Omazz-facing demo story

Frame the system as:

> Omazz Warranty & Call Intelligence: a local AI dashboard that turns Thai call-center audio into searchable transcripts, warranty-linked cases, service insights, agent QA, and anomaly alerts.

Recommended demo flow:

1. Open Home and expand `Deployment readiness`.
2. Log in as Admin.
3. Upload one anonymized Omazz warranty call.
4. Process the call and show the tagged transcript.
5. Show how the system auto-links customer/warranty from the filename phone number, and how Inbound/Outbound + Agent code are derived from the same filename.
6. Show case grouping, next action owner, and case merge if relevant.
7. Open Dashboard for sentiment, issue keywords, anomaly, agent performance, QA evidence, and case summary. Show the "เจาะลึก" drill-down chart under Topic Distribution for product-issue damage categories.
8. Confirm Next Action rows use case-specific content and do not repeat fake prompt examples such as fixed amounts, product codes, or phone numbers.
9. Show Admin's Inbound/Outbound filter and Dashboard's Agent filter on Agent Performance.
10. Open Customers for warranty history and linked call context.
11. Open Settings briefly to show Demo / Real AI switching.

## Privacy notes

- Audio files and SQLite databases are local runtime data and ignored by Git.
- Keep HuggingFace tokens and passwords only in `.env`.
- Do not ship real audio, real customer DBs, logs, or temporary reports in a demo ZIP.
