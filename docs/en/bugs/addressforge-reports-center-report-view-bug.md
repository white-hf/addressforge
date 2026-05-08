# AddressForge Reports Center View API Missing and Report Artifact Path Mismatch Bug

## Issue Type
- Functional defect
- Broken report viewing flow
- Frontend/backend contract mismatch

## Overview
After operations users run `shadow` or complete training/evaluation, they go to `Reports Center` and click:

- `Quality Report`
- `Evaluation Report`
- `Gold Governance Report`

The UI keeps saying the report is missing, while backend logs show:

- `GET /api/v1/business/reports/view/quality` -> `404`
- `GET /api/v1/business/reports/view/evaluation` -> `404`
- `GET /api/v1/business/reports/view/gold_governance` -> `404`

This is not just a “report not ready yet” case. There is a concrete break between the report-center view entrypoints, the report scanning logic, and the actual artifact locations produced by evaluation/shadow.

## Symptoms
### 1. The Reports Center calls view routes that do not exist
In [reports.html](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/templates/reports.html:141), the frontend calls:

- `viewReport('quality')`
- `viewReport('evaluation')`
- `viewReport('gold_governance')`

which requests:

- `/api/v1/business/reports/view/quality`
- `/api/v1/business/reports/view/evaluation`
- `/api/v1/business/reports/view/gold_governance`

But [business.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/api/routes/business.py:47) only implements:

- `GET /api/v1/business/reports`
- `GET /api/v1/business/reports/download`
- `GET /api/v1/business/benchmark-report`

There is no `/reports/view/{type}` route at all.

### 2. The reports list scans a different directory from where evaluation artifacts are actually written
[business_service.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/services/business_service.py:117) only scans:

- `runtime/reports`

But evaluation-related artifacts are actually split across at least two locations:

- `runtime/reports`
  - `*_release_report.md`
- `runtime/models`
  - `*_eval.md`
  - `*_eval.json`
  - `*_shadow.json`

In the current code:

- the evaluation Markdown release report is written to `runtime/reports`
  - see [evaluator.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/evaluator.py:657)
- benchmark/eval Markdown files still exist in `runtime/models`
  - confirmed by the runtime directory contents
- shadow results are written only as `runtime/models/*_shadow.json`
  - see [shadow.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/shadow.py:191)

So the Reports Center currently has neither a unified view API nor a unified report discovery strategy.

### 3. The report summary fields do not reflect real report types
`get_reports_list()` currently returns summaries like:

- `quality = files[0]["created_at"] if files else "-"`
- `evaluation = "-"`
- `gold = "-"`

That means:

- `quality` is just “the latest arbitrary file timestamp in runtime/reports”
- `evaluation` is always `-`
- `gold` is always `-`

So the top cards can still look empty even if evaluation/governance outputs already exist elsewhere.

## Root Cause Analysis
### Root cause 1: the frontend calls type-specific report view APIs that the backend never implemented
The Reports Center is already organized by:

- quality
- evaluation
- gold_governance

but the backend does not provide corresponding type-specific view handlers.

### Root cause 2: report artifacts do not follow one unified storage contract
Different report outputs are written into different directories:

- `runtime/reports`
- `runtime/models`

and shadow/gold-governance do not consistently produce human-viewable markdown/html outputs.

### Root cause 3: the report-center list logic is not aligned with business semantics
The Reports Center should answer:

- “Where is the latest quality report?”
- “Where is the latest evaluation report?”
- “Where is the latest gold governance report?”

But the current implementation only answers:

- “What files currently exist under runtime/reports?”

That is not the same thing.

## Direct Impact on Operations
- After `shadow`, users cannot confirm from the Reports Center whether a usable result exists
- Clicking `View Evaluation` or `Governance Analysis` leads to 404 or “Report not ready”
- The Reports Center cannot serve as the actual place to inspect training/evaluation/shadow/gate outputs
- Users must fall back to logs, DB inspection, or filesystem inspection
- The product appears to support report viewing, but the viewing path is not actually complete

## This is not a UX-only issue
This is not just about wording or button placement. It is a functional defect because:

- the frontend calls missing APIs
- the backend does not implement the required capabilities
- the report discovery logic does not match the artifact generation logic

It should therefore be handled as a functional bug, not as a pure UX enhancement.

## Required Fix Outcomes for the Architect
### 1. `/api/v1/business/reports/view/{type}` must actually exist
At minimum it must support:

- `quality`
- `evaluation`
- `gold_governance`

and each type must have a deterministic “latest report” lookup path.

### 2. Report artifacts must follow a unified storage contract
The system must define:

- which business reports are written to `runtime/reports`
- which model-level artifacts remain in `runtime/models`
- which outputs the Reports Center is allowed to render

It cannot keep relying on scattered files across unrelated directories.

### 3. Report summaries must be computed per report type
At minimum the API must return:

- latest quality report timestamp
- latest evaluation report timestamp
- latest gold governance report timestamp

It cannot keep using one arbitrary latest file under `runtime/reports` as the `quality` summary.

### 4. Shadow output must be visible in the Reports Center
If shadow is part of the release workflow, then:

- it cannot remain only as a JSON artifact in `runtime/models`
- it must become visible through the Reports Center as either a summary or a detailed report

### 5. The 404s must be eliminated, not masked by frontend toasts
The current frontend fallback `showToast("Report not ready or missing.")` only hides the defect. It does not replace missing routes or missing report-generation behavior.

## Minimum Acceptance Criteria
The following end-to-end flow must work:

1. user runs `evaluation_once` or `shadow_once`
2. the system generates a viewable report for the correct report type
3. the Reports Center top cards show real timestamps
4. clicking `View Evaluation / View Now / Governance Analysis` no longer returns 404
5. the page shows the latest report of that type instead of only offering raw file download links

## Current Conclusion
The core issue with the current Reports Center is:

**the frontend exposes report view entrypoints, but the backend does not implement the matching routes; at the same time, report artifact storage and report-discovery logic are inconsistent, so users still cannot view evaluation/shadow outputs from the Reports Center even after those workflows run.**
