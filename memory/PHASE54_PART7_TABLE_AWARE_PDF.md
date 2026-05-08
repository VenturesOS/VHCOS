# Phase 54 — Part 7: Table-aware PDF fallback (pdfplumber)
**Date:** 2026-05-07
**Type:** Resume parsing accuracy upgrade
**Status:** ✅ Built & verified — pending EC2 deploy

## Goal
Recover contact info / experience / skills from resumes whose layout
hides them inside borderless tables or multi-column boxes. Standard
text extractors (fitz, PyPDF2) collapse those into fragmented unordered
text that confuses the LLM resume parser. We need a table-aware
fallback that emits clean `Key | Value` rows the LLM can read.

## Decision (user-driven)
- Library: **pdfplumber 0.11.9** (~30 MB; pure-python, fast, battle-tested)
- Trigger: **smart fallback** — only when prior extractors yield < 500 chars
- Scope: **`extract_text_from_file()`** — single integration point covers
  every caller (`parse_resume_with_ai`, bulk import, cv_upload, etc.)

## Implementation
### `services/matching_engine.py`
- New module-level import `_pdfplumber` (graceful fallback if missing)
- New step in PDF pipeline between PyPDF2 and OCR:
  1. `fitz` (fast)
  2. `PyPDF2` (fallback)
  3. **`pdfplumber` table-aware** (new) — only if text < 500 chars
  4. OCR (last resort, image-based PDFs)
- Caps at first 6 pages (resumes > 6 pages → cover letters/appendices)
- Output preserves table rows as `cell | cell | cell` format
- Logs each fallback fire so we can quantify impact in production

### `requirements.txt`
- `pdfplumber==0.11.9`
- `pdfminer.six==20251230` (transitive)
- `pypdfium2==5.8.0` (transitive)

## Verification (workspace pod)
Generated an adversarial test PDF with contact info in a borderless
table and skills in a grid table, then ran both extractors:

| Extractor | Phone visible? | Email visible? | "Skill | Years" structured? |
|---|---|---|---|
| fitz alone | label & value on separate lines (LLM-confusing) | same | NO — flat list `Python\n5\nDjango\n4` |
| **fitz + pdfplumber** | `Phone: 9876543210 Email: anshul@example.com` ✅ | ✅ | YES — `Python \| 5`, `Django \| 4` rows ✅ |

Length jumped from 139 → 194 chars, AND structure went from "wall of
flat tokens" to "clean key:value pairs" which is the actual win for
the downstream LLM.

## Tests
```
$ pytest tests/test_pdf_table_fallback.py -v
test_table_resume_yields_structured_text PASSED
test_pdfplumber_module_loaded            PASSED
============== 2 passed in 2.31s ==============
```
Asserts:
- A table-only PDF still yields phone + email + skills
- pdfplumber module is importable inside `matching_engine`

## Files Changed
- `backend/services/matching_engine.py` (~40 LOC: import + fallback step)
- `backend/tests/test_pdf_table_fallback.py` (new, 2 tests)
- `backend/requirements.txt` (+ pdfplumber + 2 transitive deps)

## Deploy (EC2)
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  cd backend && \
  ./venv/bin/pip install pdfplumber==0.11.9 && \
  cd .. && \
  sudo systemctl restart gunicorn && \
  sleep 5 && \
  cd backend && ./venv/bin/python -m pytest tests/test_pdf_table_fallback.py -v
```
Expected: `2 passed in <3s`. New log line `[pdfplumber] table-aware
fallback used for X.pdf: 139 -> 194 chars` will appear whenever the
fallback fires.

## Observability
Grep `journalctl` after a few days of usage:
```bash
sudo journalctl -u gunicorn --since "24h ago" | \
  grep -c "table-aware fallback used"
```
Tells you how many resumes per day actually needed the fallback —
that's the population that was previously parsing incorrectly.
