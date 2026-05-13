# AddressForge Project Structure Standard

## Document Info
- Document type: Project Structure Standard
- Effective date: 2026-05-12
- Owner: AddressForge Architecture / Engineering
- Status: Active
- Governance basis:
  - `addressforge-agile-delivery`
  - `codex-agile-product-delivery`

## 1. Purpose

This document formally defines the responsibility boundaries of the current AddressForge project structure.

Its purpose is to avoid:
- uncontrolled document growth
- mixing runtime outputs with source or long-lived assets
- overlapping ownership between design, iteration, and summary documents
- unclear placement of tests, scripts, and model artifacts

It does not require an immediate full repository refactor.
From now on:
- new files should follow this standard where possible
- older files should gradually converge when they are substantially updated

## 2. Current Structure Assessment

The project already has a strong base structure:
- `src/addressforge/`
- `docs/zh/`
- `docs/en/`
- `tests/`
- `scripts/`
- `runtime/`
- `sql/`
- `templates/`
- `static/`
- `web/`

So the problem is not lack of structure.
The problem is:

- **the structure exists, but its governance boundaries need to be formalized**

## 3. Top-Level Directory Responsibilities

### 3.1 `src/addressforge/`
Core system source code.

Subdirectory roles:
- `api/` public API routes and server mainline
- `console/` console backend
- `control/` worker, job orchestration, pipeline control
- `core/` common infrastructure, config, parsing base, features, retrieval
- `ingestion/` data intake
- `learning/` training, evaluation, shadow, gold, baseline logic
- `models/` model registry and model-management logic
- `pipelines/` training, cleaning, export pipelines
- `services/` service-layer business logic
- `workspace/` workspace management logic

### 3.2 `docs/`
Formal documentation root.

Language split:
- `docs/zh/`
- `docs/en/`

### 3.3 `tests/`
Test-code root.

Recommended convergence:
- `tests/unit/`
- `tests/integration/`
- `tests/regression/`

Existing tests do not need immediate relocation, but new tests should prefer the layered layout.

### 3.4 `scripts/`
Project-level executable scripts.

Use for:
- ingestion/cleaning/refresh/export/verification scripts
- operational helpers
- one-off repair tools

### 3.5 `runtime/`
Runtime-generated outputs.

Use for:
- `runtime/models/`
- `runtime/reports/`
- `runtime/vector_index/`
- `runtime/exports/`
- logs

### 3.6 `models/`
Long-lived model templates or distributed default model assets.

Use `models/` for static packaged defaults, not for volatile runtime-generated artifacts.

### 3.7 `sql/`
Database schema and migration-related files.

### 3.8 `templates/`
Server-side HTML templates.

### 3.9 `static/`
Static assets.

### 3.10 `web/`
Frontend project source and build outputs.

## 4. Documentation Structure Rules

Even if the project does not immediately move files into nested subfolders, documents should now be understood in these six groups:

1. README / quickstart / workflow
2. product / requirements / roadmap
3. system design / architecture
4. iteration execution plans
5. iteration execution summaries
6. operations / runbooks / UI / benchmarks

## 5. Test Structure Rules

### Current rule
Existing tests can remain where they are until touched.

### New-test guidance
- pure function or local logic:
  - `tests/unit/`
- multi-module/service/DB-mock logic:
  - `tests/integration/`
- long-flow, real-artifact, or regression reproduction:
  - `tests/regression/`

## 6. Separate Runtime Outputs From Source Assets

### Long-lived engineering assets
Should live under:
- `src/`
- `docs/`
- `models/`
- `sql/`

### Runtime-generated outputs
Should live under:
- `runtime/`

### Temporary training noise
Examples:
- `catboost_info/`

Treat these as temporary outputs, not as official structural dependencies.

## 7. Special Current Notes

### 7.1 `addressforge/addressforge/runtime/`
This looks like a historical or duplicated structure.

Recommendation:
- do not expand it as the future standard path
- later clean it up or document its legacy purpose if still needed

### 7.2 `catboost_info/`
CatBoost training noise directory.

Recommendation:
- treat as temporary output
- not part of the formal project layout

## 8. New File Placement Rules

From now on:
- new phase plans:
  - `docs/zh/` and `docs/en/`
- new phase summaries:
  - `docs/zh/` and `docs/en/`
- new design docs:
  - `docs/zh/` and, when needed, `docs/en/`
- new training/evaluation artifacts:
  - `runtime/models/`
- new quality reports:
  - `runtime/reports/`
- new scripts:
  - `scripts/`
- new tests:
  - preferably `tests/unit|integration|regression`

## 9. Execution Principles

1. Do not force a one-shot full repository restructure
2. Standardize **new content first**
3. Gradually align older content when it is already being revised
4. Preserve:
   - working links
   - working script paths
   - working runtime paths

## 10. Summary

AddressForge already has a substantial engineering structure.
The purpose of this standard is not to replace it, but to:

- **formalize the current structure**
- **give future work a stable destination**
- **prevent uncontrolled growth**

