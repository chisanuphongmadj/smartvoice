# Omazz release checklist

Use this before sending SmartVoice to Omazz or running a live demo.
**Last reviewed:** 2026-10-16

## Must do before sharing

- Remove real customer audio from `data/raw_audio/` and real receipts/slips from `data/warranty_proofs/`.
- Remove local databases such as `data/smartvoice.db` unless fully anonymized. Besides customers and calls, the database also holds sales orders (names, addresses, phone numbers), staff accounts (`users`) and the full `audit_log` — usernames, customer names, and a history of who did what.
- Remove temporary reports such as `_anomaly_report.txt` and any `_*.py` / `_*.txt` scratch files.
- Confirm `.env` is excluded from the ZIP/commit.
- Confirm `data/models`, `data/logs`, `.venv`, `.git`, `smartvoice.egg-info`, `.claude/`, `.worktrees/`, `.pytest_cache/` and `.pytest_tmp/` are excluded from the handoff package.
- Run the test suite:

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

Expected current baseline: `492 passed` as of 2026-10-16 (warnings about `.pytest_cache` permissions are non-blocking if all tests pass; if you hit `PermissionError` on the pytest tmp dir, pass `--basetemp="$env:TEMP\pytest-clean"`).

- Log in and verify `ตรวจความพร้อมของระบบ` on the home page (results are cached for 5 minutes — press "ตรวจสอบใหม่" after changing anything).

## Accounts

On first start with an empty database the app creates `admin` / `admin1234`.

- **Change that password before the demo or handoff** — sidebar account box → `เปลี่ยนรหัสผ่าน`. The sidebar and the readiness check keep warning until it is changed.
- Create one account per staff member on `จัดการผู้ใช้`, with the right role:

| Role | Pages |
|---|---|
| Admin | everything |
| Supervisor | everything except เพิ่ม/แก้ไขข้อมูลลูกค้า and จัดการผู้ใช้ (reads SOs, cannot import/edit them) |
| QA / Agent | home, the 5 Dashboard pages, จัดการเคส, ลูกค้าและการรับประกัน, ใบสั่งขาย (read-only); QA cannot claim cases |

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
2. Open `ตั้งค่าระบบ`.
3. Click `โหมดสาธิต (ไม่ต้องใช้ GPU)`.
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

Optional: set the Discord webhook on `ตั้งค่าระบบ` and press `ส่งข้อความทดสอบ`, so case claims show up in the team channel during the demo.

## Omazz-facing demo story

Frame the system as:

> Omazz Warranty & Call Intelligence: a local AI dashboard that turns Thai call-center audio into searchable transcripts, warranty- and order-linked cases that staff claim and close, verified service insights, agent QA, and anomaly alerts — with role-based access, exportable reports and a full audit trail.

Recommended demo flow:

1. Log in as Admin (with the default password already changed).
2. On the home page, show "งานที่รอคุณ" (unclaimed cases, my cases, severe anomalies) and expand `ตรวจความพร้อมของระบบ`.
3. Upload one anonymized Omazz warranty call.
4. Process the call and show the tagged transcript ([พนักงาน] / [ลูกค้า]).
5. Show how the system auto-links customer/warranty from the filename phone number, and how Inbound/Outbound, Agent code and call time are derived from the same filename.
6. Open `จัดการเคส`: click a case to read what the customer reported and the next step, press `รับเคสนี้`, then show that a second user cannot take it; close it and show the Discord message.
7. Open the Dashboard pages (ภาพรวม, คีย์เวิร์ด แบรนด์ ช่องทาง, สายที่ผิดปกติ, ผลงานพนักงาน, รายการสาย). Point out that every QA point and anomaly is backed by a quote from the call, and show the "เจาะลึก" product-issue chart.
8. Press `ส่งออกรายงาน` → `รายงาน PDF`, and open `รายการสาย (CSV)` in Excel (Thai displays correctly).
9. Show Admin's Inbound/Outbound filter and the Agent filter on ผลงานพนักงาน.
10. Open `ใบสั่งขาย (SO)`: download the Excel template, import an anonymized file, click an SO to show it laid out like the company document.
11. Open `ลูกค้าและการรับประกัน`, click a customer: warranties (with proof of purchase and Active/Cancel status), sales orders, cases and calls in one window.
12. Open `เพิ่ม/แก้ไขข้อมูลลูกค้า`: add a customer and a warranty with a receipt image, edit one field, cancel the warranty, then "ลบ" it and show it is only hidden — restore it from `รายการที่ซ่อนไว้`.
13. Open `ประวัติการใช้งาน` and show the entries those steps just produced, including the before → after values, the SO import, the report export, and the CSV download.
14. Open `จัดการผู้ใช้` to show roles, enable/disable, and that there is no password reset or delete — then log in as an Agent to show the menu only lists the pages that role may open.
15. Open `ตั้งค่าระบบ` briefly to show:
    - Demo / Real AI switching
    - GPU auto-detection banner ("ตรวจพบ GPU" when present, otherwise a warning — `cuda` hidden from the Device dropdown)
    - Auto-apply combo: switch Whisper model → Backend/Device/Compute update immediately to the recommended pairing
    - Post-save validation: error/warning/info messages if user picks an incompatible combo

## Privacy notes

- Audio files and SQLite databases are local runtime data and ignored by Git.
- Keep HuggingFace tokens and passwords only in `.env`.
- Passwords and tokens are never written to the audit log — only the name of the field that changed.
- Customer, warranty and sales-order rows are hidden, not deleted, so "deleting" one in the UI does not remove it from the database file. Anonymize or drop the database before sharing it.
- Exported reports (PDF/CSV) contain customer phone numbers and call summaries — treat them like the database. Every export is recorded in the audit log.
- Do not ship real audio, real customer DBs, receipts, logs, or temporary reports in a demo ZIP.
