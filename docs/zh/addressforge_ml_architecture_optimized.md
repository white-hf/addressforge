# AddressForge ML Architecture Evolution (Optimized Version)
## 下一代地址智能系统 ML 演进设计文档（优化版）

> 基于 AddressForge 当前系统现状，对现有 ML 架构进行重新分析、抽象与升级设计。
> 本文重点不再只是“解释当前系统”，而是：
>
> - 从现代 ML System Design 角度重新审视当前架构
> - 明确 Address Intelligence 的真正问题本质
> - 重新划分 Rule / Parser / Retrieval / ML 的职责边界
> - 给出真正可持续演进的 ML 架构路线

---

# 1. 核心结论（Executive Summary）

当前 AddressForge 最大的问题：

不是：

规则不够

也不是：

模型不够复杂

而是：

当前系统的“系统中心”仍然是 Parser + Rule

而不是：

Retrieval + Ranking

这是最本质的问题。

---

当前系统虽然已经引入：

- weight learning
- decision calibration
- pairwise scoring
- gold/eval/shadow/release gate

但：

它的主控制流仍然是：

Rule
→ Parser
→ Threshold
→ Decision

而不是：

Candidate Retrieval
→ ML Ranking
→ Canonical Resolution

这意味着：

当前 ML：

本质上只是：

“规则系统上的统计增强层”

而不是：

“真正的数据驱动地址智能系统”

---

# 2. 当前系统真正的问题是什么

当前系统最核心的问题是：

“Parser-first Architecture”

---

# 2.1 Parser-first 的天然问题

当前系统本质：

原始地址
↓
parser
↓
规则修正
↓
候选
↓
权重调整
↓
decision

问题在于：

parser 不是真实世界。

parser：

只是：

“一种对地址的猜测”

而：

真实地址问题：

本质是：

Entity Resolution Problem（实体解析问题）

不是：

Text Parsing Problem（文本解析问题）

---

# 2.2 为什么 parser 永远会碰天花板

例如：

SUSHI ON BROAD INC226 BROAD ST UNIT107BEDFORD NS

parser 天然困难：

因为：

- company name
- street name
- unit number
- venue name

混在一起。

真正问题不是：

怎么 parse

而是：

“它到底对应哪个真实地址实体”

---

# 2.3 地址系统真正本质

现代 Address Intelligence：

本质是：

Retrieval + Resolution

而不是：

Parsing

---

# 3. Address Intelligence 正确架构（最重要）

---

# 3.1 当前架构（旧）

Rule
→ Parse
→ Validate
→ Threshold
→ Decision

ML：

只是：

校准器

---

# 3.2 下一代架构（推荐）

真正现代架构：

Normalize
→ Embedding
→ Candidate Retrieval
→ ML Ranking
→ Canonical Resolution
→ Decision

即：

Retrieval-first Architecture

---

# 3.3 为什么 Retrieval-first 更正确

因为：

真实世界：

地址不是“文本”

而是：

地理实体（Geospatial Entity）

用户输入：

只是：

对实体的模糊描述。

---

例如：

apt 3 1555 barrngton

系统真正问题：

不是：

如何parse

而是：

“它最像哪个真实地址实体”

---

# 4. 对当前 ML 设计的重新评价

---

# 4.1 当前系统不是“没有 ML”

当前系统已经具备：

- gold
- evaluation
- calibration
- pairwise weighting
- shadow/release gate

这已经是：

很成熟的 ML System Engineering

---

# 4.2 当前系统缺的不是“更多 feature”

真正缺的是：

“系统主导权”

目前：

主导系统的是：

parser + rule

ML：

只是：

附属修正层

---

# 4.3 正确方向不是“更复杂 parser”

而是：

“让 ML 主导 Candidate Resolution”

---

# 5. Address ML 真正应该学习什么

真正核心任务：

不是：

文本分类

而是：

Entity Matching

---

# 5.1 下一代系统真正应该学习什么

下一代系统真正应该学习：

“地址相似性空间”

即：

Address A
Address B
↓
是否同一真实实体

---

# 6. 推荐的新 ML 分层（重要）

---

# 6.1 Layer 1 — Parsing Layer

职责：

仅负责：

基础结构恢复

包括：

- tokenization
- normalization
- province/city extraction
- unit hint extraction

不要让 parser：

决定：

最终真实地址

---

# 6.2 Layer 2 — Retrieval Layer（核心）

新增：

Address Embedding Retrieval

系统中心迁移到这里。

核心思想：

输入地址
↓
embedding
↓
Top-K similar canonical addresses

---

# 6.3 Layer 3 — ML Ranking Layer

真正的核心 ML。

输入：

query
+
candidate

输出：

same-address probability

---

# 6.4 Layer 4 — Resolution Layer

负责：

最终 canonical address resolution

---

# 6.5 Layer 5 — Decision Layer

最后：

accept / review / reject

---

# 7. 为什么当前系统会出现 Decision F1 天花板

真正原因：

不是：

threshold 没调好

而是：

decision 不应该建立在 parser 结果上。

正确方式：

应该建立在：

candidate resolution confidence

之上。

---

# 8. CatBoost 是正确方向，但还不够

CatBoost / XGBoost 是正确方向。

因为当前：

已经有：

- parser confidence
- candidate score
- unit hint
- disagreement feature

这些：

非常适合：

GBDT

---

# 8.1 但真正长期核心不是 GBDT

长期真正核心：

仍然会是：

Embedding + Retrieval

因为：

地址问题：

本质：

semantic entity matching

---

# 9. 推荐真正下一代架构（重点）

新主链：

Input Address
↓
Normalization
↓
Embedding
↓
Vector Retrieval
↓
Candidate Set
↓
GBDT Ranking
↓
Canonical Resolution
↓
Decision

---

# 9.1 Parser 不再是中心

parser：

降级为：

feature provider

而不是：

主控制器

---

# 10. 推荐技术栈（优化版）

## 10.1 Parsing

- libpostal
- RapidFuzz

## 10.2 Embedding

推荐：

BAAI/bge-small-en-v1.5

## 10.3 Retrieval

推荐：

pgvector

## 10.4 Ranking

推荐：

CatBoost

原因：

- 类别特征强
- 缺失值强
- 小数据集优秀
- ranking 支持成熟

## 10.5 Database

推荐：

PostgreSQL + PostGIS

---

# 11. 推荐新的训练目标（非常关键）

未来：

应该训练：

Address Pair Matching

训练样本：

输入：

query address
candidate canonical address

标签：

same_entity = 0/1

---

# 11.1 真正学习内容

模型学习：

- street similarity
- semantic similarity
- unit ambiguity
- parser disagreement
- commercial noise
- geo alignment

之间的：

非线性交互

这是：

当前 weight calibration：

学不到的。

---

# 12. 为什么不要直接上 Transformer End-to-End

原因：

地址系统：

不是：

生成任务

而是：

高精度实体解析任务

---

# 12.1 LLM 最大问题

- hallucination
- 不稳定
- 不可控
- 难解释
- 成本高

---

# 12.2 真正适合的位置

未来：

LLM 更适合：

Hard Case Reasoning

例如：

- company name
- venue name
- landmark ambiguity

而不是：

主解析链

---

# 13. 推荐真正的 ML 演进路线（最终版）

## Phase 1（当前）

Parser + Rule + Calibration

## Phase 2（推荐立即做）

新增：

Embedding Retrieval

## Phase 3

新增：

CatBoost Candidate Ranking

## Phase 4

Decision：

从：

threshold-based

迁移到：

confidence-based

## Phase 5

新增：

Online Learning

学习：

human correction feedback

## Phase 6（未来）

Hard-case LLM reranker

---

# 14. 对整个系统最重要的重新定义（最终核心）

当前系统：

定义是：

Address Parsing System

这是不够准确的。

真正应该重新定义为：

Address Intelligence Resolution System

因为：

真正任务不是：

parse address

而是：

“解析现实世界中的地址实体”

---

# 15. 最终结论（Final Conclusion）

当前系统真正优秀的地方：

- parser 主链
- gold/eval/release gate
- human review
- calibration
- shadow validation

这些：

已经构成：

成熟 ML System Infrastructure

---

当前系统真正缺什么：

缺的不是：

更多规则

也不是：

直接上神经网络

而是：

Retrieval-first ML Architecture

---

下一代最合理演进：

真正正确方向：

Parser
→ Feature Provider

Embedding Retrieval
→ System Center

CatBoost Ranking
→ Core Decision Engine

---

# 最终一句话总结

AddressForge 当前已经拥有：

“成熟的数据闭环”

但：

还没有真正完成：

“从 Parser-first 到 Retrieval-first 的 ML 架构跃迁”。
