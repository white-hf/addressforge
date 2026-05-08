# AddressForge 迭代执行计划 - 2026-04-29 (Phase 3: ML 地址解析优化需求)

## 文档信息
- 文档类型：Execution Plan / Optimization Requirements
- 适用日期：2026-04-29
- 负责人：AddressForge 产品 / 工程
- 状态：Planned
- 触发原因：后续地址解析成功率提升不能继续主要依赖新增规则，必须逐步切换到 gold 驱动的模型学习与运行时融合。

## 1. 当前背景与问题定义
当前系统已经通过多轮规则修正，显著改善了：
- `house -> commercial` 误判
- 高频 `unit` 召回
- `building_type` 的部分稳定性

但当前提升仍然主要来自：
- 新增规则
- fallback 逻辑
- heuristic 调整

这会带来三个问题：

1. 质量提升难以持续复用  
   每轮都需要继续补规则，系统难以从已有 gold 中自动学习。

2. 模型闭环虽然存在，但贡献还不够主导  
   训练、评测、replay、shadow、gate 已接通，但模型产物对实际解析成功率的贡献仍然偏弱。

3. 公寓 / 住宅 unit 识别仍是当前主要瓶颈  
   当前主战场不是商业地址，而是：
   - apartment / multi-unit
   - house with sub-unit
   - 后置裸数字 unit
   - 黏连 unit keyword

因此，本阶段的核心目标不是继续扩规则，而是：

**把 gold 驱动的学习信号接进训练产物与运行时，让后续质量提升越来越多来自模型学习，而不是新增正则。**

## 2. 当期总目标
本阶段优化目标是：

1. 提升地址解析成功率中与 `unit` 相关的关键指标
2. 让 parser reranking 和 candidate scoring 开始真实学习 gold 信号
3. 让训练 artifact 成为运行时排序和决策的重要输入
4. 让后续质量提升能够明确归因到模型学习，而不只是规则新增

## 3. 核心优化目标

### 3.1 Parser Reranking 学习化
系统不能继续主要依赖固定 parser 分数，必须基于 gold 学会：

- 哪个 parser 在哪类地址上更可靠
- 哪类 pattern / match_rule 更可信
- 哪类候选更可能包含正确的 `unit`

### 3.2 Unit Presence / Unit Recovery 学习化
系统必须把公寓 / 住宅 unit 识别，从“规则兜底为主”推进到“模型加权为主”。

重点场景包括：
- `APT308`
- `UNIT1302`
- `street 128 CITY`
- `203 UNIT Halifax`
- `A/B`
- `12A`
- `house with sub-unit`

### 3.3 Residential Boundary 稳定化
系统必须更稳定地区分：
- `single_unit`
- `multi_unit`

当前阶段的重点不是提升 `commercial_f1`，而是：
- 保住 `house`
- 提升 `apartment / multi_unit`
- 避免 unit 优化反向伤害 `building_type`

### 3.4 Gold 驱动闭环强化
后续质量提升必须越来越多来自：
- human gold
- active learning
- benchmark 错例

而不是继续依赖纯规则堆积。

### 3.5 训练产物到运行时的闭环
模型提升不能只停留在 artifact 文件里，必须真实进入：
- parse
- reranking
- candidate scoring
- replay
- shadow
- benchmark

## 4. 具体需求

### 需求 1：训练 artifact 必须学习 parser source reliability
训练过程必须从去重后的 gold 中学习不同 parser source 的可靠性，并将结果写入 artifact。

交付要求：
- artifact 中包含 `parser_weights`
- 权重来源于真实 gold 对比
- 不允许来自硬编码常量或伪标签

### 需求 2：训练 artifact 必须学习 match-rule / pattern reliability
训练过程必须识别：
- 哪些 pattern 更可靠
- 哪些 unit extraction 路径更可靠

交付要求：
- artifact 中包含 `match_rule_weights`
- 权重至少覆盖当前高频 unit 模式
- 训练逻辑必须能解释这些权重的来源

### 需求 3：训练 artifact 必须学习 unit 相关提示信号
训练过程必须将以下信号显式参数化：
- explicit unit-signal recovery weight
- unit-present bonus / penalty

交付要求：
- artifact 中能看到这些参数
- 参数不能停留在文件中，必须能被 runtime 读取

### 需求 4：runtime candidate scoring 必须消费学习型权重
运行时排序不能只看静态分数，必须消费训练 artifact 中的学习参数。

交付要求：
- `parse()` / candidate ranking 真实消费：
  - `parser_weights`
  - `match_rule_weights`
  - unit bonus / penalty
- 指定版本的 candidate model 能加载自己的 runtime 配置

### 需求 5：unit 相关收益必须能通过 benchmark 看见
优化结果必须直接体现在关键指标上，而不是只停留在局部 case 修正。

重点指标：
- `unit_number_f1`
- `unit_recall`
- `building_type_f1`
- `decision_f1`

### 需求 6：质量提升必须可归因
每轮优化之后，必须能区分：
- 哪些提升来自规则
- 哪些提升来自 artifact / learned weights / runtime scoring

不能再接受“看起来变好了，但无法解释主要提升来源”的情况。

## 4A. 技术实现演进说明

### 需求 1：训练 artifact 学习 parser source reliability
已采用的技术方法包括：
- **parser 可靠性统计学习**
  - 从去重后的 gold 中，按 parser source 统计正确率和相对贡献
  - 作用：把“固定 parser 偏好”转成可学习的 source reliability
- **训练产物参数化**
  - 将 parser 可靠性写入 artifact 中的 `parser_weights`
  - 作用：让 parser 偏好从代码常量迁移到可训练参数

当前代码载体：
- `learning/trainer.py`
- `api/server.py`

### 需求 2：训练 artifact 学习 match-rule / pattern reliability
已采用的技术方法包括：
- **pattern 命中可靠性学习**
  - 针对高频 unit 模式、match rule、recovery path 统计其与 gold 的一致性
  - 作用：让系统知道“哪类模式更可信”，而不是一律同权
- **pattern 权重运行时消费**
  - 将 `match_rule_weights` 接入 runtime candidate scoring
  - 作用：把 pattern 经验从离线训练真正带到 parse/ranking

当前代码载体：
- `learning/trainer.py`
- `api/server.py`

### 需求 3：训练 artifact 学习 unit 相关提示信号
已采用的技术方法包括：
- **显式 unit hint 参数化**
  - 将 explicit unit hint、residential unit hint、commercial hint 转成可学习参数
  - 作用：避免 unit 识别长期只能靠 if/else 规则兜底
- **unit bonus / penalty 建模**
  - 对“有 unit 提示但候选漏 unit”与“候选携带可信 unit”建立奖励/惩罚
  - 作用：让 unit 恢复质量直接影响候选排序

当前代码载体：
- `core/common.py`
- `learning/trainer.py`
- `api/server.py`

### 需求 4：runtime candidate scoring 消费学习型权重
已采用的技术方法包括：
- **artifact 驱动 runtime scoring**
  - parse/reranking 不再只看静态 base score，而是叠加 learned weights
  - 作用：让训练产物真正改变运行时排序
- **版本绑定 runtime 配置**
  - candidate model version 可加载自己的 artifact 配置
  - 作用：保证 benchmark / replay / shadow 能看到真实候选行为

当前代码载体：
- `api/server.py`
- `services/replay_service.py`
- `learning/shadow.py`

### 需求 5-6：收益可见且可归因
已采用的技术方法包括：
- **评测指标绑定 unit 主目标**
  - 持续用 `unit_number_f1`、`unit_recall`、`building_type_f1`、`decision_f1` 做主验收
  - 作用：避免只修局部 case 却不看整体收益
- **学习收益与规则收益区分**
  - 要求每轮说明是 learned weights 生效，还是规则/fallback 生效
  - 作用：防止“看起来变好，但不知道为什么”

当前代码载体：
- `learning/evaluator.py`
- `learning/trainer.py`

## 5. In Scope
本阶段在范围内的工作：

- parser source reliability 学习
- match-rule / pattern reliability 学习
- unit-related learning signals
- runtime scoring 融合
- candidate version 真实参与 benchmark / replay / shadow
- 以 `unit` 为核心的 gold-driven 提升

## 6. Out Of Scope
本阶段不作为主线的内容：

- 运营系统 UI / 页面体验
- Dashboard / Reports / Batch 的流程重构
- job 状态可见性修复
- 大量继续扩张低价值长尾规则
- 以 `commercial_f1` 为第一目标的优化

## 7. 验收标准

### 指标验收
本阶段至少应满足：

1. `unit_number_f1` 继续提升，或至少不回退
2. `unit_recall` 继续提升，或至少不回退
3. `building_type_f1` 不因 unit 优化明显回退
4. `decision_f1` 保持高位稳定

### 工程验收
本阶段还必须满足：

5. 训练 artifact 中明确出现新的学习型参数
6. runtime 明确消费这些参数
7. replay / shadow / benchmark 可绑定 candidate version
8. 新一轮提升不能只靠新增正则解释

## 8. 风险与观察点
- 如果 gold 中 `unit` 样本密度仍不足，学习型权重可能过稀
- 如果 runtime 只是加载参数但不显著改变排序结果，则“模型化提升”仍是表面接线
- 如果 unit 优化继续依赖规则而不是 learned weights，说明主线尚未真正转向 ML
- 如果 `house` 准确率回退，必须优先保住住宅基础盘

## 9. 完成判定
当以下条件成立时，可认为本阶段完成：

- unit 相关指标继续提升
- 训练 artifact 开始稳定影响 runtime scoring
- parser reranking 的收益可以从 gold 中学习出来
- 后续新一轮提升不再主要依赖新增规则

## 10. 执行后要求
本文件是优化需求与执行计划，不是执行总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 phase summary

不得把执行结果直接回填到本计划文档中。
