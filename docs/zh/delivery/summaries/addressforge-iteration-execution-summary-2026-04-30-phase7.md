# AddressForge 迭代执行总结 - 2026-04-30 (Phase 7: Canonical Address Quality, Reference Fusion, And Assetization Convergence)

## 文档信息
- 文档类型：Execution Summary
- 对应计划：`addressforge-iteration-execution-plan-2026-04-30-phase7.md`
- 状态：Completed

## 1. 阶段目标回顾
Phase 7 的目标是：
- 建立 canonical/reference 质量诊断能力
- 建立 reference-backed 与 non-reference assetization 对比统计
- 让 asset promotion 的 coverage、gap、risk 可解释
- 为后续 reference-first / merge 优化建立可观测基础

## 2. 技术实现演进

### 需求 1：canonical/reference 质量诊断服务
本阶段实际采用的技术方法：
- 建立可提升资产池，只纳入 accepted + high-confidence 行参与 canonical 诊断
- 通过多来源结构字段提取减少单一解析结果缺字段造成的误判
- 引入 raw-text locality recovery 与 `city -> province` 保守补全
- 输出样本级 gap 证据，而不只输出 gap 数量

实际效果：
- `canonical_building_gap` 从早期三位数缺口压到 `0`
- `canonical_unit_gap` 压到 `0`
- locality 显性阻塞压到 `0`

### 需求 2：asset quality 报告
本阶段实际采用的技术方法：
- 建立独立 asset quality report
- 将 hotspot 从 building key 聚合扩展到 row-level 证据
- 报表逐步加入：
  - `reference_gap_reason_summary`
  - `reference_gap_hotspot_details`
  - `unit_convergence_quality_summary`
  - `residual_hotspot_risk_summary`

实际效果：
- 报表可稳定落盘到 `runtime/reports`
- canonical/reference 主线已有独立、可复查的阶段产物

### 需求 3：asset promotion 可解释性增强
本阶段实际采用的技术方法：
- promotion 过程可观测化，输出 reference-backed / non-reference / unique key 等统计
- promotion 前 row 级分类
- locality fallback 写入前补救
- reference fallback 融合
- authoritative canonical refresh
- canonical unit 规范化写入与历史脏变体合并

实际效果：
- canonical building 与 canonical unit 数量持续提升
- `reference_backed_building_ratio` 提升到稳定高位
- canonical unit 尾部脏值问题清零

### 需求 4：基于诊断的 reference-first / merge 优化
本阶段实际采用的技术方法：
- hotspot 风险分层
- reference gap 原因分解
- unit convergence 质量分层
- street suffix 归一化比较
- street 中嵌入 unit 尾巴剥离
- homogeneous single-unit repeat 降级

实际效果：
- actionable `reference_gap` 清零
- actionable `mixed_building_type_review` 清零
- actionable `unit_normalization_review` 清零

## 3. 预期收益与实际收益对照

### 任务 1：canonical/reference 质量诊断服务
- 预期收益：
  - canonical gap 从“数量差异”变成“可解释质量缺口”
- 实际收益：
  - canonical gap 已清零
  - locality / reference / unit gap 已可分层解释

### 任务 2：asset quality 报告
- 预期收益：
  - 形成可归档、可比较、可复查的资产质量产物
- 实际收益：
  - report 已稳定生成
  - 已包含 row-level hotspot 证据与 residual risk 摘要

### 任务 3：asset promotion observability enhancement
- 预期收益：
  - 资产沉淀过程可解释
- 实际收益：
  - promotion 已输出 reference-backed / non-reference / unique key 等统计
  - canonical building 与 unit 写入路径已可诊断

### 任务 4：canonical gap 原因分桶与样本级例子
- 预期收益：
  - “为什么没进 canonical”可直接转成下一轮修复任务
- 实际收益：
  - `reference_gap_summary` 已清零
  - `unit_summary` 中 actionable 尾部问题已清零

## 4. 当前最终结果
最新真实结果显示：
- `reference_gap_summary`
  - `no_reference_candidate_found = 0`
  - `reference_candidate_found_but_locality_mismatch = 0`
  - `reference_candidate_found_but_street_tail_mismatch = 0`
  - `reference_candidate_found_but_matcher_threshold = 0`
  - `reference_candidate_found_but_street_conflict = 0`
- `unit_summary`
  - `benign_multi_unit_convergence = 5`
  - `unit_normalization_review = 0`
  - `mixed_building_type_review = 0`
  - `commercial_unit_convergence = 0`
- `residual_hotspot_risk_summary`
  - `likely_multi_unit_convergence = 5`
  - `likely_reference_gap = 0`
  - `likely_merge_review = 0`

## 5. 结论
Phase 7 可以视为完成。

原因：
- canonical gap 已清零
- locality gap 已清零
- actionable reference gap 已清零
- actionable unit normalization tail 已清零
- actionable mixed building_type tail 已清零

当前剩余的 `5` 个 hotspot 更接近 benign multi-unit convergence，不再属于 canonical/reference 质量主线上的核心缺陷。

