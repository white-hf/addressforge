# ⚙️ System Requirements, Data Guidelines & Model Evaluation Metrics

This document outlines the hardware and software specifications needed to run AddressForge, the dataset requirements for machine learning (ML) capability, and the core metrics used to evaluate new models.

---

## 1. System Requirements (运行环境与软硬件要求)

### 💻 Hardware Requirements (硬件配置)
- **Minimum Requirements (最低配置)**:
  - **CPU**: 1-Core CPU.
  - **RAM**: 2GB RAM.
  - **Storage**: ~500MB of free space for source code and models, plus database storage (~100MB per 200,000 raw address records).
  - *Suitable for*: API serving and light query routing.
- **Recommended Requirements (推荐配置)**:
  - **CPU**: 4-Core CPU or higher.
  - **RAM**: 8GB+ RAM.
  - *Suitable for*: High-throughput batch cleaning (up to 130+ items/sec), offline vector embedding generation (using `bge-small-en-v1.5`), and fast CatBoost training.

### 🔌 Software Requirements (软件要求)
- **Operating System**: macOS, Linux (Ubuntu/Debian recommended), or Windows (via WSL2).
- **Runtime**: **Python 3.8+** (System is validated on Python 3.14.5).
- **Database Backend**: **MySQL 8.0+** (stores raw address records, cleaning results, active learning queues, and reference building assets).
- **Core Python Libraries** (Automatically managed via `requirements.txt`):
  - `sentence-transformers` & `torch`: Pre-trained text embeddings generation.
  - `faiss-cpu`: Dense vector similarity search index.
  - `catboost`: Gradient Boosted Decision Tree (GBDT) classification and pairwise ranking.
  - `mysql-connector-python`: C-extended MySQL driver.
  - `fastapi` & `uvicorn`: High-performance asynchronous API endpoints.

---

## 📊 2. Dataset Guidelines: Quantity & Quality (数据量与数据质量要求)

To achieve high-accuracy address normalization and entity resolution, your company's data should satisfy these guidelines:

### 📥 Reference Data Size (基础建筑物库数据量)
- **Concept**: The candidate recall pool relies on the `external_building_reference` table.
- **Minimum**: For local tests, a few thousand building records are enough.
- **Production**: To cover a major city or province, you need **10,000 to 500,000+** reference addresses. The higher the coverage of your reference data, the lower the `enrich` routing rate.

### 🏷️ Gold Label Dataset Size (标注训练集数据量)
- **Startup / Bootstrap**: **200 to 500** human-verified correct addresses (`gold_label`) are sufficient to train an initial CatBoost Reranker and Decision Model using cross-validation.
- **Production Grade**: **1,000 to 5,000+** active learning samples are recommended to calibrate confidence thresholds and handle complex apartment structures.

### ⚠️ Data Quality Standards (数据质量要求)
- **Coordinates Precision**: Reference coordinates (`reference_lat`, `reference_lon`) must have a precision of **$\le 10$ meters**. Large GPS errors will trigger false `gps_conflict` alarms.
- **Gold Label Integrity**: Human Gold labels must be **100% accurate**. Programmatically generated draft labels (e.g., silver labels from LLMs) must not be treated as human gold unless verified by an operator.
- **Addressing Diversity**: Training sets must have a balanced composition of single-unit houses, multi-unit apartments, and commercial structures to prevent the models from collapsing into a simple unit extractor.

---

## 📈 3. Model Evaluation Metrics (模型评估指标)

When you train a new model version, AddressForge calculates a comprehensive set of metrics to compare the new candidate against the active baseline:

| Metric Name (指标名称) | Concept (概念) | Passing Threshold (准入出口标准) |
| :--- | :--- | :--- |
| **Decision F1 (决策 F1)** | Measures overall correctness of final decisions (`accept` vs `review` vs `reject`). | **$\ge 0.95$** (or showing improvement of **$\ge +3.0\%$** over baseline). |
| **Review Rate (人工审核率)** | The percentage of addresses routed to manual queues. | Aim to **decrease by $\ge 15\%$** (to save human labor). |
| **Building Type F1 (建筑类型 F1)** | Measures classification accuracy of single-family houses, apartments, and commercial structures. | **$\ge 0.97$** (protecting single-family precision). |
| **Unit Number Recall** | Percentage of actual apartment units correctly identified. | **$\ge 0.70$** |
| **Unit Number Precision** | Percentage of identified units that are correct (prevents parsing street numbers as units). | **$\ge 0.98$** |
| **Regression Risk (回归风险)** | Percentage of addresses correctly resolved by the baseline model but failed by the candidate. | **$\le 0.05$** (max 5% regression allowed). |
| **Disagreement Win Rate** | Candidate win rate on samples where the candidate and baseline decisions differ. | **$\ge 90\%$** |
| **Latency Delta (时延变动)** | Request response latency increase per address. | **$\le 10\text{ms}$** |
