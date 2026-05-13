# AddressForge 迭代执行计划 - 2026-04-29 (Phase 5: Apartment Unit Hard-Sample Densification And Candidate Quality Lift)

## 文档信息
- 文档类型：Execution Plan / Optimization Requirements
- 适用日期：2026-04-29
- 负责人：AddressForge 产品 / 工程
- 状态：Completed
- 触发原因：Phase 4 已完成 candidate 级学习与 runtime 消费闭环，但 `unit_number_f1` 与 `unit_recall` 没有继续显著提升，说明当前瓶颈已从“学习能力未接通”转向“高价值 apartment/unit gold 密度不足、候选质量不够稳定”。

## 1. 当前背景与问题定义
Phase 4 已经完成：
- candidate 级训练样本构建
- candidate 特征学习
- candidate pairwise 胜负学习
- runtime 对 candidate 学习权重的真实消费

当前说明两件事：

1. **模型学习链路已接通**
   系统已经具备用 gold 驱动 candidate 级排序学习的能力。

2. **下一阶段瓶颈转向数据密度与候选质量**
   当前真实指标没有继续明显提升，核心原因更像是：
   - apartment / unit 高价值 gold 样本仍然不够密
   - 某些 hard cases 虽然已有候选，但候选之间仍不够“可分”
   - 候选质量提升速度慢于学习链路完善速度

因此，下一阶段的核心问题是：

**继续优先提升公寓 unit 解析成功率，但手段要从“继续接学习链路”切换为“扩大高价值 apartment/unit 样本密度 + 提升候选质量 + 用更聚焦的 hard cases 驱动训练”。**

## 2. 当期总目标
本阶段目标是：

1. 明显增加 apartment / unit hard cases 的高价值 gold 密度
2. 让训练样本更多集中在真正拉低 `unit_number_f1` 和 `unit_recall` 的错型上
3. 提升 parser candidate 的可分性和候选质量，而不是只增加学习权重
4. 继续优先提升：
   - `unit_number_f1`
   - `unit_recall`
   - `building_type_f1`

## 3. 核心优化目标

### 3.1 Apartment Unit Hard-Sample Densification
需要系统性补强以下高价值样本：
- 后置裸数字 unit
- 黏连 `APT/UNIT/ROOM/FLOOR`
- `A/B`、`12A`、`203B`
- house with sub-unit / secondary suite
- 无逗号、顺序错乱、城市省份尾巴粘连

### 3.2 Candidate Quality Improvement
模型排序已经能工作，但候选集本身仍需要继续提升质量：
- 候选应尽量给出“一个明显更好的 apartment/unit 解析”
- 避免多个候选都同样不完整或同样错误
- 继续提高 unit 提取前移到 parse 阶段的覆盖率

### 3.3 Hard-Case-Driven Training Loop
训练集不能再平均扩张，而要优先围绕：
- 最新 evaluation 错例
- replay / shadow 中与 current 不一致的样本
- LLM 与系统结论冲突的 apartment/unit 样本

## 4. 具体需求

### 需求 1：高价值 apartment/unit 样本必须定向扩张
下一轮人工审核样本应优先来自：
- `unit_number` 错例
- `multi_unit` 误判样本
- parser disagreement 且包含 unit 线索的样本
- LLM 与系统在 apartment/unit 上冲突的样本

交付要求：
- active learning 队列能单独输出 apartment/unit hard-sample 批次
- 队列生成时避免重复已审核样本

### 需求 2：候选质量必须继续提升
在 parse 阶段，系统应继续优先把 unit 恢复前移，而不是大量依赖 validate 兜底。

交付要求：
- parse candidate 更高比例直接携带正确 `unit_number`
- apartment/unit 候选之间应更容易被排序模型区分

### 需求 3：训练必须优先吃 hard cases
训练不应再主要从平均 gold 分布学习，而应提高 hard cases 的训练权重。

交付要求：
- 训练输入中能区分普通样本与 hard samples
- hard samples 可被单独统计与回放

### 需求 4：评测必须面向 apartment/unit 主目标
评测应明确回答：
- 哪些 apartment/unit 错型还在拉低指标
- 当前候选集是不是足够可分
- 本轮提升究竟来自：
  - 候选质量提高
  - 还是 hard-sample 密度提高

## 4A. 技术实现演进说明

### 需求 1：高价值 apartment/unit 样本定向扩张
已采用的技术方法包括：
- **错误桶驱动采样**
  - 优先从 `unit_number` 错例、`building_type` 错例、LLM/system 冲突样本里抽 hard samples
  - 作用：让人工审核集中在最能拉升 unit 指标的样本上
- **去重式 review batch 生成**
  - 生成队列时避开已审核样本和历史重复样本
  - 作用：提高 gold 扩张的有效密度，而不是重复劳动

当前代码载体：
- `learning/gold.py`
- `api/routes/review.py`

### 需求 2：候选质量继续提升
已采用的技术方法包括：
- **unit 恢复前移到 parse 阶段**
  - 优先在 parse candidate 内直接恢复 unit，而不是大量依赖 validate 兜底
  - 作用：让候选集本身更“可分”
- **面向 apartment/unit 的 pattern 修正**
  - 专注修正黏连 `APT/UNIT`、后置裸数字 unit、house sub-unit 等高价值错型
  - 作用：提高候选集中“明显更好候选”的出现概率

当前代码载体：
- `core/common.py`
- `api/server.py`

### 需求 3：训练优先吃 hard cases
已采用的技术方法包括：
- **hard-sample profile 显式化**
  - 在 training artifact 中输出 hard-sample 比例、unit-hint 样本数、multi-unit 样本数
  - 作用：让训练不再被平均 gold 分布掩盖
- **hard-case 来源可追踪**
  - 区分普通样本与 high-value apartment/unit hard samples
  - 作用：评估提升时能判断收益来自样本密度还是其他因素

当前代码载体：
- `learning/trainer.py`

### 需求 4：评测面向 apartment/unit 主目标
已采用的技术方法包括：
- **围绕 unit 主指标验收**
  - 持续用 `unit_number_f1`、`unit_recall`、`building_type_f1` 做阶段收益判断
- **收益来源拆解**
  - 每轮要求区分：
    - hard-sample 扩样收益
    - 候选质量提升收益
  - 作用：避免简单把所有提升都归因给训练

当前代码载体：
- `learning/evaluator.py`
- `learning/trainer.py`

## 5. In Scope
- apartment/unit 高价值样本扩张
- hard-sample 生成与批次管理
- parser candidate 质量继续提升
- hard-case-driven 训练输入强化
- 面向 apartment/unit 的评测与诊断

## 6. Out Of Scope
- 运营系统 UI 流程改造
- 报表中心问题修复
- commercial 作为主优化方向
- 国家抽象与多国家支持
- 大规模新功能平台化

## 7. 验收标准

### 指标验收
1. `unit_number_f1` 再次提升
2. `unit_recall` 再次提升
3. `building_type_f1` 不明显回退

### 数据与训练验收
4. 新增 gold 中 apartment/unit hard cases 占比明显提高
5. 训练输入中可明确识别 hard-sample 来源
6. 候选质量诊断能解释本轮 apartment/unit 主要剩余错型

## 8. 风险与观察点
- 如果人工审核继续以普通 house 为主，Phase 5 收益会被稀释
- 如果 parser candidate 质量提升不明显，新增 hard-sample 也可能只能带来有限增益
- 如果 candidate 已经足够好而 gold 仍不够密，瓶颈会继续停留在监督密度

## 9. 完成判定
当以下条件成立时，可认为本阶段完成：
- apartment/unit hard-sample gold 密度明显提高
- 训练输入明确偏向高价值 unit 错例
- parser candidate 质量或候选可分性继续提升
- `unit_number_f1` 与 `unit_recall` 再次上升

## 10. 执行后要求
本文件是优化需求与执行计划，不是执行总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 phase summary

执行结果不得直接回填到本计划文档中。
