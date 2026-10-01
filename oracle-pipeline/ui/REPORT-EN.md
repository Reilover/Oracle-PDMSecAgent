# REPORT-EN — ORACLE Tier-3 Console English Version

Date: 2026-09-28 · Deliverable: full English UI (`en.html`) + 2 verified screenshots. Chinese `index.html` untouched.

## 1. Changes

- **`ui/static/en.html` (NEW)** — complete English translation of `index.html` (all UI copy: nav, legends, table headers, buttons, toasts, about page, dashboard KPIs, timeline, labeling page). Terminology aligned with the paper: window / scenario / source / routing path / per-question confidence / approve / veto / relabel / confirm / pending / decided / threshold (τ / τ_h).
  - Statuses: `已决策→decided`, `待裁决→pending`; buttons: `整窗 Confirm→Window-level Confirm (writes audit)`, `改判…→relabel…`, `标注→Label`.
  - All JS-generated strings translated too (toasts, empty states, timeline headings, SSE badges).
  - `enNarr()` helper does **display-only** translation of pipeline narrative labels (`窗口→Window`, `场景→scenario`, `源→source`, `统计→stats:`); audit.jsonl data itself is untouched.
  - Chinese `index.html` remains the default at `/`; English at **`/static/en.html`** (shared 8024 instance serves it as-is — static mount, no server change needed).

## 2. Screenshots (headless chromium 1234 via playwright, viewport 1440px, dark theme)

| File | Content | Size |
|---|---|---|
| `ui/screenshots/en-queue.png` | Queue page, full page: 16 windows, colored per-question confidence chips, decided/pending statuses | 1440×1046 |
| `ui/screenshots/en-detail.png` | Window detail `e4-monitor_probe-20260922-124142-0006`: T1 vs T2 per-question comparison rows (tactic/urgent/severity/action), approve ✓ / veto ✗ / relabel dropdowns, Window-level Confirm/Reject + note input, State panel, evidence panel | 1440×1000 |

Captured against a second server instance on `127.0.0.1:8025` (started and stopped by this session; the shared `:8024` instance was never touched).

## 3. Verification

1. **Zero-Chinese check (script)**: `grep [\u4e00-\u9fff]` over full `en.html` → **0 Chinese characters** (the 12 hanzi found are inside the `enNarr()` regex literals that translate data labels at display time; for comparison `index.html` contains 190).
2. **Visual check of both PNGs**: nav (Queue/Replay/Dashboard/Labeling/About), table headers (Window ID/Scenario/Source/Routing path/Per-question confidence/Status/Decision), buttons, narrative box, State panel — **no CJK characters anywhere** (only τ/·/≥ symbols).
3. Playwright text assertions passed on the detail page (`Per-question comparison`, `Window-level Confirm` present).

## 4. Notes

- Paper currently references `ui/screenshots/demo-queue.png` (Chinese) — swap to `en-queue.png`/`en-detail.png` is on the paper side, not done here.
- Detail screenshot window routed `tier1_laya→tier3_human` (no T2 run for that window — T2 column shows `—`, expected gating behavior; two-tier windows visible in en-queue.png routing paths).
