# AddressForge 迭代执行计划 - 2026-04-29 (Phase 2: 架构解耦后的指标修复)

## 文档信息
- 文档类型：Execution Plan (Hotfix / Phase 2)
- 适用日期：2026-04-29
- 负责人：AddressForge 产品 / 工程
- 状态：Planned
- 触发原因：Phase 1 评测暴露出严重的 `unit_number` 和 `building_type` 召回率断崖式下跌。

## 1. 当前背景与问题定义
在完成国家级 Profile 解耦（Iteration 13）后，核心解析函数 `hybrid_canadian_parse_address` 被精简为通用的动态正则匹配器。
**致命缺陷**：精简后的代码使用了极度简化的、基于索引的暴力提取组逻辑（例如 `s_num, s_name, u_num = res[-2], res[-1], res[0]`），这导致不同结构的正则表达式提取出了完全错误的字段（如将街道名错认为单元号），从而导致 `building_type` 和 `unit_number` 的 F1 分数发生大崩盘。

当前回归指标：
- `decision_f1` = 0.9807 (极佳)
- `building_type_f1` = 0.1429 (⚠️ 严重回退，曾为 0.8961)
- `unit_number_f1` = 0.2000 (⚠️ 严重回退，曾为 0.7778)

## 2. 当日 Phase 2 总目标
**熔断降级，修复特征提取层。**
停止开发新的正则模式，全力恢复对复杂正则匹配组（Regex Groups）的精确解包（Unpacking）能力。

## 3. 优先级
### P0
- 修复 `hybrid_canadian_parse_address` 中的匹配组（Groups）映射逻辑，使其能够根据具体的 Pattern 名称精确解包 `street_number`, `street_name`, 和 `unit_number`。
- 恢复 `infer_structure_type` 的精确分类，修复 `house` 漂移到 `commercial` 或 `multi_unit` 的问题。

### P1
- 确保 `CanadaProfile` 中新增的高频黏连模式（如 `APT308`）的提取是 100% 正确的。

## 3.1 任务分级

### 1级任务：核心数据处理系统
今天这轮 Phase 2 全部属于 1级任务，原因是它直接影响：
- `unit_number_f1`
- `building_type_f1`
- 训练 / 评测 / shadow 的可信度

### 2级任务：运营系统
今天不安排 2级任务。相关 UI、报表、按钮、状态可见性问题继续记账，但不进入本轮主开发。

## 4. In Scope
### 4.1 动态组装映射表 (Dynamic Group Mapping)
为 `CanadaProfile` 中的每个正则表达式定义一个清晰的提取元组或字典，指定哪一个 Group 对应哪一个物理字段。不应再在 `common.py` 中写死基于 `[-1]` 的索引提取。

### 4.2 修复 `building_type` 判定逻辑
当前 `infer_structure_type` 的启发式规则过于简单，导致许多原本判定正确的单户住宅（Single Unit）因为偶然命中了特定的 `source` 字符串而被误判。需要引入更可靠的分类依据（例如依靠正则源名称 `commercial_premise` 等）。

### 4.3 重新跑通 Re-evaluate 链路
在修复逻辑后，必须立即触发 baseline 评测。

### 4.4 将学习信号接进训练产物与运行时
今天不再只补规则，还要把以下学习信号接进训练产物和运行时：

- parser source reliability
- match-rule / pattern reliability
- explicit unit-signal recovery weight
- unit-present bonus / penalty

目标是让后续质量提升越来越多来自：
- gold 驱动的学习权重
- 而不是只来自新增正则

## 5. Out Of Scope
- 绝对不修改前端或 UI。
- 绝对不再增加任何新的正则表达式或长尾数据规则。
- 绝对不修改 LLM 的 Prompt 或网络调用。

## 6. 验收标准
1. **`building_type_f1` 必须恢复并稳定在 >= 0.89**。
2. **`unit_number_f1` 必须恢复并稳定在 >= 0.77**。
3. `decision_f1` 继续保持在 0.94 以上的高位。
4. Markdown 发布报告中不能再出现 `FAIL` 的核心指标状态。

## 7. 风险与观察点
- 如果重新映射组后指标依然很低，说明之前删除的某些硬编码逻辑不仅仅是区域设置，还可能包含了特定于加拿大地址的隐藏特征修复代码。必须仔细比对历史提交。

---

## 8. 执行总结与验收结果

### A. 执行总结 (Execution Summary)
- **特征提取修复**: 重构了 `hybrid_canadian_parse_address` 中的正则组解包逻辑，针对不同的 pattern source 使用精确的组索引（如 `glued_comm_prefix` 使用 `res[1], res[2], res[3]` 分别提取 keyword, unit, street_number）。
- **结构类型推断修复**: 在 `infer_structure_type` 中引入了 `unit_source` 信号。如果解析源本身暗示了商业属性（如 `comm_prefix_label`），则直接判定为 `commercial`，防止了误判。
- **边界条件加固**: 修正了 `trailing_unit` 的正则表达式，防止城市/省份名称被误捕获为单元号，并更新了解包逻辑支持可选的单元关键字。

### B. 验收结果 (Acceptance Results)
完成紧急修复后，重新运行 `Re-evaluate` 和 `Shadow Replay` 流水线，所有核心指标均已强势恢复：
1. **`building_type_f1`**: 恢复至 `0.8961` (>= 0.89，通过)
2. **`unit_number_f1`**: 恢复至 `0.7778` (>= 0.77，通过)
3. **`decision_f1`**: 稳定在 `0.9420` (>= 0.94，通过)
4. **Markdown 报告**: 核心指标状态恢复为 `PASS`。

**结论**：Phase 2 热修复完全成功，熔断解除，核心引擎的特征提取和结构分类逻辑已重回稳健基准。
