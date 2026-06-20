# ⚙️ 运行环境要求、数据标准与模型评估指标

本文档概述了运行 AddressForge 所需的软硬件规范、机器学习（ML）能力的数据集规模与质量要求，以及用于评估新模型效果的核心指标体系。

---

## 1. 运行环境与软硬件要求 (System Requirements)

### 💻 硬件配置 (Hardware Requirements)
- **最低配置 (Minimum Requirements)**:
  - **CPU**: 单核 CPU (1-Core CPU)。
  - **内存 (RAM)**: 2GB 内存。
  - **存储空间 (Storage)**: 约 500MB 空间用于存放源代码与基础模型，另外需要额外的数据库存储空间（每 200,000 条原始地址记录约需 100MB）。
  - *适用场景*: API 接口服务部署、轻量级查询路由和开发调试。
- **推荐配置 (Recommended Requirements)**:
  - **CPU**: 4核 CPU 或更高配置。
  - **内存 (RAM)**: 8GB+ 内存。
  - *适用场景*: 高吞吐量的批量地址清洗（单机可达 130+ 条/秒）、离线向量嵌入生成（基于 `bge-small-en-v1.5`）以及快速的 CatBoost 模型训练。

### 🔌 软件要求 (Software Requirements)
- **操作系统**: macOS, Linux (推荐 Ubuntu/Debian) 或 Windows (通过 WSL2 运行)。
- **运行环境**: **Python 3.8+** (系统已在 Python 3.14.5 版本下完成完整验证)。
- **数据库后端**: **MySQL 8.0+** (用于存储原始地址记录、清洗结果、主动学习队列以及标准建筑物库资产)。
- **核心 Python 依赖库** (已通过 `requirements.txt` 自动管理):
  - `sentence-transformers` & `torch`: 预训练文本向量嵌入生成。
  - `faiss-cpu`: 密集向量相似度检索索引。
  - `catboost`: 梯度提升决策树 (GBDT) 分类与成对排序。
  - `mysql-connector-python`: 带有 C 扩展的高性能 MySQL 驱动。
  - `fastapi` & `uvicorn`: 高性能异步 API 接口服务。

---

## 📊 2. 数据量与数据质量要求 (Dataset Guidelines)

为了实现高精度的地址规范化与实体解析，您公司的地址数据应满足以下基本指导原则：

### 📥 基础建筑物库数据量 (Reference Data Size)
- **概念说明**: 候选地址召回池依赖于标准化的 `external_building_reference` 表。
- **最低要求**: 进行本地测试或跑通流程时，几千条建筑物记录即可。
- **生产环境**: 覆盖一个主流城市或省份，通常需要 **10,000 到 500,000+** 条标准建筑物参考地址。标准参考库覆盖率越高，进入 `enrich`（需要补全）路由的比例就越低。

### 🏷️ 标注训练集数据量 (Gold Label Dataset Size)
- **冷启动 / 引导阶段**: **200 到 500 条** 经人工校验正确的地址 (`gold_label`) 就足够利用交叉验证来训练初始的 CatBoost Reranker 排序模型和 Decision 决策模型。
- **生产级别**: 建议积累 **1,000 到 5,000+ 条** 主动学习样本，用于精确校准置信度阈值并处理复杂的公寓/房间号单元结构。

### ⚠️ 数据质量标准 (Data Quality Standards)
- **经纬度精度**: 建筑物参考经纬度坐标 (`reference_lat`, `reference_lon`) 的定位精度必须在 **$\le 10$ 米** 以内。过大的 GPS 偏差会触发 `gps_conflict`（GPS 冲突）警报。
- **黄金标签完整性**: 人工标定的黄金标签 (Gold Labels) 必须保证 **100% 准确**。程序自动生成的草稿标签（例如大语言模型生成的银标签）在未经人工校验前，绝不能标记为 `label_source = human` 混入黄金训练集。
- **地址多样性**: 训练集必须包含合理比例的单户住宅 (single-unit houses)、多单元公寓 (multi-unit apartments) 以及商业建筑 (commercial structures)，以防止模型退化为纯粹的“单元房间提取器”。

---

## 📈 3. 新模型效果评估指标 (Model Evaluation Metrics)

当您训练或进化出一个新的模型版本时，AddressForge 会计算一整套全面的评估指标，并将新候选模型（Candidate）与当前线上活跃模型（Active Baseline）进行对比，告诉您模型在各项维度上的效果变化：

| 指标名称 (Metric Name) | 指标概念与含义 (Concept) | 准入出口标准 (Passing Threshold) |
| :--- | :--- | :--- |
| **决策 F1 值 (Decision F1)** | 衡量最终系统分类决策（`accept` 自动采纳 vs `review` 人工审核 vs `reject` 驳回）的整体正确率与召回率。 | **$\ge 0.95$** (或相比 Baseline 提升 **$\ge +3.0\%$**)。 |
| **人工审核率 (Review Rate)** | 自动流转到人工审核队列的地址占总处理量的比例。 | 目标降低 **$\ge 15\%$** (以极大节省人工运营成本)。 |
| **建筑类型 F1 值 (Building Type F1)** | 衡量系统将地址划分为单户住宅、公寓、商用建筑的分类准确率。 | **$\ge 0.97$** (重点防范单户住宅被误判为公寓)。 |
| **单元号召回率 (Unit Number Recall)** | 实际存在公寓单元/房间号的地址中，被系统正确识别出房间号的比例。 | **$\ge 0.70$** |
| **单元号精确率 (Unit Number Precision)** | 系统提取出的单元房间号中，确实是房间号而非路号等噪声的比例。 | **$\ge 0.98$** |
| **回归风险 (Regression Risk)** | 在 Baseline 能够正确解析的样本中，新候选模型却解析失败的比例。 | **$\le 0.05$** (最大允许 5% 的回归损失)。 |
| **分歧样本胜率 (Disagreement Win Rate)** | 在新旧模型决策不一致的“分歧样本”中，新模型决策正确的比例。 | **$\ge 90\%$** |
| **时延变动 (Latency Delta)** | 单条地址请求在 API 接口的平均响应时间增加量。 | **$\le 10\text{ms}$** |
