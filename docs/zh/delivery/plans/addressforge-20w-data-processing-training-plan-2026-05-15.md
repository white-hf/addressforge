# AddressForge 20w 数据处理与训练作业计划 - 2026-05-15

## 文档信息
- 文档类型：Data Processing & Training Execution Plan
- 适用日期：2026-05-15
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：在不新增功能的前提下，把系统已有的 20w 地址数据治理成可训练、可验证、可回流、可上线的可靠数据资产

## 1. 当前背景
系统已经具备以下基础能力：
- `dirty address diagnostics`
- `review opportunity leaderboard`
- `preview / reclean / evidence`
- `residual bucket` 识别与重新播种
- `DecisionModel` / `Reranker` / `BuildingTypeModel` runtime identity
- `shadow -> assist -> guarded override -> promote / rollback`

但如果把 20w 数据直接一把喂给训练流程，仍会遇到：
- `review` 样本过保守
- 历史 backlog 污染训练分布
- 残余样本没有回流 gold
- 训练、评估、回放口径不完全一致

所以当前重点不是新增功能，而是：
1. 消化已有 backlog
2. 回流真正有证据的边界样本
3. 用冻结集和 shadow/replay 验证模型可靠性
4. 逐轮收紧 gate 直到可以稳定上线

## 2. 总目标
1. 将 20w 原始数据分层治理为可训练的数据资产
2. 将可自动处理的 review backlog 消化掉
3. 将顽固 residual bucket 回流为新的 gold 和 calibration 样本
4. 用真实 holdout、shadow、replay、gate 建立可靠模型判定机制
5. 在不引入新功能的情况下，完成训练闭环和生产收口

## 3. 约束原则
1. 不再新增产品能力或控制台功能
2. 所有动作必须围绕已有闭环展开
3. 训练前必须先做数据分层与去重
4. 回流样本必须可追溯
5. 每轮训练必须和上一轮 baseline 对比
6. 任何指标提升都必须同时检查回归风险

## 4. 数据分层策略
20w 数据按以下层次管理：

### 4.1 Raw
- 原始导入数据
- 用作全量源头，不直接作为主训练集

### 4.2 Clean
- 当前 runtime 能稳定自动处理的数据
- 作为线上运行的主要覆盖层

### 4.3 Review
- 当前仍需人工判断的数据
- 只作为 active learning、calibration、残余分析输入

### 4.4 Gold
- 已经人工确认且经过去重的高质量监督数据
- 作为主训练集和评估集核心来源

### 4.5 Residual
- 经过最新 runtime 仍无法自动消化的顽固样本
- 作为下一轮人工审核和再训练的边界样本源

## 5. 作业节奏
建议按 6 个连续阶段循环推进。每一阶段都可以按批次或按周执行，但顺序不要打乱。

### 阶段 1：基线冻结与数据审计
目标：
- 固定当前 active baseline
- 明确 20w 数据的真实构成
- 找出 review / accept / enrich / reject / residual 的初始分布

作业：
- 统计当前 20w 数据分布
- 冻结 holdout 集
- 输出当前 baseline 指标：
  - `decision_f1`
  - `building_type_f1`
  - `unit_number_f1`
  - `review_rate`
  - `disagreement_rate`
- 确认 current runtime identity

完成标准：
- 有一份冻结的 baseline 报告
- 有一份不可训练 holdout
- 后续训练不再污染这份 baseline

### 阶段 2：按批次消化 review backlog
目标：
- 优先处理 review 压力最大的来源和批次
- 让可以自动恢复的样本先回到 `accept` 或 `enrich`

作业：
- 用 `Review Opportunity Leaderboard` 排序批次
- 对 top batch 执行：
  - `Preview Reclean`
  - `Reclean Reviews`
  - `Load Evidence`
  - `Load Residual Buckets`
- 按 `source_name / batch_id` 追踪恢复收益

完成标准：
- review backlog 明显下降
- 每个批次的恢复收益可解释
- 残余原因可以按桶定位

### 阶段 3：Residual bucket 回流 gold
目标：
- 将顽固 residual 样本变成新 gold 和新 active learning 样本

作业：
- 从 residual bucket 中挑选最有价值的边界样本
- 按 residual reason / building type / disagreement kind 采样
- 去重后播种到 active learning queue
- 由人工审核后回写 gold

完成标准：
- residual bucket 成功回流为新的 gold
- 新 gold 具备去重保证
- 训练集边界样本质量提升

### 阶段 4：重训 DecisionModel / Reranker / BuildingType
目标：
- 用新的 gold 和 residual 回流样本重训现有模型
- 不改变架构，只更新权重和阈值

作业：
- 重训 DecisionModel
- 重训 Reranker
- 重训 BuildingTypeModel
- 输出训练产物与 runtime identity
- 记录 decision policy calibration

完成标准：
- 新模型产物可落盘
- runtime identity 与评测对齐
- 训练元数据可审计

### 阶段 5：Shadow / Replay / Gate 验证
目标：
- 确认新模型真的优于 baseline
- 确认没有破坏 house / apartment / commercial 边界

作业：
- 跑 shadow compare
- 跑 replay compare
- 检查 release readiness
- 检查 assist trial advantage
- 检查 reranker impact direction

完成标准：
- 关键指标不回退
- shadow advantage 为正
- gate 通过或明确指出 blocker

### 阶段 6：生产回放与滚动收口
目标：
- 只在证据充分时推进 promote
- 不满足 gate 时保留 rollback

作业：
- 通过 promote gate 的模型才允许 promote
- 通过 `/reload` 更新运行时
- 必要时执行 `/rollback`
- 对新的 review backlog 再进入下一轮

完成标准：
- 模型升级可回滚
- 生产状态可审计
- 下一轮 backlog 有新的输入

## 6. 每轮必须输出的证据
每轮作业结束后，至少输出以下内容：
- 当前处理批次
- 处理前后 review / accept / enrich / reject 变化
- residual bucket 主桶变化
- gold 增量
- 训练产物路径
- runtime identity
- shadow/replay/gate 结论

## 7. 推荐执行顺序
1. 基线冻结与数据审计
2. review backlog 按批次消化
3. residual bucket 回流 gold
4. 重训现有模型
5. shadow / replay / gate 验证
6. promote / reload / rollback 收口

## 8. 完成标准
当以下条件同时成立时，可以认为 20w 数据训练闭环达成：
1. 大部分可自动处理样本已从 review 中移出
2. residual bucket 已形成稳定回流机制
3. 冻结 holdout 上的指标稳定优于旧 baseline
4. shadow / replay / gate 不再暴露系统性回退
5. runtime identity 贯穿训练、评估、回放和上线
6. 生产上可安全 promote、reload、rollback

