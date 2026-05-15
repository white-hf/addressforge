# AddressForge 迭代执行计划 - 2026-05-12 (Phase 17: BuildingTypeModel And Retrieval Fusion)

## 文档信息
- 文档类型：Execution Plan / ML Task Expansion Plan
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：完成 `BuildingTypeModel` baseline，并让 retrieval 成为稳定融合层

## 1. 当前背景与问题定义
当前 retrieval 已进入系统，但仍更像：
- retrieval-assisted parser

而不是：
- retrieval-first stable fusion layer

同时，`BuildingTypeModel` 还没有正式 baseline 闭环。

## 2. 当期总目标
1. 建立 `BuildingTypeModel v1`
2. 明确 retrieval 在 runtime 中的融合边界
3. 开始用 ML 处理 commercial/incomplete 残余桶

## 3. 具体需求

### 需求 17-1：BuildingTypeModel baseline
交付要求：
- 建立：
  - `single_unit`
  - `multi_unit`
  - `commercial`
  baseline / compare / shadow
- 对 `assist_trial` 额外输出：
  - `eligible_count`
  - `applied_count`
  - `transition_counts`
  - `gold_match_rate`
  作为是否继续扩大 BuildingType assist 的运营证据

### 需求 17-2：Retrieval fusion policy
交付要求：
- 明确 retrieval 什么时候：
  - 只是提示
  - 是强 anchor
  - 必须被业务规则覆盖保护

### 需求 17-3：Commercial/incomplete ML support
交付要求：
- 把：
  - commercial prefix noise
  - incomplete vs recoverable incomplete
  纳入监督学习支持

## 4. 技术方法
- **Building-type structured classifier**
  - 基于 parser/reference/hint 特征建模。
- **Retrieval confidence gating**
  - 用向量分数与结构一致性共同决定 retrieval 影响力。
- **Residual review bucket learning**
  - 对商业和不完整地址残余桶做专门样本回流。

## 5. 预期收益
- 降低 building_type 边界回退
- 让 retrieval 从提示层升级为稳定融合输入
- 减少对商业前缀噪音的硬规则依赖

## 6. 交付物
- `BuildingTypeModel v1`
- retrieval fusion policy
- commercial/incomplete compare report

## 7. 完成标准
1. `BuildingTypeModel` 有 baseline / compare / shadow
2. retrieval 融合边界可解释、可审计
3. commercial/incomplete 不再只靠规则收口

## 8. 后续衔接
Phase 17 完成后，进入：
- `Phase 18: Rollout, Gate, Operations Completion`
