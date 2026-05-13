# AddressForge 执行总结 - 2026-04-29 (Phase 6: Residential Unit Label Consistency And Semantic Disambiguation)

## 文档信息
- 文档类型：Execution Summary / Acceptance Result
- 适用日期：2026-04-29
- 关联计划：
  - `addressforge-iteration-execution-plan-2026-04-29-phase6.md`
- 状态：Completed

## 1. 总体结论
Phase 6 已完成。

本阶段完成了：
- relabel consistency 复审批次生成
- 训练前 label consistency 诊断
- `Upper/Lower/Apt/Unit` 的语义消歧
- semantic ambiguity 复审批次生成与样本源扩展
- 训练、runtime 与评测对标注污染的保护

本阶段的主要目标已经达成：
- 稳定 `single_unit` / `multi_unit` 的语义边界
- 避免 `Upper Lahave` 这类地名噪音被错误学习成 unit 结构
- 在不引入回退的前提下守住 `building_type_f1`、`unit_number_f1` 与 `unit_recall`

## 2. 已完成内容
### 2.1 Relabel Consistency 批次生成
系统现在可以生成专门的 `building_type` 复审批次，重点覆盖：
- 文本里有强 residential unit hint，但标成 `single_unit` 的样本
- 应重新确认为 `multi_unit` 的样本

同时，批次生成逻辑会避开已审核样本，避免重复派发。

### 2.2 训练前 Label Consistency 诊断
训练 artifact 中已新增：
- `label_consistency_diagnostics`

可显式量化：
- `single_unit` + strong unit hint
- `multi_unit` + missing unit evidence
- `commercial` + residential-like pattern

这意味着训练链路在真正学习前，已经具备一层标注一致性检查能力，而不是盲目吃所有 human gold。

### 2.3 Parse / Runtime / Training 语义消歧
解析、runtime scoring 和训练特征现在都可以区分：
- 真实 residential sub-unit 信号
- 仅作为地名一部分出现的 `Upper/Lower`

例如：
- `48 Rudolf Road, Upper Lahave, NS` 会保持为 `single_unit`
- `Upper 123 Main St, Halifax, NS` 仍然会保留为真实的 residential sub-unit 场景

### 2.4 Semantic Ambiguity 复审批次生成
系统现在已经具备专门的 semantic ambiguity review queue 生成能力，并且候选来源可覆盖：
- 当前 cleaning 结果
- 最新 evaluation 的 `building_type` 错例

最近几次真实运行里 `inserted = 0` 被视为正向结果，说明当前库里这类高价值语义歧义样本已经被历史审核和去重机制覆盖。

## 3. 验收结果
### 3.1 工程验收
已完成：
- relabel consistency 批次生成
- 训练 artifact 的 label consistency diagnostics
- parse/runtime/training 的语义消歧特征接线
- semantic ambiguity review batch generation
- semantic ambiguity 样本源扩展

### 3.2 Runtime / Training 验证
已确认：
- geographic `Upper/Lower` 地名噪音不再被误加成 residential unit 信号
- 真实 residential prefix-unit 仍然可恢复

训练侧也已确认：
- training artifact 真实包含 semantic disambiguation 特征
- label consistency diagnostics 已真实写入训练输出

### 3.3 指标结果
本阶段结束时验证的最新 candidate 指标：
- `decision_f1 = 0.9641`
- `building_type_f1 = 0.9072`
- `unit_number_f1 = 0.8108`
- `unit_recall = 0.75`
- `commercial_f1 = 0.0`

相对于上一轮 relabel 稳定后的 candidate：
- 没有引入新的回退
- semantic disambiguation 成功稳住了边界
- 本阶段更主要的收益来自“防污染”和“边界稳定化”，而不是再次大幅拉升 top-line 指标

## 4. 本阶段核心收获
### 4.1 有效方向
- 标注一致性和语义卫生已经进入主学习链路
- `Upper/Lower` 语义歧义可以在不伤真实 sub-unit 的前提下被管理
- 防止错误监督进入训练，与继续补 hard sample 同样重要

### 4.2 暴露出的下一阶段问题
- 当前 semantic ambiguity 的高价值 review/gold 池已经被消耗得差不多了
- 后续继续提升，已经不太可能再主要来自同一批歧义样本
- 下一阶段瓶颈上移为：
  - canonical address quality
  - reference-backed convergence
  - stable address assetization quality

## 5. 阶段结论
Phase 6 视为完成。

后续优化应进入新的独立 phase，重点转向：
- canonical address quality
- reference fusion confidence
- address assetization quality and convergence
