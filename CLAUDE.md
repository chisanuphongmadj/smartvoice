# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SmartVoice** — AI-powered Call Center Analytics สำหรับ call center ภาษาไทย (domain: ร้านที่นอน/เฟอร์นิเจอร์ Restonic/โลตัส)

Pipeline: `audio (.wav/.mp3) → Whisper STT → Pyannote diarization → LLM speaker correction → LLM analysis → SQLite → Streamlit UI`

## Commands

All commands run from inside `smartvoice/` using the venv Python interpreter on Windows:

```powershell
# Run all tests (ignore test_config.py — has env side-effects)
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q

# Run a single test file
& ".venv\Scripts\python.exe" -m pytest tests\test_pipeline.py -v

# Run the app
.venv\Scripts\activate
streamlit run Home.py       # → http://localhost:8501

# Seed mock data
& ".venv\Scripts\python.exe" scripts\seed_mock_data.py

# Backfill topic_detail for legacy "แจ้งปัญหาสินค้า" calls (dry-run by default)
& ".venv\Scripts\python.exe" scripts\backfill_topic_detail.py [--apply]

# Compare Ollama models on the 4 analyses over stored transcripts (DB opened read-only)
# → data\llm_compare\<timestamp>\report.md (gitignored: it quotes real calls)
& ".venv\Scripts\python.exe" scripts\compare_llm_models.py --models <current> <candidate> [--limit N]
```

**Current test baseline:** 519 tests, must pass 100% before every commit.

**External dependency:** Ollama must be running before processing calls:
```powershell
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama serve
```

## Architecture

### Package layout (`smartvoice/smartvoice/`)

| File | Role |
|------|------|
| `config.py` | Single source of truth for all env vars |
| `db.py` | SQLite schema, migrations, CRUD (tables: `calls`, `customers`, `warranty_registrations`, `call_customer_links`, `cases`, `users`, `sales_orders`, `sales_order_lines`). Scale-friendly helpers: `count_calls_by_status()`, `get_pending_call_ids()`, `get_processing_calls()`, `get_all_calls(limit=N)`. Also holds the append-only `audit_log` table. Customer/warranty edits go through `update_customer()` / `update_warranty()` (column whitelists); deletes are `soft_delete_*()` / `restore_*()` — see **Soft delete + audit trail** |
| `pipeline.py` | Core orchestrator — speaker correction multi-pass, case assignment (~70 KB) |
| `prompts.py` | All LLM prompt templates (~54 KB) |
| `ollama_client.py` | LLM client + JSON extraction; 4 separate analysis calls. Includes `normalize_topic_detail()` for the product-issue drill-down vocabulary |
| `file_manager.py` | Audio upload + SHA-256 deduplication. Filename helpers: `extract_phone_from_filename()`, `extract_direction_from_filename()` (Inbound/Outbound), `extract_agent_code_from_filename()` |
| `env_settings.py` | `.env` read/write + UI helpers: `gpu_available()`, `gpu_device_name()`, `validate_whisper_combo()` (model/backend/device/compute compatibility), `recommended_combo_for_model()` (auto-apply on model change) |
| `ui_helpers.py` | Shared CSS, login page, `init_page(page_key)` role guard, badges, processing launchers |
| `customer_entry.py` | Validation + create/update/hide/restore rules for the manual data-entry page (phone normalisation, duplicate guards that skip the row being edited, warranty expiry maths); writes its own audit entries through `audit.record()` — no Streamlit import, so it is unit-testable. Also `set_warranty_status()` (Active/Cancel) |
| `sales_orders.py` | Sales orders (SO): `FIELDS` (Thai template header + NAV English aliases per column), `read_upload()` (xlsx/csv, finds the header row, cp874 fallback), `parse_import()` (one row per line → orders grouped by SO number, row-numbered errors), value parsers (พ.ศ. dates, `1,234.50`, Excel-stripped leading 0), `complete_totals()`, `import_orders()` (upsert + one `import` audit entry), `save_manual()` / `hide()` / `restore()` / `link_customer()`, `template_bytes()`. No Streamlit import — see **Sales orders (SO)** |
| `dashboard_report.py` | Dashboard export — `build_report()` → `pdf_report()` (fpdf2 + HarfBuzz Thai shaping, bars drawn as rectangles, own `wrap_text()`), `summary_csv()`, `calls_csv()` (utf-8-sig, formula-safe cells). Also owns the agent-score maths (`scored_calls`, `agent_summary`) that `10_Agent_Performance.py` imports, and `count_list_field()`. No Streamlit import |
| `customer_view.py` | Customers page tables (`customer_rows`, `warranty_rows`, warranty state/expiry) and `render_customer_detail()` — the dialog opened by clicking a customer or warranty row |
| `so_view.py` | Streamlit rendering of an SO laid out like the company's "ใบสั่งขาย" — used by the SO page, the Customers page and the Cases dialog (`render_customer_orders()`) |
| `insight_rules.py` | Deterministic checks on every LLM answer before it is saved — quote verification, QA scoring, next-action assembly, sentiment guard, anomaly verification + keyword backstop, brand/platform canonicalisation, topic clamping. See **LLM analysis** |
| `audit.py` | Audit-trail vocabulary + `record()` — action/entity constants, Thai labels, secret redaction, `diff_fields()`. Every page logs through it (`ui_helpers.audit()` fills in the signed-in user) |
| `processing_control.py` | Stop button + live-run state for background processing: `begin()`/`finish()` per job, `request_stop()`, `check()` (raises `ProcessingCancelled`, a **BaseException** so the STT/LLM `except Exception` fallbacks can't swallow it), `uninterruptible()` around saving results, `run_call_ids()` for the Admin live panel. No Streamlit import — see **Stopping processing** |
| `case_workflow.py` | Case ownership rules — `claim()` / `release()` / `change_status()`; only the claimer changes status, Admin/Supervisor may release (not take) someone's claim, QA can't claim. Logs to audit + notifies Discord. No Streamlit import |
| `labels.py` | Thai words for every code shown on screen (`call_status()`, `case_status()`, `sentiment()`, `field()` for audit-log field names) and `thai_time()` — UTC ISO → `dd/mm/yyyy HH:MM น.` in UTC+7. No Streamlit import |
| `discord_notify.py` | Discord incoming-webhook sender (`DISCORD_WEBHOOK_URL`); background thread, never raises, `allowed_mentions` off, phone masked to last 4 digits |
| `auth.py` | PBKDF2 hashing, DB/`.env` account lookup, role → page permission matrix (`ROLE_PERMISSIONS`, `can_access()`, `visible_pages()`) |
| `stt/` | STT sub-package: `audio.py` → `transcribe.py` → `diarize.py` → `orchestrator.py` |

`Home.py` is the router (see **Login & role-based navigation**), not just a landing page.

Streamlit pages: `pages/1_📤_Admin.py`, `2_📊_Dashboard.py` (Dashboard → ภาพรวม), `3_👥_Customers.py`, `4_Settings.py`, `5_👤_Users.py`, `6_➕_Data_Entry.py`, `7_📜_Audit_Log.py`, `8_Dashboard_Insights.py`, `9_Dashboard_Anomaly.py`, `10_Agent_Performance.py`, `11_Cases.py` (จัดการเคส), `12_Call_Summaries.py`, `13_Sales_Orders.py` (ใบสั่งขาย)

### Dashboard is split into pages

The Dashboard used to be one ~1,000-line page; the professor found it too hard to read, so each topic is its own page (`auth.DASHBOARD_PAGES`), shown under one **Dashboard** heading in the sidebar. `Home._SECTIONS` maps every page to a sidebar heading (`""` = top, no heading).

- Every Dashboard page calls `dashboard_common.load_filtered_calls()` — one shared filter bar (date / topic / sentiment / load limit). Each page draws its own copy of the widgets and Streamlit does **not** carry a widget's value to the same key on another page (it silently falls back to the first option). So the real values live in `_keep_*` session keys: `restore_filters()` writes them back on **every** run before the widgets draw, and each widget has `on_change=remember_filters` so a change is saved before the next restore. Saved date ranges are clamped to the loaded calls because `st.date_input` raises when its value is outside min/max.
- Chart styling (`CHART_LAYOUT`, palettes, `hbar()`) lives in `dashboard_common` too — new charts should use it rather than copy the Plotly settings.
- **ส่งออกรายงาน** sits next to the filter bar on every Dashboard page (`dashboard_common.render_export_menu()`, drawn by `load_filtered_calls()`): PDF report, summary CSV, call-list CSV of the current filter. Files are built only on click — `st.download_button(data=callable, on_click="ignore")` — and the callable writes an `export` audit entry with the user captured at render time (the click is served outside the page run). Numbers come from `dashboard_report`, never a second copy of a page's maths.
- `11_Cases.py` reads cases straight from SQL, then only the calls of the cases on screen (`db.get_calls_for_cases()`, one query). Case subjects are just the first call's broad topic, so the table and panel show `case_workflow.case_brief()` instead — latest summary, specific problem type, next step, urgency — so staff know what they are claiming.

### Speaker correction pipeline (`pipeline.py:1408-1459`)

Pyannote frequently mislabels speakers; LLM also makes mistakes — the system uses layered correction:

1. STT → diarization → grouped segments
2. `_split_long_segments_by_sentence()` — pre-split at Thai sentence boundaries
3. `ollama_client.correct_speakers()` — LLM label correction
4. `_aggressive_relabel_from_strong_cues()` — **deterministic override** using Thai domain cues ⭐
5. 9 splitter functions (opening/mixed/question-answer/closing turns)
6. `_stabilize_sandwiched_turns()`
7. `_aggressive_relabel_from_strong_cues()` again — after splitters create new chunks
8. `_merge_adjacent_same_speaker()`
9. `_enforce_role_rules()`
10. `ollama_client.cleanup_transcript()` — text polish
11. Repeat steps 2–9 (round 2)
12. `_apply_domain_normalization()` + dedup drops

**Critical order constraint:** `_aggressive_relabel_from_strong_cues` must run **before** `_merge_adjacent_same_speaker`, or merging will lock in wrong labels permanently.

### LLM analysis (`ollama_client.py`) — the model proposes, `insight_rules.py` decides

5 Ollama requests per call, all `format: "json"`, temperature 0, `num_ctx` = `OLLAMA_NUM_CTX` (default 12288 — Ollama's own default on a 16 GB GPU is 4096, which silently cut the start of the QA prompt):
1. `extract_summary_and_topics()` — summary, topic, **topic_detail**, keywords, brand/platform mentions
2. `analyze_sentiment()` — customer_quote → reason → sentiment (quote first grounds the label)
3. `evaluate_agent_qa()` — QA checklist: `"found": [{"item": "P1", "quote": ...}]` + `customer_had_problem`
3b. same function, **separate request** for the next action (`prompts.NEXT_ACTION_USER`) — asked together with the checklist, the model returned `pending: false` on calls that plainly had open work
4. `detect_anomaly()` — category + evidence_quote + reason

Every request → `extract_json()` → empty dict on failure (logs and continues). The transcript is capped at `MAX_CHARS` (14,000) by dropping the **middle** — the old cut kept only the first 6,000 characters and lost the close of 4 in 11 real calls.

**Never trust the model's totals, flags or lists — `insight_rules.py` recomputes them** (all validated on the 11 real calls, see `tests/test_insight_rules.py`):
- QA: an item counts only if its quote is something the agent said (`agent_said()`: not in a `Customer:` line, or in agent voice — diarization leaves agent words as "Speaker 0" or merged into customer lines). P2 (polite particles) is measured, not quoted. Score = share of applicable items (P3 only applies when the customer had a problem), 1-5. The old prompt scored every call 5/5.
- Next action: `build_next_action()` joins todo | detail | deadline | follow-up, fills "ไม่ระบุในสาย (แนะนำ: …)" from the owner, strips template leftovers (`<...>`, `[บริบท]`); `money_action_is_ungrounded()` rejects a refund task on a call with no money talk (the old example "ติดตามการโอนเงินคืน" was copied onto unrelated calls).
- Sentiment: `check_sentiment()` — positive needs a praise word in the customer's quote ("ขอบคุณครับ" alone was labelled positive); a swearing/explicitly displeased customer is never positive/neutral.
- Anomaly: `verify_anomaly()` — the quote must occur in the call and contain a keyword of its category; severity comes from the category table. Agent misconduct (B, high severity) goes through `misconduct_is_grounded()`: the quote must be the agent's, B1/B3 need rude/refusing words in it, and B2 needs the customer to say they were told wrong ("บอกผิด", "ตอนแรกบอกว่า") — a plain "ไม่ใช่" is ordinary clarifying. `keyword_anomaly()` is a backstop that scans **Customer lines only** for health words and profanity. Keywords are matched with `has_keyword()`, which knows Thai traps ("แจ้งความต้องการ" ≠ "แจ้งความ").
- Brands/platforms: `canonical_mentions()` keeps only names actually said (the company greeting "บริษัทที่นอนโลตัส" doesn't count) under one spelling; the dashboard regroups older rows with `canonical_name()`.
- Topic: `normalize_topic()` clamps to the 9 topics.

`topic_detail` vocabulary (filled only when `topic == "แจ้งปัญหาสินค้า"`): `ผ้าขาด/ผ้าหุ้มชำรุด`, `เตียง/โครงหัก`, `สปริง/ฟองน้ำยุบ`, `เปื้อน/รอยขีดข่วน`, `กลิ่น/แพ้/ระคายเคือง`, `ความชื้น/น้ำท่วม`, `ขนาด/สเปคผิด`, `อื่นๆ`. Clamped via `normalize_topic_detail()` (stems are whole words — a bare "รา" matched "รายละเอียด").

**Prompt changes are validated by re-running the 4 analyses on the stored transcripts** and comparing against the previous prompts — a script like that is cheaper than a full STT run and caught every regression above.

### Auto case assignment (`pipeline.py:_auto_assign_case`)

1. **Recency short-circuit** — open case for this customer within `CASE_RECENCY_HOURS` (default 4h) → attach immediately (no LLM)
2. **LLM topic match** — compare new call's topic/summary against existing open cases
3. No match → create new case

### STT modes

| `MOCK_STT` | `WHISPER_BACKEND` | Result |
|-----------|-------------------|--------|
| `true` | any | Mock transcripts (fast, no GPU) |
| `false` | `transformers` | Recommended for Thai accuracy (`biodatlab/distill-whisper-th-large-v3`) |
| `false` | `faster-whisper` | Speed-optimized, `large-v3` or native CT2 model |

HF_TOKEN required for `pyannote/speaker-diarization-3.1` access. Without it, diarization is skipped and all speech is attributed to "Speaker 0".

## Domain: Thai Speaker Cues

Rule-based logic in `_aggressive_relabel_from_strong_cues` uses these patterns:

| Pattern | Indicates |
|---------|-----------|
| `พลอย/พอย + verb` | Agent (self-reference by name) |
| `คุณลูกค้า`, `ทางบริษัท/เรา/เจ้าหน้าที่` | Agent |
| `สวัสดีค่ะ [company name]` | Agent (opening) |
| `พี่ + verb` (self-reference) | Customer |
| `(ลูก/น้อง)` as vocative | Customer addressing agent |
| `ขอเลื่อนวัน`, `ติดตามเรื่องส่ง` | Customer |

**Do not modify `_AGENT_MARKERS` / `_CUSTOMER_MARKERS` without regression tests** — scoring is position + role sensitive; ambiguous additions cause flip errors.

## Anomaly Detection

Anomaly = escalation-worthy event, NOT just negative sentiment. Every flag requires a quoted passage from the transcript.

| Category | Required keywords | Severity |
|----------|------------------|----------|
| A1 Legal threat | "ฟ้อง", "ทนาย", "ดำเนินคดี", "ศาล", "แจ้งความ" | high |
| A2 Complaint threat | "สคบ.", "ร้องเรียน", "กระทรวง", "เพจ", "สื่อ" | high |
| A3 Escalation request | "ขอคุยกับหัวหน้า", "ขอสายผู้จัดการ" | medium |
| A4 Profanity | Actual swear words / กู-มึง (not just tone) | low |
| B Agent misconduct | Direct quote required | high |
| C1 Health from the product | "แพ้", "ผื่น", "คัน", "แสบ", "ระคายเคือง", "เชื้อรา", "สารเคมี", "บาดเจ็บ" | medium |
| C2 Disaster / C3 compensation | "น้ำท่วม", "ไฟไหม้" / "ค่าเสียหาย", "ชดเชย" | medium / low |

Normal complaints resolved politely = negative sentiment, **not** anomaly.

## Scale-friendly Home / Admin / Dashboard

These pages avoid loading rows they don't display, so they stay responsive at 10K+ uploads:

- **Home** (`Home.py`): the four cards come from `count_calls_by_status()`. Counting with `get_all_calls()` (a `SELECT *`) pulled every transcript into memory — measured ~278 ms and ~57 MB per page view at 5,000 calls. The readiness checks are wrapped in `@st.cache_data(ttl=300)` because an expander body runs even while collapsed and those checks hit Ollama/HuggingFace over the network (~2.6 s); together this took a home render from 2.9 s to 0.2 s at 5,000 calls.
- **Admin** (`pages/1_📤_Admin.py`): top metric cards read from `count_calls_by_status()` (SQL `GROUP BY`) so they're accurate even when only the latest-N rows are loaded for display. Load-limit picker defaults to `200 ล่าสุด` when total > 200, else `ทั้งหมด`. "Process All Pending" uses `get_pending_call_ids()` (lazy) so old pending calls aren't missed. The `@st.fragment(run_every=3)` live panel (`_live_run_panel`) reads only the current run's rows via `db.get_calls_progress()` (no transcripts) plus `get_processing_calls()`, and reruns the whole page only when another call finishes.
- **Dashboard** (all pages via `dashboard_common.load_filtered_calls()`): load-limit picker defaults to `1,000 ล่าสุด` when total > 1000, else `ทั้งหมด`. Analytics signal quality matters more here than first-paint speed, so the default is larger than on Admin.

## Filename-derived filters

Three pieces of metadata are derived from the CDR filename pattern `YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.wav`:

- **Phone** — `extract_phone_from_filename()` (used during upload for customer auto-link)
- **Direction** — `extract_direction_from_filename()` → powers the Inbound/Outbound radio filter on Admin
- **Agent extension** — `extract_agent_code_from_filename()` → powers the Agent dropdown filter on the Agent Performance page (`10_Agent_Performance.py`). Returns the short numeric segment (2-5 digits) that isn't the 14-digit timestamp or a 10-digit Thai phone.

No DB migration needed for direction/agent — derive at filter-time.

## Login & role-based navigation

`Home.py` is the entrypoint **router**, not a plain landing page:

1. `bootstrap_app()` — init DB, seed the bootstrap admin (`admin` / `admin1234`) when no account exists anywhere, recover stale processing, inject CSS
2. Not logged in → `st.navigation([login_page], position="hidden").run()` + `st.stop()`
3. Logged in → `st.navigation([...auth.visible_pages(role)])`, sidebar account box, then `page.run()`

**Calling `st.navigation` disables Streamlit's automatic `pages/` menu for the whole app** — that is what makes role filtering real: a page the role can't access is never in the nav, so Streamlit answers a hand-typed `/admin` URL with a redirect to the default page.

Permissions live in one place, `auth.ROLE_PERMISSIONS`:

| Role | home | admin | dashboard pages* + cases | customers + sales_orders | data_entry | audit | settings | users |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Supervisor | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| QA | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Agent | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

\* `auth.DASHBOARD_PAGES` — dashboard, insights, anomaly, agent_performance, calls. Every role sees all of them plus `cases`. `sales_orders` is readable by every role; importing/editing/hiding SOs on that page follows `can_access(role, PAGE_DATA_ENTRY)` (Admin).

Rules to keep intact:

- Every page file starts with `user, role = init_page(PAGE_<KEY>)` — the server-side backstop. Never gate a page with an ad-hoc `if role in {...}` check.
- `normalize_role()` maps anything unknown to `Agent` (least privilege), so a bad DB/`.env` value can't escalate.
- Adding a page means: new `PAGE_*` constant + `PAGE_ORDER`/`PAGE_LABELS_TH` entry + `ROLE_PERMISSIONS` membership + `_PAGE_SPECS` route in `Home.py` + `init_page()` call in the page. `tests/test_home_entrypoint.py` fails if any of these is missed.
- Accounts are DB-first, `.env` (`SMARTVOICE_USERS`) second. `.env` accounts have `user_id is None` and can't change their own password.
- `auth.would_remove_last_admin()` guards the Users page — there must always be ≥1 enabled Admin.
- **No admin-initiated password reset exists, by policy.** A password belongs to
  its owner: only `auth.change_password()` sets one and it demands the current
  password. An Admin's lever is the enable/disable toggle. Do not add a reset
  helper to `auth.py` or a reset form to the Users page — `tests/test_auth.py`
  fails if either reappears.
- The Users page has **no delete button** either: `audit_log` rows point at those
  accounts, so an account is disabled, never removed. `db.delete_user()` stays as
  a maintenance-only helper that no page calls.
- Session state holds the login, so a browser refresh (F5) logs the user out. That's accepted; no cookie/JWT layer.

## Soft delete + audit trail

**Customer and warranty rows are never removed from the database.** "ลบ" in the
UI means `deleted_at` / `deleted_by` get stamped, the row drops out of every
default query, and an audit entry records who did it. Never add a
`DELETE FROM customers` / `DELETE FROM warranty_registrations` anywhere.

- `soft_delete_customer()` hides the customer **and** their warranties, flagging
  those warranties `hidden_with_customer = 1`. Call links, cases and calls are
  left completely untouched, so call history still resolves.
- `restore_customer()` brings back the customer plus only the warranties carrying
  that flag — one an Admin hid separately stays hidden. (A shared `deleted_at`
  timestamp cannot be used for this: two hides in the same second collide.)
- `soft_delete_warranty()` / `restore_warranty()` handle a single registration;
  restoring is refused while its customer is still hidden.
- Every read helper takes `include_deleted=False` by default. `phone` and
  `registration_no` are UNIQUE, so a hidden row still owns its value — the
  duplicate check in `customer_entry` looks with `include_deleted=True` and tells
  the user to restore instead of failing on the constraint later.

### What gets logged

Every staff action goes through `audit.record()` (pages call the session-aware
`ui_helpers.audit()` wrapper) and lands in the append-only `audit_log` table,
readable on `pages/7_📜_Audit_Log.py` (Admin + Supervisor):

| Source | Entries |
|---|---|
| `ui_helpers` login flow | `login`, `login_failed`, `logout`, self-service password change |
| `customer_entry` | customer / warranty create, update, hide, restore |
| `pages/5_👤_Users.py` | account create, role & status change (enable/disable) |
| `pages/1_📤_Admin.py` | call upload & delete, manual customer link, case subject/merge, stop processing (`cancel`), requeue stuck calls |
| `case_workflow` | case claim / release / status change (Cases + Admin pages both call it via `ui_helpers.render_case_ownership()`) |
| `sales_orders` | SO import (one `import` entry per file), create, update (header diff + line count), hide, restore, customer link |
| `customer_entry.set_warranty_status()` | warranty `cancel` / `reactivate` |
| `dashboard_common.render_export_menu()` | Dashboard PDF / CSV downloads (`export`, entity `report`) |
| `pages/4_Settings.py` | `.env` saves and the Quick Mode presets |

Rules that keep the trail trustworthy:

- **`audit_log` is append-only** — nothing in the codebase updates or deletes a
  row in it. That is also why customers and warranties are hidden, not removed:
  a log pointing at rows that no longer exist explains nothing.
- `audit.record()` **never raises** — a failed log must not lose the user's action.
- Secrets are dropped by `audit.redact()` (`password`, `password_hash`,
  `hf_token`, ...); the field name stays so the change is still visible.
- `update` entries carry `{field: [before, after]}` from `audit.diff_fields()`,
  and an edit that changes nothing writes no entry at all.
- Adding a new mutating action means adding an `audit()` call next to it —
  `tests/test_audit.py` checks that every page which changes data touches the trail.

## Sales orders (SO) + warranty fields from the company templates

The company sent its blank "ใบสั่งขาย" (Dynamics NAV) and warranty-registration
screens to show **which fields** must be stored (real data can't be shared — never
ship sample rows that look real; the Excel template has headers only).

- `sales_orders` (header) + `sales_order_lines`; `so_number` is UNIQUE and is the
  upsert key — re-importing a file updates the SO and **replaces all its lines**.
  SOs are hidden (`deleted_at`), never deleted, like customers.
- Import format is **one row per line item**, header columns repeated. Columns are
  matched by normalised name (`sales_orders.map_columns`), so our Thai template and
  NAV exports both work. A bare `No.` is the item number when `Document No.` is
  present, otherwise the SO number. Errors are reported per Excel row and block
  the import button.
- Blank amounts are computed (`complete_totals`); values given in the file win.
  The edit form's "auto totals" checkbox defaults on only when the stored totals
  equal what the lines add up to (`totals_follow_lines`).
- Customer link: ship-to phone, then sell-to phone (`find_customer_id`). A re-import
  whose phone matches nobody keeps an existing (manual) link.
- Warranty: `so_number` (text reference, not an FK — a warranty may be entered
  before its SO is imported), `ref_id`, `status` active/cancelled (**Cancel keeps the
  row visible** with its status; hiding is `deleted_at`), `proof_path`. Proof files
  go through `file_manager.save_proof_file()` — type sniffed from content
  (jpg/png/webp/pdf), ≤10 MB, named by SHA-256 under `data/warranty_proofs/`; old
  proofs are never removed (audit rows point at them).
- Customers gained `nick_name` and `channel`.

## Stopping processing + live results (Admin page)

- Processing runs in daemon threads in the Streamlit process; `processing_control` is plain module state, so a stop pressed in one browser stops the run for everyone.
- Stopping is cooperative — checkpoints are every `pipeline._step()`, every STT progress message (the transformers backend logs once per 15 s chunk), and every `ollama_client.chat()` request. Worst-case delay is one chunk / one LLM request / one Pyannote run.
- A stopped call goes back to `uploaded` with **no** `error_msg` (`db.reset_calls_to_uploaded()`) — the Admin page shows any `error_msg` as a failure. The queue puts back the calls it marked `processing` up front but never started.
- Saving results + case assignment run inside `processing_control.uninterruptible()`: case matching asks Ollama, and a stop there would leave a `done` call with no case.
- The live panel lists the run's calls as they finish and lets staff open each finished call's summary/transcript right away (a selectbox, not a dialog — the 3 s fragment rerun would close a dialog). It also offers "คืนสถานะไฟล์ที่ค้าง" when calls are `processing` but nothing runs in this server (app was closed mid-call), instead of waiting `PROCESSING_STALE_MINUTES`.

## Case ownership (claim / no stealing / Discord)

- A case is claimed with `db.claim_case()` — one `UPDATE ... WHERE assignee_username IS NULL AND status != 'closed'`, so two simultaneous clicks can't both win. Status changes go through `db.set_case_status_as_assignee()`, which checks the owner in its `WHERE` too. Never change a case's status from a page with `db.update_case_status()` — that helper is for the pipeline's auto `follow_up` only.
- UI for every role lives in `ui_helpers.render_case_ownership(case, key_suffix)`; keys include the case id and a suffix because the Admin page draws the same case under each of its calls.
- Discord: `DISCORD_WEBHOOK_URL` (Settings page). Unset → nothing is sent. The URL is a secret and `audit.redact()` drops it.

## UI conventions (company-facing)

- **Thai on screen, codes in the DB.** Show statuses/sentiment/field names through `smartvoice.labels`; show timestamps with `labels.thai_time()` — never `created_at[:19]` or "UTC" (staff are in UTC+7; the DB stores UTC).
- **Menu:** `Home._PAGE_SPECS` gives every page a Thai title and a `:material/...:` icon (`tests/test_usability.py` checks both), and `st.navigation(..., expanded=True)` — without it Streamlit hides links past the 10th behind "View more".
- **Home page** is a work queue: unclaimed cases, my open cases, severe anomalies, each with an `st.page_link` shortcut. The case shortcuts pass `?owner=unassigned|mine`, which `11_Cases.py` applies once to its owner filter and then removes.
- **Destructive actions ask first.** Deleting calls (one or many) and merging cases open an `@st.dialog` with "ลบถาวร"/"ยกเลิก". File removal goes through `file_manager.remove_audio_file()`, which reports a locked file instead of raising.
- **Click any cell to read the row.** Tables with long text or a detail view (Cases, Call list, Agent Performance, Anomalies, Audit Log, Sales orders, Customers + their warranties) use `selection_mode=ui_helpers.TABLE_CLICK_MODES` (cell only — a click on any cell counts; row mode is left out because its checkbox column reopened the dialog when a box was un-ticked) and open an `@st.dialog(width="large")` with the full text. `ui_helpers.picked_row()` returns `(row, is_new)`; only a selection that gains something is new, so the dialog opens once per click — not on reruns, not on deselecting; each page also offers a "เปิด…อีกครั้ง" button.
- **Selections are row positions, not ids.** When an action reorders the table (claiming a case bumps its `updated_at`), the selection points at a different row. The Cases table key includes a hash of the row order so the selection resets, and the dialog re-opens by the remembered case id (`_case_dialog_case`) to show the result.
- Transcripts render through `ui_helpers.render_transcript()` — labels [พนักงาน]/[ลูกค้า], HTML-escaped (the text comes from speech recognition).
- Show **when the call happened** from `file_manager.extract_call_time_from_filename()`; `created_at` is only the upload time.
- Messages that must survive `st.rerun()` go through a session "flash" (Admin page `_flash()`), otherwise they vanish before anyone reads them.
- Model names (STT/LLM) in the sidebar and the readiness checks on Home are Admin/Settings-only; other roles never see them.

## Settings page behavior

`pages/4_Settings.py` is intentionally NOT wrapped in `st.form` because Streamlit form widgets don't fire `on_change` callbacks until form submit. The page uses reactive widgets (each with `key=`) + a single `st.button("Save Settings")` to commit all values together.

Key behaviors:
- **GPU detection** at page load via `gpu_available()` — hides `cuda` from Device dropdown when no GPU is present, so users can't save a combo that will crash later
- **Auto-apply recommended combo on model change** — the Whisper model selectbox's `on_change=_apply_model_recommendations` callback writes `recommended_combo_for_model()` output to session_state for Backend/Device/Compute. User can still adjust afterwards.
- **Post-save validation** — `validate_whisper_combo()` runs after save and renders `error` / `warning` / `info` messages so users see actionable feedback before the next `process_call()` would otherwise crash.

`_MODEL_RECOMMENDED_COMBO` table in `env_settings.py` maps each known model to its preferred `(backend, device, compute)`. Adding a new model to the Settings dropdown should also add an entry here (otherwise it falls through with no auto-apply).

## Known Pitfalls

- **`test_config.py`** manipulates env vars with side-effects on other tests — always pass `--ignore=tests\test_config.py`.
- **`created_at` in DB** = upload/process time, not the actual call date. Call date is in the filename: `YYYYMMDDHHMMSS-...`.
- **Typhoon 8B copies whatever the prompt shows**: example actions ("ติดตามการโอนเงินคืน"), placeholder text (`<เบอร์ที่ลูกค้าให้ไว้>`), brand lists, *and pre-filled JSON answer templates* (a skeleton with `"done": false` / `"pending": false` came back unchanged). Describe the keys in words instead of showing a filled skeleton, give no concrete example values, and verify in `insight_rules`. Keep `sanitize_next_action()` in the display path for older DB rows.
- **One request, one job.** Bundling the next action into the QA request made the model drop it; it is its own request now.
- **`scb10x/typhoon2.1-gemma3-12b` won't load on Ollama 0.32.5** ("selectattr: unknown test 'tool_calls'"): the GGUF's Jinja chat template hits a llama.cpp parser bug, and a Modelfile `TEMPLATE` doesn't override it. The local workaround is a copy of the GGUF with that validation loop blanked out (same byte length), imported as `typhoon2.1-gemma3-12b-local`. In the 13-call comparison it wrote better summaries/topics, but answered `sentiment_reason` in English on 9/13 calls and wrote bare-verb todos ("รอ", "ประสาน"); telling every analysis prompt to write Thai and asking for "คำกริยา + ทำอะไร/กับใคร" fixed both (0/13 English) without changing the 8B's answers. It also raised a false high-severity B2 (agent misinformation) on an ordinary item-name mix-up, which led to the B-category check in `misconduct_is_grounded()`. It still takes ~2× as long as the 8B — not switched yet.
- **Testing Ollama with Thai from Git Bash `curl` sends mangled text** and the model answers nonsense; test through Python (`ollama_client.chat`).
- **Common Whisper errors:** "โอมาสนา"/"โนโลตัส"/"ฟิวทู" for brand names; "ที่โน่น"/"ทีเนี่ย" for "ที่นอน"; Thai phone numbers often mixed Thai/Arabic digits.
- **fpdf2 hangs on Thai with `WrapMode.CHAR`** — `multi_cell` never returns on a long Thai run with no spaces at full width. The report wraps lines itself (`dashboard_report.wrap_text()`, never splitting a consonant from its vowel/tone marks) and draws each line with `cell()`. Text copied out of the PDF comes out reordered (side effect of HarfBuzz shaping); the printed text is correct.
- **PowerShell:** Never use `cd` — set `Cwd` parameter instead.
- **Imports** must be at the top of every file; never mid-file.
- **Never slice Thai text to a character count** (`summary[:100]`). Thai has no spaces between words, so the cut always lands mid-word — show the text in full and let it wrap.
- **Streamlit widget keys that edit a picked row must include the row id** (`key=f"_edit_role_{user_id}"`). With a fixed key Streamlit keeps the previous row's value and ignores `value=`, so switching rows saves stale data over the new one.
- **An `st.expander` body runs even while collapsed.** Anything slow inside it (network checks, big queries) runs on every rerun — cache it.
- **Same widget key on two pages ≠ same widget.** Streamlit leaves the old value in session state but the new page's widget ignores it and resets to its first option. Persist cross-page values in a plain key and write them back every run (see `dashboard_common.restore_filters`).
- **Network calls on a page must be cached** (`@st.cache_data`) — the Settings readiness checks used to hit Ollama/HuggingFace (~2.6 s) on every click.
- **UI labels are words, not emoji.** Menu entries use Material icons (`:material/...:`) next to the words, set explicitly so Streamlit doesn't pick up the emoji in some page file names. `tests/test_home_entrypoint.py` fails if a decorative icon comes back. The page *file names* (`pages/1_📤_Admin.py`) still contain emoji and `Home.py` routes to those exact paths — don't strip them.

## Pre-commit Checklist

- `pytest tests\ --ignore=tests\test_config.py -q` → 100% pass
- Add a regression test for every bug fix
- Remove temp files `_*.py`, `_*.txt`
- DB schema changes → migration must not break existing data + update `docs/database_design.md`
- Prompt changes → end-to-end test with at least one real audio file

## Environment

Configure via `smartvoice/.env` (copy from `.env.example`). Key variables:
- `WHISPER_MODEL`, `WHISPER_BACKEND`, `WHISPER_DEVICE`, `WHISPER_COMPUTE`
- `HF_TOKEN` — required for pyannote diarization (request access at huggingface.co)
- `OLLAMA_MODEL`, `OLLAMA_BASE_URL`
- `MOCK_STT=true` — fast development mode without GPU
- `DB_PATH` — defaults to `data/smartvoice.db`
- `CASE_RECENCY_HOURS` — window for recency-based case attachment
- `DISCORD_WEBHOOK_URL` — case claim/close notifications (blank = off)
- `REPORT_FONT_PATH` — Thai `.ttf` for the PDF report (blank = Tahoma / Leelawadee / Noto Sans Thai / TLWG, first found; none → the PDF button is disabled)

`data/` and `.env` are gitignored (runtime data + secrets).
