# Omazz release checklist

Use this before sending SmartVoice to Omazz or running a live demo.

## Must do before sharing

- Remove real customer audio from `data/raw_audio/`.
- Remove local databases such as `data/smartvoice.db` unless the data is fully anonymized.
- Remove temporary reports such as `_anomaly_report.txt`.
- Confirm `.env` is not included in the ZIP or commit.
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

```env
MOCK_STT=true
```

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

1. Open the home page and expand `Deployment readiness`.
2. Log in as Admin.
3. Upload one anonymized Omazz warranty call.
4. Process the call and show the tagged transcript.
5. Show the dashboard: sentiment, issue keywords, brand mentions, case management, and next actions.
6. Show customer and warranty linking.

## Privacy notes

- Audio files and SQLite databases are local runtime data and are ignored by Git.
- Keep HuggingFace tokens and passwords only in `.env`.
- If sharing a ZIP, exclude `.venv`, `.git`, `data/raw_audio`, `data/models`, `data/logs`, and local DB files.
