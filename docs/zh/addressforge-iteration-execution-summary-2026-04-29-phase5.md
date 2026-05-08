# AddressForge 执行总结 - 2026-04-29 (Phase 5: Apartment Unit Hard-Sample Densification And Candidate Quality Lift)

## 文档信息
- 文档类型：Execution Summary / Acceptance Result
- 适用日期：2026-04-29
- 关联计划：
  - `addressforge-iteration-execution-plan-2026-04-29-phase5.md`
- 状态：Completed

## 1. 总体结论
Phase 5 已完成。

本阶段完成了：
- apartment/unit hard-sample 定向扩样
- hard-sample 训练输入画像
- 复审后 relabel 样本重新进入 gold
- 基于新 gold 的 retrain / evaluation / shadow / gate 验证

本阶段的主要目标已经达成：
- `unit_number_f1` 再次提升
- `unit_recall` 再次提升
- `building_type_f1` 在 relabel 后恢复并超过 active baseline

## 2. 已完成内容
### 2.1 Hard-Sample 批次生成
已新增 apartment/unit hard-sample 定向抽样能力，包括：
- 最新 evaluation 的 `unit_number_errors`
- 带 unit hint 的 `building_type_errors`
- LLM prescreen 与系统在 apartment/unit 上冲突的样本
- 当前清洗结果里带 unit hint 但结构不稳的样本

### 2.2 训练输入 Hard-Sample 画像
训练 artifact 中已新增：
- `hard_sample_profile`

可显式统计：
- `total_gold`
- `hard_sample_gold`
- `hard_sample_ratio`
- `unit_hint_gold`
- `multi_unit_gold`
- `hard_task_type_gold`

### 2.3 Relabel 复审闭环
已发现并修复一批“文本含明显 apartment/unit 线索，但 human gold 标成 `single_unit`”的样本。

该修复直接用于：
- 重新 freeze gold
- 重新训练 candidate
- 重新评测 building type 与 unit 指标

## 3. 验收结果
### 3.1 指标结果
最终 candidate 版本：
- `canada_candidate / v_phase5_after_relabel_20260429`

最终关键指标：
- `decision_f1 = 0.9641`
- `building_type_f1 = 0.9072`
- `unit_number_f1 = 0.8108`
- `unit_recall = 0.75`
- `commercial_f1 = 0.0`

相对于 active baseline：
- `decision_f1`: `0.942 -> 0.9641`
- `building_type_f1`: `0.8961 -> 0.9072`
- `unit_number_f1`: `0.7778 -> 0.8108`
- `unit_recall`: `0.70 -> 0.75`

### 3.2 Shadow 结果
- `score_delta = 0.0232`
- `candidate_match_rate = 0.568`
- `active_match_rate = 0.568`
- `disagreement_rate = 0.0`
- `promote_recommended = true`

### 3.3 Gate 检查结果
当前核心 gate checks 已全部通过：
- `decision_f1`: passed
- `building_type_f1`: passed
- `unit_number_f1`: passed
- `unit_recall`: passed
- `commercial_f1`: passed
- `review_rate`: passed
- `reject_rate`: passed

说明：
- 发布判断顶层 `ready` 字段仍可能受汇总/刷新逻辑影响
- 但就当前真实评测与 shadow 指标而言，本阶段 candidate 已达到可 promote 候选状态

## 4. 本阶段核心收获
### 4.1 有效方向
- apartment/unit hard-sample 密度提升能继续拉升 `unit_number_f1` 与 `unit_recall`
- human gold relabel 对 `building_type_f1` 恢复作用明显

### 4.2 暴露出的下一阶段问题
- 当前模型已经对 apartment/unit 更敏感，但 gold 标注口径不一致会直接污染 `building_type`
- `Upper/Lower` 等文本既可能是 unit 线索，也可能是地名组成部分
- 下一阶段不能只继续加 hard samples，必须加强：
  - 标注一致性控制
  - residential sub-unit 与地名修饰词语义消歧

## 5. 阶段结论
Phase 5 视为完成。

后续优化应进入新的独立 phase，重点不再是单纯扩充 hard-sample，而是：
- 标注一致性治理
- `single_unit` / `multi_unit` 口径稳定化
- `Upper/Lower/Apt/Unit` 语义消歧
