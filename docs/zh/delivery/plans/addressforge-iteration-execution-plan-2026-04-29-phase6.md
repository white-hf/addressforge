# AddressForge 迭代执行计划 - 2026-04-29 (Phase 6: Residential Unit Label Consistency And Semantic Disambiguation)

## 文档信息
- 文档类型：Execution Plan / Optimization Requirements
- 适用日期：2026-04-29
- 负责人：AddressForge 产品 / 工程
- 状态：Completed
- 触发原因：Phase 5 已经继续提升 `unit_number_f1` 与 `unit_recall`，并通过 relabel 恢复了 `building_type_f1`。当前下一阶段瓶颈已转向：human gold 标注口径不一致，以及 `Upper/Lower/Apt/Unit` 等文本信号的语义混杂。

## 1. 当前背景与问题定义
Phase 5 完成后，系统已实现：
- apartment/unit hard-sample 定向扩样
- hard-sample 驱动训练
- relabel 后的指标回升

当前状态说明两件事：

1. **高价值 apartment/unit 样本扩张是有效的**
   `unit_number_f1`、`unit_recall` 与 `building_type_f1` 都已被继续拉升或恢复。

2. **下一阶段主要问题不再是“样本不够”，而是“样本口径不稳”**
   当前 gold 中已出现：
   - 文本带明显 apartment/unit 线索，但标成 `single_unit`
   - `Upper/Lower` 既可能表示 unit，也可能只是地名的一部分
   - 模型与规则可能学到被标注口径污染的边界

因此，下一阶段核心问题是：

**稳定 `single_unit` / `multi_unit` 的标注语义边界，并对 residential sub-unit 与地名修饰词做更可靠的语义消歧。**

## 2. 当期总目标
本阶段目标是：

1. 建立面向 `building_type` 的标注一致性扫描与复审机制
2. 减少“明显带 unit 线索却被标成 `single_unit`”的 gold 污染
3. 区分真正的 residential sub-unit 信号与地名中的 `Upper/Lower`
4. 在不牺牲当前 `unit` 指标的前提下，继续稳住或提升：
   - `building_type_f1`
   - `unit_number_f1`
   - `unit_recall`

## 3. 核心优化目标

### 3.1 Label Consistency Governance
系统必须能主动识别并输出高风险标注不一致样本，例如：
- `single_unit` + 强 apartment/unit 文本信号
- `multi_unit` + 无任何 unit 证据
- `commercial` + 明显住宅模式

### 3.2 Semantic Disambiguation For Unit-Like Tokens
系统必须对以下模糊文本做更清晰区分：
- `Upper/Lower` 作为 unit
- `Upper/Lower` 作为地名组成部分
- `Apt/Unit/Suite/#` 作为真实 unit
- 与原始 street/city/province 尾巴混在一起的假 unit 片段

### 3.3 Training Guardrails Against Label Pollution
训练前必须具备对 gold 标注一致性的检查能力，避免明显错误口径直接进入学习链路。

## 4. 具体需求

### 需求 1：新增 gold 标注一致性复审批次
系统应能生成专门的 relabel review batch，用于重新审核疑似错标样本。

交付要求：
- 可单独生成 `building_type` relabel 队列
- 可排除已确认无问题的地名类 `Upper/Lower` 噪声样本
- 队列可批量预跑 LLM prescreen，供人工快速复审

### 需求 2：新增 label consistency 诊断输出
系统应在训练前或训练报告中输出 label consistency diagnostics。

交付要求：
- 能统计：
  - `single_unit` + strong unit hint
  - `multi_unit` + missing unit evidence
  - `commercial` + residential-like pattern
- 可输出样本列表用于人工复审

### 需求 3：增强 residential sub-unit 语义消歧
解析与特征层应增强：
- `Upper/Lower` 地名识别
- residential sub-unit 结构提示
- 真实 unit hint 与地名尾巴污染的分离

交付要求：
- 解析或 runtime 特征中能显式区分：
  - `unit-like token`
  - `geographic modifier token`
- 训练与运行时可消费该区分信号

### 需求 4：评测必须验证“口径稳定后的收益”
评测应明确回答：
- `building_type_f1` 是否因 relabel consistency 改善
- `unit_number_f1` / `unit_recall` 是否保持不回退
- 剩余错型里有多少来自标注问题而非解析问题

## 4A. 技术实现演进说明

### 需求 1：gold 标注一致性复审批次
已采用的技术方法包括：
- **疑似错标样本扫描**
  - 自动识别 `single_unit + 强 unit hint`、`building_type` 可疑样本
  - 作用：把 relabel 从人工偶发现象变成系统性治理
- **专用 relabel review batch**
  - 单独生成 `building_type` 复审队列，并排除已知地名噪音
  - 作用：让人工复审集中在真正会污染模型的样本上

当前代码载体：
- `learning/gold.py`
- `api/routes/review.py`

### 需求 2：label consistency 诊断输出
已采用的技术方法包括：
- **训练前一致性扫描**
  - 在训练前统计 `single_unit + strong unit hint`、`multi_unit + missing unit evidence` 等高风险口径问题
  - 作用：避免明显错误 gold 直接进入训练
- **样本级诊断回写 artifact**
  - 在 training artifact 中写入 `label_consistency_diagnostics`
  - 作用：让训练阶段就能看到当前 gold 污染程度

当前代码载体：
- `learning/trainer.py`
- `tests/test_training_diagnostics.py`

### 需求 3：residential sub-unit 语义消歧
已采用的技术方法包括：
- **地名修饰词 vs sub-unit 区分**
  - 区分 `Upper/Lower` 是地名组成部分，还是 residential sub-unit
  - 作用：避免把 `Upper Lahave` 误当 unit，同时保住 `Upper 123 Main St`
- **语义特征进入 parse/runtime/training**
  - 把 geographic modifier、unit-like token 等信号写入 feature vector 并接入 scoring/training
  - 作用：让语义边界不只靠规则，而能进入学习链路

当前代码载体：
- `core/common.py`
- `api/server.py`
- `learning/trainer.py`

### 需求 4：评测验证口径稳定收益
已采用的技术方法包括：
- **relabel 前后指标对照**
  - 用 `building_type_f1`、`unit_number_f1`、`unit_recall` 看口径修正后的收益
- **语义消歧稳定性验证**
  - 验证语义消歧后指标不回退，且地名噪音不再污染 training/runtime

当前代码载体：
- `learning/evaluator.py`
- `learning/shadow.py`

## 5. In Scope
- relabel review batch generation
- label consistency diagnostics
- `Upper/Lower/Apt/Unit` 语义消歧
- 训练前一致性检查
- building_type 与 unit 指标联动验证

## 6. Out Of Scope
- 运营系统 UI 改版
- release center / reports center 缺陷修复
- commercial 作为主优化方向
- 多国家支持
- 大规模 canonical 资产平台化

## 7. 验收标准

### 指标验收
1. `building_type_f1` 保持不回退，或继续提升
2. `unit_number_f1` 不回退
3. `unit_recall` 不回退

### 数据与训练验收
4. 系统能单独输出 relabel consistency 批次
5. 训练前可量化高风险 label inconsistency 样本数
6. 评测能解释剩余 `building_type` 错误中，哪些来自解析、哪些来自标注口径

## 8. 风险与观察点
- 如果 relabel 口径再次不一致，模型会继续被污染
- 如果 `Upper/Lower` 语义消歧做得太激进，可能误伤真实 sub-unit
- 如果只做数据治理、不继续改 runtime 特征，收益可能有限

## 9. 完成判定
当以下条件成立时，可认为本阶段完成：
- relabel consistency 批次生成能力稳定可用
- 训练前一致性检查可量化输出高风险样本
- `building_type_f1` 稳住或继续提升
- `unit` 指标不因语义消歧而回退

## 10. 执行后要求
本文件是优化需求与执行计划，不是执行总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 phase summary

执行结果不得直接回填到本计划文档中。
