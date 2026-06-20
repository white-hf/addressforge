# AddressForge Retrieval-first ML Evolution & Iteration Plan
## 下一代地址智能系统（v2.0）版本定义与迭代实施排期

本文基于 [retrieval_first_evolution_spec.md](file:///Users/whitetang/Desktop/work/AddressesSystem/addressforge/docs/zh/architecture/retrieval_first_evolution_spec.md) 设计，定义了 AddressForge 升级至“检索优先（Retrieval-first）”架构的版本演进图谱与详细的双周迭代排期计划。

---

## 1. 版本规划与里程碑 (Version Roadmap & Milestones)

我们将下一代地址智能消歧系统的整体演进划分为 4 个主要里程碑版本：

| 版本号 (Version) | 阶段名称 (Stage) | 核心集成内容 (Core Integrations) | 交付成果与出口标准 (Exit Criteria) |
| :--- | :--- | :--- | :--- |
| **v2.0-Alpha1** | **向量召回集成** | 1. 离线建筑物 Embedding 计算与落库<br>2. HNSW 索引服务构建<br>3. 双路检索（BM25 + 向量）服务层封装 | **出口标准**：<br>- 语义检索召回率 Recall@10 $\ge 99.5\%$<br>- 检索阶段单次耗时 $\le 8\text{ms}$ |
| **v2.0-Beta1** | **消歧重排重训** | 1. 构建 Binary `same_entity` 训练样本集<br>2. 训练 CatBoost 实体相似度消歧模型<br>3. 重构决策机制为基于 Confidence 的校准 | **出口标准**：<br>- Reranker 模型 MRR $\ge 0.98$<br>- 离线评测 F1 相比旧版本提升 $\ge 5\%$ |
| **v2.0-RC1** | **Shadow 影子验证** | 1. 线上流量双写（主流程/Shadow 流程）<br>2. 异步特征与决策日志对比<br>3. 收集并人工审核 Disagreement 数据 | **出口标准**：<br>- 连续运行 7 天无系统级 Crash<br>- 在系统判断不一致时，新架构胜出率 $\ge 90\%$ |
| **v2.0-Release** | **全面上线与切流** | 1. 规则 Parser 剥离主链并降级为特征提供器<br> 2. 正式由语义检索控制流主导决策<br>3. 回流 Review 数据，开启增量主动学习 | **出口标准**：<br>- 线上 Accept 准确率 $\ge 99.2\%$<br>- 审核 backlog 自动消化比例提升 $\ge 80\%$ |

---

## 2. 迭代实施排期 (Detailed Iteration Schedule)

整体项目预计开发周期为 **4 周（2 个迭代双周）**。

### 📅 Iteration 1 (第 1 - 2 周): 向量引擎与双路召回打通 (v2.0-Alpha1)

#### 第 1 周：离线向量索引与检索服务
* **[Day 1-2]：标准建筑物向量化建库**
  * 编写离线脚本，使用 `BAAI/bge-small-en-v1.5` 将系统已有的 `canonical_building` 数据库中所有标准地址实体生成 384 维向量。
  * 在数据库中扩展 `canonical_building` 表结构，新增向量存储列（或创建专用的 `canonical_building_embedding` 映射表）。
* **[Day 3-5]：向量检索机制引入**
  * 搭建 HNSWLib 内存向量库，并测试从二进制文件实时加载建筑物向量索引。
  * 编写 `VectorRetrievalService`，实现单条 Query 转换为稠密向量，并在 HNSW 索引中快速检索 Top-K 最优标准建筑物。

#### 第 2 周：双路检索融合与 Recall 验证
* **[Day 6-7]：双路检索融合（Hybrid Retrieval）**
  * 将现有的数据库字面全文检索（FTS/BM25）与向量检索融合。
  * 输入 Query 先经过标准化，并发分发至字面检索与向量检索，对返回的候选建筑物合并去重。
* **[Day 8-10]：Recall 评测与首阶段发布**
  * 运行历史 `gold_label` 数据（1,400+ 样本），统计真实标准建筑物实体是否包含在双路检索的前 10 个候选集中（Recall@10）。
  * 确保召回率达标，封装成统一的 `DualRetrievalGateway` 接口，发布 **v2.0-Alpha1**。

---

### 📅 Iteration 2 (第 3 - 4 周): 实体消歧模型训练与 Shadow 影子验证 (v2.0-Beta1 / RC1)

#### 第 3 周：CatBoost 相似度重排与决策校准
* **[Day 11-12]：训练样本集构建（Negative Mining）**
  * 从 `gold_label` 中导出 Query 和对应的正向 Candidate，并通过双路检索挖掘 Top-9 的硬负样本（相似但不匹配的地址），构建 Pairwise 训练集。
* **[Day 13-14]：实体消歧特征工程与 CatBoost 模型重训**
  * 新增文本编辑距离、数值硬匹配、物理地理距离等交叉特征。
  * 重训 CatBoost Reranker 模型，输出 Query 与 Candidate 是否为同一物理实体的匹配概率。
* **[Day 15]：决策层 confidence 重构与 Beta 发布**
  * 结合 Reranker 概率进行置信度分段校准，发布 **v2.0-Beta1**。

#### 第 4 周：Shadow Verification 影子测试与全面切流 (v2.0-RC1 / Release)
* **[Day 16-18]：Shadow Pipeline 部署与数据回流**
  * 开启后台异步的影子流水线。线上真实流量流入后，在不影响旧版决策响应的前提下，同步走一遍 Retrieval-first 链路。
  * 将两路输出对比结果写入 `historical_replay_result`，对不一致的地址进行人工/LLM审计。
* **[Day 19-20]：Parser 降级与正式切流**
  * 确认影子系统指标无Regression后，重构主干控制流，Parser 改为仅计算特征，不再决定候选。
  * 正式将主流程切换为向量主导的 Retrieval-first 架构，发布 **v2.0-Release**。

---

## 3. 落地所需的环境与数据支撑需求

为确保该排期能够顺利执行，需要准备以下底层资源：
1. **数据准备**：确保 `canonical_building` 表中包含高质量的标准建筑物 ID 映射，以便进行实体索引。
2. **计算资源**：Worker 与 API 节点需配备 1 核及以上闲置 CPU，以支持 `bge-small-en-v1.5` 在本地内存极速推理。
3. **评测基准**：依赖现有的 `test_canadian_address_quality.py` 等单元测试集作为无回归发布的防线。
