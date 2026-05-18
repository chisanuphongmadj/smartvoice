# Sidebar Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ปรับ sidebar navigation ให้ดูสะอาดขึ้นด้วย spacing, typography และ active state ที่เป็นระเบียบขึ้น โดยไม่แตะ logic ของระบบ

**Architecture:** คง navigation เดิมของ Streamlit ไว้ แล้วเพิ่ม CSS selector ที่จำกัดเฉพาะ sidebar navigation ใน shared stylesheet เพื่อควบคุม layout และ visual hierarchy โดยไม่เปลี่ยน component structure หรือ routing

**Tech Stack:** Python, Streamlit, CSS

---

## File Structure

- Modify: `smartvoice/ui_helpers.py`
  - เพิ่ม CSS สำหรับ sidebar navigation เท่านั้น
- No new test files
  - งานนี้เป็น visual-only CSS polish จึงตรวจด้วย rendered QA และ regression suite เดิม

### Task 1: Refine Sidebar Navigation Styling

**Files:**
- Modify: `smartvoice/ui_helpers.py`

- [ ] **Step 1: Capture the current rendered sidebar state**

Run the app and record the current sidebar appearance before editing so the visual delta is clear.

- [ ] **Step 2: Implement the minimal CSS update**

Add scoped CSS under `_CSS` for:

```css
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
    padding-top: 0.35rem;
}

section[data-testid="stSidebar"] [data-testid="stSidebarNav"] ul {
    gap: 0.2rem;
}

section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a {
    min-height: 2rem;
    padding: 0.4rem 0.55rem;
    border-radius: 8px;
    color: #aeb5c5;
    line-height: 1.35;
    font-weight: 500;
}

section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a[aria-current="page"] {
    background: rgba(124, 131, 240, 0.12);
    color: #f3f4f6;
}
```

- [ ] **Step 3: Run rendered QA**

Check Home, Admin, Dashboard, Customers, and Settings pages and confirm:

```text
- sidebar spacing is more even
- active page remains visually clear
- login widget and footer info are unaffected
```

- [ ] **Step 4: Run regression tests**

Run:

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```powershell
git add smartvoice/ui_helpers.py
git commit -m "style: polish sidebar navigation spacing"
```
