# AddressForge: Next-Generation Address Intelligence Engine

AddressForge is a next-generation address intelligence and entity resolution engine. Moving beyond traditional regex string parsing (Parser-first), AddressForge shifts to a **Retrieval-First / Entity Resolution** paradigm, resolving raw address descriptions to unique physical geospatial entities.

---

## 🏗️ Core Architecture (v2.1 - v2.5 Evolution)

```mermaid
graph TD
    Input["Raw Address String (with GPS)"] --> Norm["Lightweight Normalization (core/utils)"]
    Norm --> DualRetrieval["Dual Retrieval Gateway (core/retrieval)"]
    DualRetrieval -->|BGE-Small dense vectors| VectorRet["FAISS Dense Semantic Retrieval"]
    DualRetrieval -->|ST_DWithin equivalents| GpsFilter["GPS Spatial Filtering (250m Gate)"]
    VectorRet & GpsFilter --> Merge["Candidate Pool Generation"]
    Merge --> MLRank["ML Tri-Model & Reranking"]
    MLRank -->|Pairwise match probability| Reranker["CatBoost Reranker Model"]
    MLRank -->|Structure constraint| BTModel["BuildingType Model (Guarded Override)"]
    Reranker & BTModel --> Decision["Confidence Calibration (DecisionModel)"]
    Decision -->|Auto-Accept Assist| OutputAccept["Structured Address Asset (Accept)"]
    Decision -->|Ambiguity Guard| OutputReview["Expert Review Queue (Review)"]
    OutputReview -->|Ollama / Qwen-2.5| LlmRefiner["Local LLM Prescreen (Silver Labels)"]
```

---

## 🚀 Key Features

### 1. Dual Retrieval & Numerical Precision (v2.3)
- **Vector Semantic Search**: Encodes input queries into 384-dimensional dense vectors using `bge-small-en-v1.5` embeddings, matched against the standard database via FAISS.
- **GPS Spatial Constraint**: Filters and ranks candidates based on physical distance using the Haversine formula (within a $250\text{m}$ gate: `ADDRESSFORGE_GPS_CONFLICT_METERS`).
- **GPS Conflict Guard**: Flags mismatched query-reference coordinates with `gps_conflict = True` to prevent vector similarity hallucinations and skip invalid ML reranker alignment.

### 2. Tri-Model Orchestration & Guarded Overrides
- **Reranker Model**: Pairwise learning comparing query-candidate features (edit distance, text alignment, postal matched, and semantic alignment).
- **BuildingType Model**: Classifies single-unit vs multi-unit structures. When $\ge 0.85$ confidence for single-unit is met, a guarded override removes phantom unit numbers, preventing false alarms.
- **Decision Model (Assist Mode)**: Evaluates confidence boundaries. In `assist_trial` mode, high-confidence model validations automatically skip manual queue backlogs.
- **LLM Refiner**: Integrates local Ollama/Qwen for edge-case diagnostics, generating draft corrections and `silver_label` suggestions.

### 3. Continuous Ingestion & Cleaning Pipeline (v2.1 - v2.2)
- **Composite Cursor Pagination**: Database-driven ingestion uses `updated_at + external_id` cursors for safe incremental synchronization.
- **Chained Trigger Processing**: Successful ingestion automatically chains to a `run_cleaning_once` job.
- **Feature Flags Tagging**: Auto-tags flags like `has_double_number`, `is_numbered_road`, and `has_explicit_unit` on ingestion, serving as indices for Active Learning queue filters.

### 4. Reference Fusion & Unit Mining (v2.4)
- **Multi-Source Reference Fusion**: Groups and merges duplicate reference data (from OSM, GeoNova, manual sources) sharing the same base address, preserving provenance in JSON attributions.
- **Delivery Unit Mining**: Mines valid unit numbers from highly successful historical transactions ($\ge 0.90$ confidence accepts) and dynamically backfills them into the canonical unit library to reduce future `enrich` gaps.

### 5. Hardened Promotion & Rollback Consistency (v2.5)
- **Consistency Gate**: Promote operations automatically verify physical artifact completeness (`.pkl`, `.json`, `.cbm`) of all three models on disk.
- **Emergency Rollback**: Supports instant rollback to the last known stable manifest, invalidating runtime TTL caches.

---

## 🔰 5-Minute Quick Start Guide for Newcomers

If you are an ML novice or a technical newcomer looking to clean your company's address data, AddressForge is designed to be extremely friendly. You don't need to know CatBoost ranking formulas or vector mathematics—you can operate it using a **Simple Command Line** or a **Web Console User Interface**.

### 💡 Think of AddressForge as a Smart Mailman:
1. **Input**: You feed it messy, handwriting-style raw address strings (Raw Address).
2. **Dense Recall (Vector)**: The engine searches the database to find the closest matching buildings.
3. **ML Decision (Calibration)**: The engine inspects units, formats, and GPS coordinates to decide if it's safe to accept, needs manual review, or should be rejected.
4. **Output**: You get clean, canonical address records ready to be stored in your database.

---

### 🖥️ Option A: Managing via the User-Friendly Web Console (Zero-Code)

The Web Console (Control Center) is the recommended interface for business operators and non-technical users to manage settings, load data, and handle reviews.

1. **Configure Ingestion Sources**: Open your browser and navigate to `http://127.0.0.1:8011/settings` (Console port is `8011`). Enter your database connection details (host, table, cursor columns) directly in the GUI. Click **"Test Connection"** and save.
2. **Trigger One-Click Sync & Clean**: Go to the Dashboard page and click the **"Run Ingestion Now"** button. The engine will import raw records and automatically chain-execute the incremental cleaning job.
3. **Handle Reviews (Review Lab)**: Go to the **Review Queue** tab. Unresolved/ambiguous addresses are listed side-by-side. View pre-screened LLM drafts, make manual edits, and click **"Approve"** to save standard addresses (which also builds Gold training sets automatically).
4. **Promote & Rollback Models**: On the **Model Registry** tab, review Decision F1 and review rate charts. Click **"Promote to Active"** to live-deploy a new candidate model, or click **"Rollback"** to instantly revert to the previous version.

---

### 🛠️ Option B: Managing via Command-Line (For Developers)

If you prefer using scripts and terminals, you can run the same pipeline in three quick steps:

#### Step 1: Import raw address data
Add your raw address data in a CSV template and load it:
```bash
# Load your company raw address CSV file
bash scripts/import_csv.sh path/to/your/company_addresses.csv
```

#### Step 2: Run the incremental cleaning pipeline
Execute the spatial-vector dual retrieval and tri-model cleaning pipeline:
```bash
# Triggers incremental sync and updates canonical address records
PYTHONPATH=src .venv/bin/python -c "from addressforge.services.fusion_service import run_reference_enrichment_pipeline; run_reference_enrichment_pipeline()"
```

#### Step 3: Extract cleaned structured outputs
Query the MySQL database to retrieve the accepted, high-confidence structured addresses:
```sql
-- Query clean accepted addresses directly from your database
SELECT raw_address_text, suggested_unit_number, base_address_key 
FROM address_cleaning_result 
WHERE decision = 'accept';
```

#### 1-Line Sandbox Playground
Test any single address interactively by sending a cURL validation request to the local API (Port `8010`):
```bash
curl -X POST http://127.0.0.1:8010/api/v1/validate \
     -H "Content-Type: application/json" \
     -d '{"raw_address_text": "unit 4 - 47 Albro lake rd Halifax"}'
```

---

### ❔ Newcomer Q&A

* **Q: Do I need to train machine learning models to start?**
  * *A*: No. AddressForge comes with a pre-trained baseline model that runs out-of-the-box.
* **Q: How does the system improve itself over time?**
  * *A*: Any manual changes approved in the Web Console are recorded as Gold labels. Running the evolution cycle (`bash scripts/run_evolution_cycle.sh`) will retrain the CatBoost models on these new corrections, making the engine smarter with zero hyperparameter tuning.

---

## 🛠️ Project Structure

```text
src/addressforge/
├── api/            # Public Normalization, Parsing, Validation, and Admin APIs
├── console/        # Control Center & Review Lab Web Application Server
├── control/        # Background Worker and Distributed Job Queue Processors
├── core/           # Core Engines: retrieval (FAISS), reference matcher, and normalization profiles
│   └── profiles/   # Localization profiles (base_canada, etc.)
├── learning/       # Model Trainer, Evaluator, and Active Learning features
├── pipelines/      # Orchestrated pipeline scripts (exports, schemas, shadow runs)
└── services/       # Business logic (asset management, model manifest reloading, replay, fusion)
```

---

## 🚀 Operations SOP

### 1. Vector Index Construction
Build the FAISS dense retrieval indexes from active external reference databases:
```bash
PYTHONPATH=src .venv/bin/python scripts/build_vector_index.py
```

### 2. Run Reference Fusion & Unit Mining
Perform multi-source building merging and backfill unit numbers from historical successes:
```bash
PYTHONPATH=src .venv/bin/python -c "from addressforge.services.fusion_service import run_reference_enrichment_pipeline; run_reference_enrichment_pipeline()"
```

### 3. Training & Evaluation Cycle
Train the CatBoost tri-model set (Decision, Reranker, BuildingType) and evaluate against the benchmark:
```bash
# Run full training pipeline
bash scripts/run_evolution_cycle.sh

# Run model evaluation report
PYTHONPATH=src .venv/bin/python scripts/run_latest_eval.py
```

### 4. Running the Test Suite
Ensure zero regression on address validation logic:
```bash
PYTHONPATH=src .venv/bin/pytest tests/
```

---

## 📖 Key Documentation

Detailed design specifications can be found under the `docs` folder:
- **Retrieval-First Evolution**: [retrieval_first_evolution_spec.md](docs/en/architecture/retrieval_first_evolution_spec.md) ([ZH](docs/zh/architecture/retrieval_first_evolution_spec.md))
- **Ingestion & Cleaning Spec**: [ingestion_cleaning_evolution_spec.md](docs/en/architecture/ingestion_cleaning_evolution_spec.md) ([ZH](docs/zh/architecture/ingestion_cleaning_evolution_spec.md))
- **Next-Gen Evolution Roadmap**: [next_generation_roadmap.md](docs/en/architecture/next_generation_roadmap.md) ([ZH](docs/zh/architecture/next_generation_roadmap.md))
- **Metrics Acceptance Gate**: [metrics_acceptance_framework.md](docs/en/governance/metrics_acceptance_framework.md) ([ZH](docs/zh/governance/metrics_acceptance_framework.md))
- **Operation Product Manual**: [operation-subsystem-guide.md](docs/en/operations/operation-subsystem-guide.md) ([ZH](docs/zh/operations/operation-subsystem-guide.md))
- **ML Learning & Customization Guide**: [ml_learning_and_customization_guide.md](docs/en/getting-started/ml_learning_and_customization_guide.md) ([ZH](docs/zh/getting-started/ml_learning_and_customization_guide.md))

---
*AddressForge: Resolving address strings to intelligent spatial assets.*
