# AddressForge 20w 数据处理与训练作业计划 - 2026-05-15

## 文档信息
- 文档类型：Execution Plan / Delivery Plan
- 适用范围：现有 20w（20 万）地址数据的治理、回流、训练与验证
- 负责人：AddressForge 架构 / 高级工程
- 状态：In Progress
- 目标：在不新增产品功能的前提下，利用现有闭环能力把 20w 数据治理成可训练、可验证、可持续回流的高质量监督数据资产

## 1. 设计前提
当前系统已经具备以下能力：
- `dirty address diagnostics`
- `review opportunity leaderboard`
- `preview / reclean / evidence`
- `residual bucket forecast / seed`
- `DecisionModel` shadow-assist
- `BuildingTypeModel` guarded override
- versioned runtime bundle
- release gate / reload / rollback
- runtime identity 审计输出

因此本计划不再增加新功能，而是围绕现有能力完成：
1. 20w 数据分层与冻结
2. review backlog 的批次化消化
3. residual bucket 的回流与再播种
4. gold / calibration / holdout 的重建
5. 模型重训、影子评估、门控验证

### 1.1 Week 1 已完成基线
- `raw_address_record` 行数：`221,873`
- `address_cleaning_result` 行数：`221,873`
- `gold_label` 人工已接受：`1,406`
- `active_learning_queue` 总量：`1,850`
- 当前已冻结 holdout snapshot：
  - `gold_set_version = gold_v20260515`
  - `split_version = v20260515`
  - `snapshot_id = 26`
  - `sample_count = 1,406`
  - `train/eval/test = 1,145 / 129 / 132`
- 当前 review 主桶：
  - `Parser confidence is moderate; review is safer.`: `7,591`
  - `Address is incomplete and needs manual confirmation.`: `1,286`
- 当前 review 批次优先级最高的三个批次：
  - `third_party / HASUB-202605112209`
  - `third_party / HASUB-202605072129`
  - `third_party / HASUB-202605092211`

### 1.2 Week 2 已启动的实际执行
- 已对 `third_party / HASUB-202605112209` 执行 `preview-top-review-opportunities`
- 该 batch 的 120 条样本预估结果：
  - `accept = 1`
  - `review = 119`
  - `projected_recovery_rate = 0.0083`
- 已对同一 batch 启动两轮 `run_cleaning_once`，累计处理 2000 条记录
- 当前 SQL 结果显示该 batch 的清洗分布：
  - `accept = 6027`
  - `pending = 2364`
  - `enrich = 4`
  - `review = 2`
- 该 batch 的残余主因：
  - `Parser confidence is moderate; review is safer.`
  - `Address is incomplete and needs manual confirmation.`
  - `LOCALITY_MISMATCH`
  - `LOW_SCORE_MATCH`
- 已对 `third_party / HASUB-202605072129` 执行 scoped residual reseed
  - 目标桶：`history_mismatch`, `asset_gap`, `building_type_gap`
  - 插入主动学习队列：`120`
  - 当前 `active_learning_queue` 总量：`1,970`
  - 其中 `residual_bucket` 来源：`120`

## 2. 总目标
1. 把 20w 数据拆成稳定的数据层，明确哪些可直接自动处理，哪些需要人工
2. 把当前高 review 批次按收益优先级逐批消化
3. 把顽固 residual bucket 回流成新的 gold / active learning 样本
4. 用冻结验证集、shadow、replay、release gate 构建可重复的训练评估闭环
5. 保证训练结果、运行时绑定、控制台观测和上线门控完全一致

## 3. 数据治理原则
### 3.1 数据分层
20w 数据统一分成五层：
- `raw`：原始导入数据
- `clean`：可稳定自动处理的数据
- `review`：仍需人工判断的数据
- `gold`：人工确认过的高质量标签
- `residual`：重跑后仍顽固的边际样本

### 3.2 训练纪律
- 不把 `review` 全量直接作为主训练集
- 主训练集以 `gold` 为主
- `residual` 只作为定向补强
- 冻结 holdout 必须固定，不能随训练轮次漂移
- `ml_gold` / 多任务样本允许同一个 `raw_id` 在不同 `sample_type` 中各自存在，但同一 `sample_type` 内的 `train/eval/test` 必须互斥
- 任何 `raw_id_cross_split` 类统计都要先区分是跨 `sample_type` 的正常复用，还是同一任务内的真实泄漏

### 3.3 运营纪律
- 批次级操作优先于全库盲扫
- 先 `preview`，再 `reclean`，最后看 `evidence`
- 任何播种动作都必须有明确 `source_name` / `batch_id` 或 residual scope

## 4. 周期性执行计划

### Week 1：20w 数据盘点与冻结
目标：
- 给 20w 数据建立稳定基线
- 确定训练/验证/冻结边界

执行项：
- 盘点当前 `raw / clean / review / gold / residual` 分布
- 按 `source_name`、`batch_id`、`building_type`、`reason` 做基线统计
- 从现有数据中固定一份 holdout 冻结集
- 选出当前最高 review 的 top batches 作为第一轮治理对象

交付物：
- 20w 数据基线摘要
- 冻结集清单
- top batch 优先级列表

完成标准：
- 冻结集固定且不参与后续训练
- 20w 数据分层状态清晰可解释

### Week 2：Review Backlog 消化
目标：
- 用现有 runtime 将最容易恢复的 review 批次先消化掉

执行项：
- 使用 `Review Opportunity Leaderboard` 选择 top batches
- 对每批执行 `Preview Top Batches`
- 只对高收益批次执行 `Reclean Top Batches`
- 使用 `Load Evidence` 验证实际恢复率

交付物：
- 批次级 recovery summary
- 真实 reclean 结果
- 残余 review 清单

完成标准：
- 明确哪些批次值得继续处理
- `review -> accept/enrich` 的收益被量化

### Week 3：Residual Bucket 回流与再播种
目标：
- 把顽固 residual 样本变成下一轮监督信号
- 以当前 gold 分布为依据，优先补强稀有类和边界类，而不是继续扩大已经很厚的 review 类

实际执行进展：
- 已对 `third_party / HASUB-202605112209` 执行 scoped residual reseed
- 采用的 target buckets 为 `history_mismatch`, `asset_gap`, `location_drift`, `building_type_gap`, `parser_disagreement`
- 已插入 active learning queue：`150`
- 已对 `third_party / HASUB-202605072129` 再执行一轮 scoped residual reseed
- 第二轮 inserted：`150`
- 已对 `historical_db_backfill` 执行 source-scoped residual reseed
- 已插入 active learning queue：`150`
- 已对 `third_party / HASUB-202605092211` 再执行一轮 scoped residual reseed
- 第三轮 inserted：`150`
- `decision calibration` 再次播种：`inserted = 0`
- `decision minority` 再次播种：`inserted = 120`
- 已对当前 queued review 执行 batch prescreen：`200`

执行项：
- 使用 `Load Residual Buckets` 识别 stubborn bucket
- 按 `reason` / `building_type` / `parser_disagreement_kind` / `reference_gap_reason` 分类
- 使用 `Seed Residual for Review` 将高价值 residual 样本回流到 active learning / gold
- 对回流样本做去重，防止同址重复灌 gold
- 结合当前 gold 分布，优先补样以下桶：
  - `decision`
  - `commercial`
  - `hard_correction`
  - `gps_conflict`
  - `reference_review`
  - `calibration_accept`
  - `unit_boost_accept`
- 对 `review` 类样本只保留真正的 hard case，不再继续无差别扩张

交付物：
- residual bucket 分布摘要
- 播种样本清单
- 回流后的 gold 增量
- gold 补样优先级清单
- 回流后的 gold 增量
- gold 补样优先级清单

完成标准：
- residual 不再只是可视化结果
- residual 能稳定转成监督样本
- 补样样本在稀有类 / 边界类上形成明显增量

### Week 4：Gold / Calibration 重建
目标：
- 用新回流样本补强少数类和边界样本

实际执行进展：
- 已冻结新的 human gold 基线：
  - `gold_set_version = gold_v20260517`
  - `split_version = v20260517`
  - `snapshot_id = 27`
  - `sample_count = 1406`
  - `train/eval/test = 1126 / 154 / 126`
- 已对 queued review 再做一轮 batch prescreen：
  - `processed = 79`
  - `cached = 121`
  - `skipped = 0`
- 已补强 building_type 边界样本：
  - `semantic_disambiguation = 3`
  - `label_consistency = 8`
- 已继续扩充 `decision minority` 队列：
  - `inserted = 154`
- 已再次执行 queued review batch prescreen：
  - `processed = 55`
  - `cached = 145`
  - `skipped = 0`

执行项：
- 重新构建 `decision minority`
- 重新构建 `decision calibration`
- 重新检查 `building_type edge cases`
- 复查重复地址文本和冲突标签

交付物：
- 新的 gold snapshot
- calibration 样本集
- 重复样本去重报告

完成标准：
- gold 更干净、更平衡
- 少数类和边界类样本数量明显补强

### Week 5：重训与影子评估
目标：
- 让训练结果经过 shadow / replay / evaluator 真实验证

执行项：
- 使用更新后的 gold 重新训练
- 运行 baseline evaluation
- 运行 shadow-assist
- 检查 runtime identity、reranker metrics、decision metrics
- 对比 active / candidate 差异

交付物：
- 新训练 artifact
- shadow 评估报告
- replay 评估报告

完成标准：
- 新模型在冻结集和 shadow 上优于旧版本或至少不退化
- runtime identity 可追溯

### Week 6：门控验证与上线决策
目标：
- 通过 release gate 判断是否进入 promote / rollout

执行项：
- 运行 `promote_model()` 兼容性检查
- 验证 `decision_model_artifact.metadata_path`
- 验证 `reranker_model_artifact` 和 `building_type_model_artifact`
- 检查 `assist_trial`、`shadow_advantage`、`assist_trial_advantage`
- 必要时执行 `reload` / `rollback` 验证

交付物：
- release readiness summary
- promote / hold / rollback 决策
- 生产回归记录

完成标准：
- 新模型只有在门控通过时才进入下一阶段
- 回滚链路可验证、可审计

## 5. 关键指标
本计划不以单一 F1 作为唯一目标，需同时观察：
- `decision_f1`
- `building_type_f1`
- `unit_number_f1`
- `review_rate`
- `reclean recovery rate`
- `residual recovery rate`
- `shadow_advantage`
- `assist_trial_advantage`
- `reranker impact_rate`
- `runtime_identity` 覆盖率

## 6. 风险与约束
### 风险
- 过度依赖全局回放，导致历史噪声被重复放大
- residual bucket 中混入少量噪声样本
- 训练/推理口径不一致，导致“看起来变好但线上不一致”

### 约束
- 不新增产品功能
- 不绕过 release gate
- 不跳过 holdout / shadow / replay
- 不允许空 scope 的 residual reseed

## 7. 成功定义
当以下条件同时满足时，20w 数据处理与训练计划才算完成：
- 20w 数据已形成稳定分层
- 主要 review backlog 已被批次化消化
- residual bucket 已回流为 gold / calibration
- 新模型在冻结集和 shadow 上稳定优于旧版本
- runtime / gate / reload / rollback 全链路一致
- 控制台可以清楚解释每一批数据的处理结果与残余原因
