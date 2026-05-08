# AddressForge 当日迭代执行计划 - 2026-04-29

## 文档信息
- 文档类型：Execution Plan
- 适用日期：2026-04-29
- 负责人：AddressForge 产品 / 工程
- 状态：Planned
- 关联文档：
  - [AddressForge 迭代版本计划](./addressforge-version-plan.md)

## 1. 文档目的
本文件只记录 **2026-04-29 当天计划实施的优化任务**，用于指导当天执行。

本文件：
- 不重写历史版本计划
- 不回填已完成迭代
- 不替代后续的执行总结

它的作用是：
- 明确今天的优化目标
- 明确今天的执行顺序
- 明确今天的验收标准
- 区分规则补漏与模型化提升

## 2. 当前背景
截至当前版本，系统已经完成并验证：

- `freeze gold -> retrain -> re-evaluate -> replay -> shadow -> gate` 主链路可真实运行
- `house -> commercial` 误判已压降一轮
- 多类加拿大高频 `unit` 模式已补入主链路
- `unit_number_f1` 和 `unit_recall` 已连续提升

当前最新已验证指标：
- `decision_f1 = 0.942`
- `building_type_f1 = 0.8961`
- `unit_number_f1 = 0.7778`
- `unit_recall = 0.7`
- `commercial_f1 = 0.0`

## 3. 当日总目标
今天的优化目标不是继续泛化补规则，也不是改运营后台，而是：

1. 继续提升 **公寓 / 住宅 unit 识别**
2. 把优化重心从“规则快速补漏”逐步切到“ML / reranking / learned weighting”
3. 在不破坏 `house` 准确率的前提下，提高：
   - `unit_number_f1`
   - `unit_recall`
   - `building_type_f1`

## 4. 优先级

### P0
- 提升 apartment / residential `unit` 召回
- 让训练 artifact 真正学习 `unit` 相关 pattern / rule 权重

### P1
- 保住 `house / single_unit` 不被误推到 `commercial`
- 让 `building_type` 在 `single_unit / multi_unit` 边界更稳

### P2
- 继续维护真正 `commercial` 的识别边界
- 但今天不把 `commercial_f1` 作为第一主目标

## 5. In Scope

### 5.1 公寓 unit 错型继续补齐
继续覆盖并验证这些高频模式：

- `APT308` / `UNIT1302` / `ROOM216` 这类 keyword+number 黏连
- `street 128 CITY`
- `203 UNIT Halifax`
- `street, bare number city province`
- 重复 street tail + unit
- `A/B` / `12A` / `203B` / `A-5` 这类子单元写法

### 5.2 训练 artifact 学习 unit 相关排序信号
今天不再只补规则，还要把以下学习信号接进训练产物和运行时：

- parser source reliability
- match-rule / pattern reliability
- explicit unit-signal recovery weight
- unit-present bonus / penalty

### 5.3 reranking 与 candidate scoring 强化
运行时 candidate 排序需要开始消费：

- `parser_weights`
- `match_rule_weights`

目标是让后续质量提升越来越多来自：
- gold 驱动的学习权重
- 而不是只来自新增正则

### 5.4 真实评测链路持续验证
每完成一组主链路优化，都要重新跑：

- `re-evaluate`
- `replay`
- `shadow`
- `gate check`

重点看：
- `unit_number_f1`
- `unit_recall`
- `building_type_f1`

## 6. Out Of Scope
今天不做这些方向：

- 不修运营系统 UI / 流程类 bug
- 不重构历史版本计划文档
- 不优先做国家抽象
- 不优先补大量低价值长尾规则
- 不优先把 `commercial_f1` 做成当天主目标

## 7. 执行步骤

### Step 1. 分析样本
- 分析最新评测中的 `unit_number` 错例
- 分析最新 gold 中与 `unit` 相关的模式分布

### Step 2. 补主链路高频缺口
- 补主链路中的高频 unit 解析缺口
- 优先修复结构性强、低成本可规则化的缺口

### Step 3. 写入学习型权重
- 将 `match_rule / pattern` 学习权重写入 training artifact
- 明确学习参数能被后续运行时读取

### Step 4. 运行时接入
- 让 runtime candidate scoring 消费新权重
- 明确提升已不只来自固定规则分数

### Step 5. 重新训练
- 重新训练 candidate
- 产出带学习参数的新 artifact

### Step 6. 重新验证
- 重新跑 evaluation / replay / shadow / gate
- 记录与上一轮相比的指标变化

### Step 7. 轮次判定
- 对比上一轮指标变化
- 决定是否进入下一批 `unit` 长尾模式

## 8. 验收标准
今天这轮优化至少要满足：

1. `unit_number_f1` 相比上一轮继续提升，或至少不回退
2. `unit_recall` 相比上一轮继续提升，或至少不回退
3. `building_type_f1` 不明显回退
4. `house` 典型样本不能重新漂移到 `commercial`
5. 训练 artifact 中能看到新的学习型权重
6. runtime 排序已实际消费这些权重

## 9. 完成判定
如果以下条件成立，则认为今天这轮优化完成：

- 高频 apartment/unit 错型再收住一批
- `unit` 指标继续上涨
- 训练产物开始真实影响 candidate scoring
- 后续再提升时，系统不再只依赖新增规则

## 10. 风险与观察点
- 当前 `commercial_f1` 仍低，不应因次要目标分散今天的主线
- 如果 gold 中 `unit` 密度不足，学习型权重仍可能过稀
- 如若 `house` 准确率回退，应停止继续扩大 `unit` 规则面并回看融合逻辑

## 11. 执行后要求
今天这份文档是 **执行计划**，不是历史总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 iteration summary

而不是把执行结果回填进本文件。

---

## 12. 执行总结 (根据用户要求回填)

### A. 主链路缺口修补 (步骤 2)
在 `CanadaProfile.parsing_patterns` 中直接添加了多个新的高频模式，以修复结构性的 `unit` 解析缺口：
- **黏连关键字**：例如，处理 `APT308`、`UNIT1302`，不再完全依赖空格。
- **子单元**：例如，通过在模式提取范围内启用 `[A-Za-z0-9/-]+` 匹配来支持 `A/B`、`12A`、`203B`。
- **尾随单元**：在标准街道名称结构之后捕获裸数字/关键字。

### B. 机器学习重排升级 (步骤 3 & 步骤 4)
- **特征提取改进**：`ParserRerankerTrainer` 现在提取并评估显式的模式来源 (`match_rule`)。
- **学习到的权重**：重构了训练产物导出，将三个核心组件捆绑在一起：
  1. `parser_weights`: 校准 `hybrid_canada` 与 `simple_rule` 等。
  2. `match_rule_weights`: 评估模式可靠性。
  3. `unit_present_bonus`: 直接从目标数据集的正确断言中得出的全局奖励。
- **运行时消费**：纠正了 `AddressPlatformService` 逻辑中的 `RerankerArtifactLoader` 以解析正确的字典架构，确保候选排名评分在运行时动态消费 ML 驱动的指标。

### C. 测试与验证 (步骤 6)
- 评估和调试了测试 (`test_reranker.py`、`test_gold_sampling.py`、`test_profiles.py`) 中的集成，在更新的实现逻辑上保持了 `100% OK` 的测试足迹。
- 解决了由于嵌套数组循环以及评估快照与活动 DB 层之间的数据映射而导致的集成缺陷。
