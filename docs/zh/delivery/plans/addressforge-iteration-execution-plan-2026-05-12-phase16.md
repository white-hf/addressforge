# AddressForge 迭代执行计划 - 2026-05-12 (Phase 16: CandidateRerankerModel Completion)

## 文档信息
- 文档类型：Execution Plan / Supervised Reranking Delivery Plan
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：完成真正监督学习的 candidate reranking

## 1. 当前背景与问题定义
当前 reranking 仍存在两个问题：
1. 服务层已经预留 `CatBoost` reranker 入口
2. 训练层仍主要是统计权重，不是完整监督模型闭环

因此当前不是“没有 reranker”，而是“reranker 还没有真正完成”。

## 2. 当期总目标
1. 建立 candidate 监督样本定义
2. 训练真正的 `CandidateRerankerModel`
3. 让 `RerankerService` 真正消费监督模型

## 3. 具体需求

### 需求 16-1：真实监督式 reranker 训练
交付要求：
- 明确 candidate winner/loser 或 pointwise score label
- 导出真正的 `.cbm` reranker artifact

### 需求 16-2：Candidate feature schema v1
交付要求：
- 候选特征必须有统一 schema
- 至少覆盖：
  - parser source
  - candidate completeness
  - unit hint alignment
  - numbered-road conflict
  - semantic alignment

### 需求 16-3：reranker compare/shadow
交付要求：
- 比较：
  - old weight-based ranking
  - supervised reranker
- 量化对 best candidate 选择、building_type、unit 的提升

## 4. 技术方法
- **Pairwise/pointwise CatBoost baseline**
  - 先用树模型完成第一版 reranker。
- **Semantic alignment as structured feature**
  - retrieval 结果作为 feature，而不是黑盒替代 parser。
- **Best-candidate error audit**
  - 建立错误 best candidate 回流机制。

## 5. 预期收益
- 降低 wrong best candidate
- 稳定 apartment/unit 主线
- 为 retrieval 融合提供可靠排序基础

## 6. 交付物
- `CandidateRerankerModel v1`
- reranker `.cbm` artifact
- compare report
- shadow report

## 7. 完成标准
1. `RerankerService` 真正消费监督模型
2. reranking 不再主要依赖旧权重法
3. 对 best candidate 选择有明确提升

## 8. 后续衔接
Phase 16 完成后，进入：
- `Phase 17: BuildingTypeModel + Retrieval Fusion`

