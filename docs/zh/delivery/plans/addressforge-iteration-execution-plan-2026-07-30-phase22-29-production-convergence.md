# AddressForge 迭代执行计划 - 2026-07-30

## Phase 22-29：生产可信度、模型质量与资产闭环收口

## 文档信息

- 文档类型：Iteration Execution Plan / Delivery Plan
- 状态：Proposed
- 计划依据：2026-07-30 生产库只读审计、现有产品目标、下一代 ML 系统设计、Phase 19-24 计划
- 计划性质：
  - 重新验收 Phase 22-24 的未闭环目标
  - 在可信基线建立后开启 Phase 25-29
- 总目标：让系统从“能够运行和产生高分报告”收敛为“指标可信、运行时一致、质量达标、资产持续生长、可以安全发布和回滚”的生产系统

## 1. 为什么需要这份收口计划

现有架构方向仍然成立：

- Parser / Normalization 负责结构恢复
- Reference / Canonical 负责事实与标准实体
- DecisionModel / Reranker / BuildingTypeModel 负责监督学习
- Policy / Safety Guard 控制模型影响范围
- Human Review / Gold / Freeze / Evaluation / Shadow / Gate 形成学习闭环

当前主要问题不是缺少新的架构能力，而是现有闭环的生产事实没有完全一致。

因此，本计划不重新设计系统主链，也不直接进入新一轮模型调参，而是先恢复：

1. 运行时身份可信
2. Gold 与评估可信
3. 发布门槛可信
4. Active/Candidate 比较可信

之后再推进模型质量、Reference/Canonical 和长期 Shadow。

## 2. 2026-07-30 生产证据基线

### 2.1 数据与运营状态

- `raw_address_record = 270,874`
- `address_cleaning_result = 270,874`
- 清洗覆盖率为 100%
- 当前决策分布：
  - `accept = 268,438`
  - `enrich = 2,034`
  - `reject = 384`
  - `review = 16`
  - `pending = 2`
- Human Gold 总量：`1,789`
- Active Learning Queue：
  - 总量：`3,215`
  - `queued = 1,402`
  - 其中：
    - `building_type = 878`
    - `review = 449`
    - `unit_number = 75`

这说明系统已经具备大规模清洗和人工回流能力，但“清洗结果仅剩 16 条 review”和“队列仍有 1,402 条 queued”之间存在运营状态差异，需要正式解释和治理。

### 2.2 模型注册与运行时状态

- 最新创建的注册模型：
  - ID 50
  - `v20260517_week4`
  - `decision_f1 = 0.2991`
  - 未晋升
- 最新评估对象：
  - ID 43
  - `v1`
  - 2026-06-20 更新
  - `promote_recommended = false`
- Workspace 默认模型：
  - `default_model_id = 1`
  - 但 registry 状态为 `evaluated`
  - `is_default = 0`
- 文档中提到的 ID 51、52 在当前生产 registry 中不存在

当前存在以下版本绑定风险：

- 活动模型登记的版本化 `.pkl/.json` 物理文件缺失
- 活动运行时降级使用通用 `.cbm`
- 最新候选评估使用的是旧 `.pkl` sidecar
- Decision、Reranker、BuildingType 来自不同生成时间
- 同一个 model version 不能唯一解析到一个不可变 runtime bundle

### 2.3 最新可验证评估指标

以 ID 43 最新评估对比旧基线：

| 指标 | 旧基线 | 最新评估 | 文档目标 | 当前判断 |
|---|---:|---:|---:|---|
| `decision_f1` | 0.7214 | 0.9416 | ≥0.95 或显著提升 | 相对提升，绝对值略低 |
| `building_type_f1` | 0.8441 | 0.8700 | ≥0.97 | 未达成 |
| `unit_number_f1` | 0.8311 | 0.8392 | 持续提升且不回退 | 小幅提升 |
| `unit_recall` | 0.7505 | 0.7628 | ≥0.70 | 达成 |
| `unit_precision` | 0.9312 | 0.9325 | ≥0.98 | 未达成 |
| `commercial_f1` | 0.1966 | 0.3010 | 稳定提升 | 仍较弱 |
| `review_rate` | 0.0014 | 0.0001 | 下降且质量不回退 | 数值下降，需检查 false accept |
| Replay disagreement | - | 0.0088 | ≤0.05 | 数值达成 |
| Assist Gold Match | - | 0.7722 | ≥0.90 | 未达成 |

补充事实：

- ML Shadow Decision F1 为 `0.9640`
- Assist Trial F1 为 `0.9419`
- Assist Trial 相对启发式收益仅 `+0.0003`
- 状态为 `needs_more_assist_calibration`
- BuildingType ML Shadow 指标当前无效，需要修复评估口径

这些数值将作为“待重新冻结的审计基线”，不能直接作为正式发布基线，因为运行时身份尚未完全一致。

### 2.4 错误桶与数据质量

最新保存错误样本的主要分布：

- Decision：
  - `UNDETECTED_CONFLICT = 47`
  - `OVER_SENSITIVE_REVIEW = 38`
  - `GENERAL_MISMATCH = 15`
- Building Type：
  - `WRONG_BUILDING_TYPE = 54`
  - `MULTI_UNIT_UNDER_COUNT = 23`
  - `COMMERCIAL_IDENTIFICATION_FAILURE = 23`
- Unit：
  - `REFERENCE_MISSING_UNIT = 72`
  - `UNIT_PARSING_CONFLICT = 25`
  - `UNIT_PATTERN_MISS = 3`

已确认 Gold 中存在疑似错误标签，例如：

- locality tail 被写入 unit
- street tail 被写入 unit
- unit/civic 顺序颠倒

这些样本必须经过人工复核，不能由 Agent 或 LLM 直接更改为 Human Gold。

### 2.5 Reference 与 Canonical 状态

- External Reference：`461,649`
- 当前来源只有 GeoNova
- 实际带 Reference 结果的清洗记录：`15,911`
- Reference 覆盖约为 `5.87%`
- 新 Canonical 表：
  - building：`5,583`
  - unit：`1,335`
- Canonical 最后更新时间早于最新原始数据
- 旧发布资产中仍有大量 `REVIEW` 等级记录

说明后续 unit 和 building 质量瓶颈已经不只是 Parser 问题，还包含 Reference 覆盖和 Canonical 持续生产问题。

## 3. 计划原则

### 3.1 测量不可信时禁止调优

Phase 22-24 重新验收完成前：

- 不宣称模型质量提升
- 不晋升新模型
- 不大规模重清洗生产 backlog
- 不根据不一致指标调节生产阈值

### 3.2 先恢复事实，再优化指标

必须先保证：

- Active model 唯一
- Candidate model 唯一
- 物理产物完整
- 评估加载的产物就是待发布产物
- Replay/Shadow 使用独立 runtime

### 3.3 Human Gold 保持权威

- LLM 只做 prescreen、建议、分组和优先级
- 疑似错误 Gold 只能进入 `pending_human_review`
- 未经人工确认的标签不得参与正式发布评测

### 3.4 保护系统主目标

后续优化必须同时保护：

- House precision
- Apartment unit quality
- Building type stability
- Decision safety
- Commercial boundary
- Review 人力成本

### 3.5 Parser/Reference/Canonical 主骨架不被跳过

本计划不允许直接用黑盒模型替换结构主链。

模型继续按以下路径演进：

```text
Shadow
  → Assist
  → Guarded Override
  → Partial Rollout
  → Default On
```

## 4. 总体执行路线

```text
Phase 22R 运行时合同重新验收
  → Phase 23R Registry / Gate / Reload / Rollback 重新验收
  → Phase 24R 可观测性与证据持久化收口
  → Phase 25 Gold 与评估可信度
  → Phase 26 Decision 安全与 Assist 校准
  → Phase 27 House / Apartment / Commercial 质量收敛
  → Phase 28 Reference / Canonical / Retrieval 收敛
  → Phase 29 长期 Shadow、受控发布与最终验收
```

`R` 表示重新验收现有阶段，而不是重新设计同一能力。

## 5. Phase 22R：Manifest-bound Runtime Contract 重新验收

### 5.1 目标

确保一个 model version 唯一对应一个不可变 runtime bundle，并被 Training、Evaluator、Replay、Shadow、API、Worker 一致消费。

### 5.2 需求

1. 统一 Decision、Reranker、BuildingType 的版本化 manifest
2. manifest 包含：
   - 物理文件路径
   - metadata/sidecar
   - feature schema version
   - parser/rule/reference version
   - decision policy
   - 文件 SHA256
3. 禁止正式评估依赖可变通用文件名
4. 禁止静默 fallback
5. Active 和 Candidate 必须创建独立 runtime 实例
6. 所有运行路径输出完整 runtime identity

### 5.3 技术方法

- 不可变版本目录
- manifest schema validation
- physical artifact completeness check
- runtime bundle factory
- explicit fallback status
- artifact hash verification

### 5.4 交付物

- Runtime bundle contract
- Manifest schema
- 版本绑定测试
- Active/Candidate 独立加载测试
- Runtime identity 报告

### 5.5 完成标准

- Registry、workspace、runtime endpoint、evaluation artifact 指向同一个 model ID/version/hash
- Decision/Reranker/BuildingType 均可追溯到物理文件
- 缺失 sidecar 时评估和晋升均失败
- fallback 被明确记录且不能通过正式 Gate
- 当前生产行为在此阶段不被改变

## 6. Phase 23R：Registry、Release Gate、Reload、Rollback 重新验收

### 6.1 目标

建立活动模型的单一事实来源，确保 promote、reload、rollback 操作一致且可审计。

### 6.2 需求

1. 统一：
   - `workspace_registry.default_model_id`
   - `model_registry.is_default`
   - `model_registry.status`
2. Evaluation 不得覆盖活动模型的发布状态
3. Reload 不得通过 bootstrap 隐式重新选择模型
4. Rollback 必须回到明确的不可变版本
5. Gate 阈值与正式文档一致
6. 缺失指标、产物、Replay 或 Shadow 证据时必须阻塞
7. Promote 前生成 dry-run readiness report

### 6.3 技术方法

- transactional activation
- compare-and-swap/default-version guard
- registry cache invalidation
- preflight validation
- immutable rollback target
- fail-closed release gate

### 6.4 完成标准

- 任意时刻只有一个活动版本
- Promote 后 runtime identity 与 registry 立即一致
- Reload 不改变活动版本选择
- Rollback 后 registry、内存态和实际输出一致
- Gate 失败原因结构化输出
- 完成一次不影响生产的 promote/reload/rollback 演练

## 7. Phase 24R：可观测性与评估证据持久化

### 7.1 目标

让所有质量结论都能回到真实运行记录和代表性样本。

### 7.2 需求

1. Historical Replay 持久化逐条 Active/Candidate 差异
2. 保存：
   - raw ID
   - runtime identity
   - active output
   - candidate output
   - current production output
   - failure/error
3. 区分：
   - disagreement rate
   - regression risk
   - candidate win rate
4. Dashboard/Report 读取同一事实源
5. Active Learning Queue 与当前清洗状态建立可解释关系
6. 清理或标记 stale queue items，不直接删除未经确认的数据

### 7.3 完成标准

- 最新 Replay 可以查询全部 mismatch 样本
- Replay 失败不会被记录为成功
- Candidate win rate 必须来自人工确认或正式 Gold
- 控制台数据与 SQL 查询一致
- “当前 review”和“queued review task”语义明确区分

## 8. Phase 25：Gold 与 Evaluator 可信度

### 8.1 目标

建立可用于训练和发布判断的可信监督数据与冻结基线。

### 8.2 需求

1. 人工复核已发现的疑似错误 Gold
2. Gold 按 `(source_id, task_type)` 保持任务语义
3. 增加字段级标签校验：
   - locality/street tail 不得作为 unit
   - 无效 decision/building type 被阻塞
4. 修复 BuildingType ML 评估口径
5. 检查同址、同楼和跨 split 泄漏
6. 建立双池：
   - correction pool
   - calibration/fresh production pool
7. 冻结新的不可训练 holdout

### 8.3 人工门槛

Agent 可以：

- 导出疑似标签
- 分桶
- 给出修改建议
- 生成审核批次

只有人工可以：

- 接受或拒绝标签修改
- 将标签标记为 Human Gold
- 批准新的正式 holdout

### 8.4 完成标准

- 所有疑似错误标签完成人工处理
- 任务级重复、冲突和泄漏报告可用
- BuildingType ML 指标不再是空评估
- 新 Frozen Gold 记录数据版本、split、数量和分布
- Active 与 Candidate 在同一冻结集上重新评测
- 形成正式可信基线报告

## 9. Phase 26：Decision Safety 与 Assist 校准

### 9.1 目标

利用可信基线提升 DecisionModel，同时控制 aggressive accept 和 false reject。

### 9.2 主要错误桶

- `UNDETECTED_CONFLICT`
- `OVER_SENSITIVE_REVIEW`
- `GENERAL_MISMATCH`
- Reject minority
- Parser disagreement
- City/locality mismatch

### 9.3 技术方法

- transition-specific assist policy
- correction/calibration 双池采样
- minority-label weighting
- candidate-level conflict features
- accept/reject 独立安全守卫
- threshold proposal → offline compare → shadow-only consumption

### 9.4 保护指标

- Building Type 不回退
- Unit Precision 不回退
- House precision 不回退
- Reject precision 可解释
- Review Rate 下降不能来自错误 accept

### 9.5 完成标准

- `decision_f1 ≥ 0.95`，或在可信冻结集上达到约定显著增益
- Assist Gold Match ≥0.90
- Assist Trial 明显优于 heuristic，而不是仅 `+0.0003`
- aggressive accept 错误桶不增加
- Reject precision/recall 被正式输出
- 未达到门槛时保持 Shadow-only

## 10. Phase 27：House、Apartment、Commercial 质量收敛

### 10.1 目标

提升 apartment unit 质量，同时保护 house 和 commercial 边界。

### 10.2 主要错误桶

- double-number single-unit false unit
- prefix-unit / civic reversal
- glued unit/civic token
- multi-unit under-count
- commercial misclassification
- bare-number unit recovery

### 10.3 技术方法

- unit/civic candidate pair construction
- candidate-level negative features
- exact numeric alignment
- learned reranking
- BuildingType supervised classification
- commercial entity and suite/floor joint features
- parser/reference evidence fusion

### 10.4 完成标准

- `building_type_f1 ≥ 0.97`
- `unit_precision ≥ 0.98`
- `unit_recall` 不低于可信基线并持续提升
- `unit_number_f1` 明显优于可信基线
- commercial 指标不回退并有明确提升
- house representative set 不出现系统性回退
- 收益主要来自学习、候选和数据质量，而不是继续扩张零散 regex

## 11. Phase 28：Reference、Canonical 与 Retrieval 收敛

### 11.1 目标

把已经转移到 Reference/Canonical 的错误瓶颈提升到资产层解决。

### 11.2 需求

1. 恢复 Canonical building/unit 增量生产
2. 对齐最新 raw/clean 数据与 canonical 更新时间
3. 建立多来源 reference fusion
4. 评估并减少 duplicate canonical entity
5. 从高可信历史事实中挖掘 unit，但保持人工/证据门槛
6. 建立 lexical/exact numeric/spatial/vector 混合召回
7. 输出正式 retrieval/reranker 指标

### 11.3 技术方法

- canonical convergence audit
- reference-backed field refresh
- entity resolution
- exact numeric guard
- hybrid candidate retrieval
- pairwise reranking
- unit mining with provenance

### 11.4 完成标准

- Canonical 增量任务持续处理新数据
- Reference coverage 相对可信基线有明确提升
- Candidate Recall@10 ≥0.995
- Reranker MRR ≥0.98
- duplicate entity fusion accuracy ≥0.99
- 所有 mined unit 保留来源和置信证据
- Reference/Canonical 收益能体现在 unit、review 或 enrichment 指标上

## 12. Phase 29：长期 Shadow、受控发布与最终验收

### 12.1 目标

用新鲜生产流量证明候选系统在真实环境中更安全、更准确且可回滚。

### 12.2 执行步骤

1. Offline Frozen Gold Gate
2. 大规模 Historical Replay
3. 连续 7-14 天 Online Shadow
4. Disagreement 人工抽样确认
5. Guarded Assist
6. Partial Rollout
7. Default On 或 Keep Active

### 12.3 核心指标

- Candidate disagreement win rate ≥0.90
- Shadow 期间 0 未处理崩溃
- 单条延迟增量 ≤10ms
- 关键质量指标不回退
- Review/Reject 分布无异常漂移
- Rollback 执行时间和结果满足操作标准

### 12.4 人工门槛

- Disagreement 胜负必须由 Human Gold 或正式人工审计支持
- 自动晋升在长期 Shadow 闭环完成前保持关闭
- Partial Rollout 扩大比例需要明确批准

### 12.5 完成标准

- Offline、Replay、Shadow 使用完全相同的候选 manifest
- Shadow 满足持续时间与样本量要求
- 所有 Gate 通过
- Promote、Reload、Rollback 演练成功
- 生产监控与告警准备完成
- 最终发布决策有完整审计记录

## 13. 阶段门槛

### Gate A：Measurement Trust Gate

必须完成 Phase 22R-25。

通过前禁止：

- 宣称模型提升
- 正式阈值调优
- 新模型晋升

### Gate B：Offline Quality Gate

必须完成 Phase 26-28 的对应质量目标。

通过前禁止：

- Guarded Override
- Partial Rollout

### Gate C：Production Release Gate

必须完成 Phase 29。

通过前禁止：

- Default On
- Auto-Promote

## 14. 每个 Phase 的固定执行循环

每个 Phase 都必须按以下顺序执行：

1. 查询最新生产数据
2. 固定本轮基线和样本范围
3. 输出错误桶和代表性样本
4. 定义一个或多个明确需求
5. 描述技术方法和保护指标
6. 实现最小完整切片
7. 运行单元、集成和回归测试
8. 使用真实 DB、artifact、Replay 或 route 验证
9. 比较前后指标和样本
10. 更新执行总结
11. 判断继续当前 Phase 或进入下一 Phase

## 15. 每轮必须交付的证据

- 环境和代码版本
- 数据时间范围
- Frozen dataset/snapshot
- Active/Candidate runtime identity
- 产物路径和哈希
- 核心指标前后对比
- 错误桶前后变化
- 代表性样本 before/after
- 回归检查
- Gate 结论
- 残余风险
- 下一步建议

## 16. 明确非范围

在 Phase 22R-27 完成前，不优先：

- 全局多国家扩展
- 端到端 Transformer Parser
- 大规模数据库迁移
- 新的控制台视觉重构
- 与核心质量无关的产品功能
- 未经验证的全面规则重写
- 自动把 LLM 结果写成 Human Gold

如果这些事项成为真实关键路径，需要单独更新产品或系统设计文档后再开启新 Phase。

## 17. 计划成功定义

本计划只有在以下条件同时满足时才完成：

1. Active/Candidate/Runtime/Artifact 身份一致且不可变
2. Gold、Frozen Set 和 Evaluator 可信
3. Decision、BuildingType、Unit 和 Commercial 达到约定质量门槛
4. Reference/Canonical 能持续处理新增数据
5. Replay 保存真实逐条差异
6. 7-14 天 Shadow 有人工确认的胜负证据
7. Release Gate、Promote、Reload、Rollback 可验证
8. 生产状态可观测、可解释、可审计
9. 没有关键路径 Phase 仍处于未完成状态

## 18. 建议的第一步

计划批准后，第一轮不修改模型行为。

第一轮应只执行：

1. 冻结当前 registry、workspace、runtime identity 和物理 artifact 清单
2. 形成 Phase 22R 的差异报告
3. 定义唯一活动模型事实源和 manifest contract
4. 写出 Phase 22R 的最小实现切片和回归测试范围

完成这一步并通过评审后，再进入代码开发。
