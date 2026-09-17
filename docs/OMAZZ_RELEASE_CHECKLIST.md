# Omazz release checklist

Use this before sending SmartVoice to Omazz or running a live demo.
**Last reviewed:** 2026-09-17 (SmartVoice 1.4.0)

## Must do before sharing

- Remove real customer audio from `data/raw_audio/`.
- Remove local databases such as `data/smartvoice.db` unless fully anonymized. Besides customers and calls, the database now also holds staff accounts (`users`) and the full `audit_log` — usernames, customer names, and a history of who did what.
- Remove temporary reports such as `_anomaly_report.txt` and any `_*.py` / `_*.txt` scratch files.
- Confirm `.env` is excluded from the ZIP/commit.
- Confirm `data/models`, `data/logs`, `.venv`, `.git`, `smartvoice.egg-info`, `.claude/`, `.worktrees/`, `.pytest_cache/` and `.pytest_tmp/` are excluded from the handoff package.
- Run the test suite:

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

Expected current baseline: `305 passed` as of 2026-09-17 (warnings about `.pytest_cache` permissions are non-blocking if all tests pass; if you hit `PermissionError` on the pytest tmp dir, pass `--basetemp="$env:TEMP\pytest-clean"`).

- Log in and verify `Deployment readiness` on the home page (results are cached for 5 minutes — press "ตรวจสอบใหม่" after changing anything).

## Accounts

On first start with an empty database the app creates `admin` / `admin1234`.

- **Change that password before the demo or handoff** — sidebar account box → `เปลี่ยนรหัสผ่าน`. The sidebar and the readiness check keep warning until it is changed.
- Create one account per staff member on `จัดการผู้ใช้`, with the right role:

| Role | Pages |
|---|---|
| Admin | everything |
| Supervisor | home, Admin, Dashboard, Customers, ประวัติการใช้งาน, Settings |
| QA / Agent | home, Dashboard, Customers |

- Admins **cannot set or reset another person's password** and **cannot delete accounts** — by policy. To cut someone off, disable the account. If a staff member forgets their password, disable the old account and create a new one.
- Optional break-glass account kept outside the database (only needed if every Admin password is lost):

```bash
python scripts/make_password_hash.py admin Admin
```

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

> Omazz Warranty & Call Intelligence: a local AI dashboard that turns Thai call-center audio into searchable transcripts, warranty-linked cases, service insights, agent QA, and anomaly alerts — with role-based access and a full audit trail.

Recommended demo flow:

1. Log in as Admin (with the default password already changed).
2. On the home page, expand `Deployment readiness`.
3. Upload one anonymized Omazz warranty call.
4. Process the call and show the tagged transcript (`บทสนทนาแยกผู้พูด`).
5. Show how the system auto-links customer/warranty from the filename phone number, and how Inbound/Outbound + Agent code are derived from the same filename.
6. Show case grouping, next action owner, and case merge if relevant.
7. Open Dashboard for sentiment, issue keywords, anomaly, agent performance, QA evidence, and case summary. Show the "เจาะลึก" drill-down chart under Topic Distribution for product-issue damage categories.
8. Confirm Next Action rows use case-specific content and do not repeat fake prompt examples such as fixed amounts, product codes, or phone numbers.
9. Show Admin's Inbound/Outbound filter and Dashboard's Agent filter on Agent Performance.
10. Open Customers for warranty history and linked call context — call summaries show in full.
11. Open `เพิ่มข้อมูล`: add a customer and a warranty, edit one field, then "ลบ" it and show it is only hidden — restore it from `รายการที่ซ่อนไว้`.
12. Open `ประวัติการใช้งาน` and show the entries those steps just produced, including the before → after values of the edit and the CSV download.
13. Open `จัดการผู้ใช้` to show roles, enable/disable, and that there is no password reset or delete — then log in as an Agent to show the menu only lists the pages that role may open.
14. Open Settings briefly to show:
    - Demo / Real AI switching
    - GPU auto-detection banner ("ตรวจพบ GPU" when present, otherwise a warning — `cuda` hidden from the Device dropdown)
    - Auto-apply combo: switch Whisper model → Backend/Device/Compute update immediately to the recommended pairing
    - Post-save validation: error/warning/info messages if user picks an incompatible combo

## Privacy notes

- Audio files and SQLite databases are local runtime data and ignored by Git.
- Keep HuggingFace tokens and passwords only in `.env`.
- Passwords and tokens are never written to the audit log — only the name of the field that changed.
- Customer and warranty rows are hidden, not deleted, so "deleting" one in the UI does not remove it from the database file. Anonymize or drop the database before sharing it.
- Do not ship real audio, real customer DBs, logs, or temporary reports in a demo ZIP.
