# 🎓 进阶指南：通过构建你自己的地址模型来学习机器学习

欢迎！如果你是一名机器学习（ML）新手或技术新人，渴望在开发实用软件的同时学习并应用 ML，那么这份指南非常适合你。

AddressForge 是一个真实世界中的**实体消歧与地址标准化**系统。通过将其定制为解析和清洗**你自己国家**的地址，你将学习并应用以下核心 ML 概念：**句子嵌入（Sentence Embeddings）、向量检索（Vector Search）、梯度提升树（GBDTs）和主动学习（Active Learning）**。

---

## 📚 核心 ML 概念与权威学习资源

以下是 AddressForge 中使用的机器学习技术的解释，以及学习和研究它们的权威资源链接：

### 1. 文本嵌入与向量检索 (Text Embeddings & Vector Search)
- **概念解释**：将文本段落转换为一个包含数值的向量（例如 384 维），以便用数值度量文本的语义。相似的文本（例如 "123 Main Street" 和 "123 Main St."）在向量空间中的物理距离会非常接近。我们使用 **FAISS** (Facebook AI Similarity Search) 来对百万级别的标准建筑物经纬度与文本进行索引，并在几微秒内完成检索。
- **底层模型**：基于 Transformer 的 Encoder 模型 `BAAI/bge-small-en-v1.5`，通过 PyTorch 加载。
- **推荐学习资源**：
  - [Hugging Face NLP Course: Semantic Search](https://huggingface.co/learn/nlp-course/chapter5/5?fw=pt) (最权威的 NLP 交互式教程)
  - [Pinecone Vector Search Learning Center](https://www.pinecone.io/learn/vector-search/) (关于 FAISS、HNSW 等向量索引算法的极佳可视化教程)
  - [SentenceTransformers 官方文档](https://www.sbert.net/) (Python 嵌入模型库的使用说明)

### 2. 表格机器学习与梯度提升树 (Tabular ML & GBDTs)
- **概念解释**：尽管深度学习在图像和文本生成中占据主导地位，但在处理结构化表格特征（如文本编辑距离、经纬度物理差距、邮编对齐度）时，**梯度提升决策树 (GBDTs)** 依然是业界公认性能最强的模型。AddressForge 使用 **CatBoost** 来对召回的候选进行两两对比排序（Pairwise Reranking），并校准自动 Accept 的置信度。
- **推荐学习资源**：
  - [StatQuest: Gradient Boost Explained (YouTube 视频)](https://www.youtube.com/watch?v=3CC4N4z3GJc) (极其通俗易懂的可视化讲解，强烈推荐)
  - [CatBoost 官方教程与文档](https://catboost.ai/en/docs/concepts/tutorials) (官方提供的动手实践 Jupyter Notebook)
  - [Machine Learning University - Tabular Data Course](https://mlu-explain.github.io/double-descent/) (通俗有趣的交互式 ML 原理解析)

### 3. 主动学习与弱监督 (Active Learning & Weak Supervision)
- **概念解释**：完全用人工标注数据非常昂贵。**主动学习**旨在自动挑选出模型判断最模糊、分歧最大的样本（边缘情况）交给人工审核。**弱监督**则利用启发式正则规则自动生成带噪音的标签（银牌数据），从而快速启动初始模型。
- **推荐学习资源**：
  - [Active Learning Literature Survey by Burr Settles (PDF)](https://burrsettles.com/pub/settles.activelearning.pdf) (主动学习领域公认的研究红宝书)
  - [Snorkel: Weak Supervision & Programmatic Labeling](https://snorkel.org/) (使用弱监督自动标注数据的权威系统框架)

---

## 🛠️ 实操教程：如何为你的国家定制 AddressForge？

按照以下 4 步，你可以将此引擎适配至你所在的国家（例如英国、日本、德国或中国）。

### 第一步：创建本地化的 Normalization Profile
AddressForge 将每个国家特有的地址规则解耦到 `src/addressforge/core/profiles/` 中。
1. 继承 `src/addressforge/core/profiles/base.py` 中定义的 `BaseCountryProfile` 接口。
2. 实现你所在国家的特有简写映射（例如将中文的“路”、“街道”或英文的“Road”做标准化规范）。
3. 定义你所在国家的省份/州列表以及合法的城市名称表。
4. 在 `src/addressforge/core/profiles/factory.py` 中注册你的新 Profile。

* **ML 学习目标**：掌握文本预处理（Text Preprocessing）、正则表达式清洗、以及值域对齐（Domain Constraint Alignment）。

### 第二步：导入你所在国家的参考地址并构建向量索引
为了检索地址，系统需要一个标准地理实体库。
1. 下载公开的地址点数据（例如 OpenStreetMap、Geonames 或你所在国家邮政的公开 Postcodes 数据）。
2. 将其整理为包含以下列的 CSV 文件：`street_number`, `street_name`, `city`, `province`, `postal_code`, `reference_lat`, `reference_lon`。
3. 使用导入服务（参考 `src/addressforge/core/reference.py`）将其批量导入到 `external_building_reference` 表中。
4. 构建你所在国家的 FAISS 向量库：
   ```bash
   # 在本地计算所有标准地址的向量嵌入（Embeddings）并保存为 FAISS 物理索引
   PYTHONPATH=src .venv/bin/python scripts/build_vector_index.py
   ```

* **ML 学习目标**：理解离线向量计算（Offline Inference）、高维向量索引（Indexing）、以及空间距离计算。

### 第三步：运行影子测试收集审核数据
1. 传入你所在公司的真实历史订单地址进行清洗。
2. 打开 Web 可视化控制台（`http://127.0.0.1:8011`），在界面上直接查看清洗结果。
3. 在 `Review Queue`（审核队列）中，对有疑问的地址进行人工修正并批准。你的每一次修正都会作为金牌标注（Gold label）存入 `gold_label` 表。
4. 运行此过程以积累几百条到上千条针对你所在国家的人工确认数据。

* **ML 学习目标**：体验人机协同（Human-in-the-loop）标注流程、主动学习数据采样策略、以及处理分类不平衡问题。

### 第四步：重新训练 CatBoost 分类与排序模型
现在，让模型学会你所在国家特有的空间与文本匹配规律：
1. 训练重排模型：
   ```bash
   # 自动挖掘硬负样本并训练 Pairwise Reranker 模型
   PYTHONPATH=src .venv/bin/python scripts/train_reranker_model.py
   ```
2. 训练决策与阈值校准模型：
   ```bash
   # 训练置信度校准模型，自动平衡 Decision F1 与人工审核率
   PYTHONPATH=src .venv/bin/python scripts/train_decision_model.py
   ```
3. 运行本地测试集以确保上线安全：
   ```bash
   PYTHONPATH=src .venv/bin/pytest tests/
   ```

* **ML 学习目标**：掌握分类模型评估指标（F1-score、混淆矩阵、召回率/精确率）、两两排序学习（Pairwise Learning to Rank）、模型调优与防过拟合策略。
