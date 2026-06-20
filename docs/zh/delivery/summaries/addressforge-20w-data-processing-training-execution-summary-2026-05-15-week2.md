# AddressForge 20w 数据处理与训练执行摘要 - 2026-05-15 Week 2

## 文档信息
- 文档类型：Execution Summary / Backlog Digestion Result
- 对应计划：[addressforge-20w-data-processing-training-execution-plan-2026-05-15.md](../plans/addressforge-20w-data-processing-training-execution-plan-2026-05-15.md)
- 状态：In Progress
- 范围：Week 2 - review backlog 消化与 top batch 预估 / 重扫

## 1. 总体结论
Week 2 已进入实际 backlog 消化。

本周已经完成：
1. 对 review 最重批次执行 top-batch recovery preview
2. 对最高 review 批次执行定向 reclean
3. 继续对同一 batch 跑 cleaning pass，推动 pending 回流
4. 从 residual bucket 角度拆出当前 batch 的主要残余原因
5. 对次高 review 批次执行 scoped residual reseed
6. 对 `third_party / HASUB-202604240249` 做了 preview，并确认其属于可继续消化的高收益小批次
7. 已对 `HASUB-202604240249` 提交 scoped reclean，当前等待后续 cleaning pass 继续推进
8. 重新预估 `third_party / HASUB-202605072129`，确认该批次在当前 runtime 下仍有较高恢复率，并已再次提交 scoped reclean
9. 对 `historical_db_backfill` 做了 source-scoped preview，确认该源仍然有高 recovery rate，并已提交 source-scoped reclean

## 2. 已完成内容
### 2.1 Top-batch Recovery Preview
已对当前 review 压力最大的批次 `third_party / HASUB-202605112209` 做预估。

该 batch 的 120 条样本预估为：
- `accept = 1`
- `review = 119`
- `projected_recovery_rate = 0.0083`

这说明该 batch 的短期自动恢复收益较低，主要仍是 review-heavy 批次。

### 2.2 Scoped Reclean
已对同一 batch 触发 scoped reclean，并连续运行两轮 `run_cleaning_once`。

实际处理结果：
- 第 1 轮 cleaning：处理 1000 条
- 第 2 轮 cleaning：再处理 1000 条
- 累计处理：2000 条

当前 SQL 统计显示该 batch 的最新分布：
- `accept = 6027`
- `pending = 2364`
- `enrich = 4`
- `review = 2`

### 2.3 Residual Bucket 分析
对该 batch 的 residual bucket 做了拆解，主要残余原因是：
- `Parser confidence is moderate; review is safer.`
- `Address is incomplete and needs manual confirmation.`
- `LOCALITY_MISMATCH`
- `LOW_SCORE_MATCH`

这表明该 batch 主要不是结构崩坏，而是：
- 中等置信度导致的保守 review
- 局部地名 / 参考匹配偏差
- 少量不完整地址

### 2.4 Scoped Residual Reseed
已对 `third_party / HASUB-202605072129` 执行 scoped residual reseed。

播种结果：
- `inserted = 120`
- `active_learning_queue` 总量升至 `1,970`
- 其中 `residual_bucket` 来源样本：`120`

目标桶：
- `history_mismatch`
- `asset_gap`
- `building_type_gap`

### 2.5 Next High-Yield Batch Preview
已对 `third_party / HASUB-202604240249` 做 scoped preview。

该 batch 的 40 条样本预估为：
- `accept = 25`
- `review = 15`
- `projected_recovery_rate = 0.625`

这说明该 batch 比前一个大批次更适合继续重扫，且当前样本中大部分是可被最新 runtime 自动恢复的多单元地址。

### 2.6 Next High-Yield Batch Reclean
已对 `third_party / HASUB-202604240249` 提交 scoped reclean。

当前可见状态：
- `affected_records = 50`
- `job_id = 3079`
- batch 的 review 已被重置为 pending，等待后续 cleaning pass 继续推进

### 2.7 Next Low-Yield Batch Preview
已对 `third_party / HASUB-202605010445` 做 scoped preview。

该 batch 的 40 条样本预估为：
- `accept = 3`
- `review = 37`
- `projected_recovery_rate = 0.075`

这说明该 batch 的短期自动恢复收益偏低，后续应优先留作 residual / calibration 候选，而不是优先投入重扫资源。

### 2.8 High-Yield Batch Reclean (Updated)
已重新预估 `third_party / HASUB-202605072129`。

该 batch 的 120 条样本预估为：
- `accept = 95`
- `review = 25`
- `projected_recovery_rate = 0.7917`

因此该批次继续被认定为高收益回收目标，并已再次提交 scoped reclean。

最新 scoped reclean 结果：
- `affected_records = 1644`
- `rolled_back_to = 7170`
- `job_id = 3086`
- 该 batch 的 review 已被全部重置为 pending，等待后续 cleaning pass 消化

### 2.9 Historical Source Scoped Reclean
已对 `historical_db_backfill` 做 source-scoped preview。

该源的 120 条样本预估为：
- `accept = 114`
- `review = 6`
- `projected_recovery_rate = 0.95`

这说明历史回填源在当前 runtime 下仍有很高的自动恢复空间，适合继续消化 backlog。

最新 source-scoped reclean 结果：
- `affected_records = 3384`
- `rolled_back_to = 13831`
- `job_id = 3093`
- 该源的 review 已被全部重置为 pending，等待后续 cleaning pass 消化

## 3. 验证结果
### 3.1 预估与实际的关系
预估结果说明：
- 该 batch 不是高收益自动恢复批次
- 但它仍是 review 最重的 batch 之一，适合作为 backlog 消化对象

### 3.2 训练可用性
当前 residual 主要集中在 `moderate confidence` 和 `locality mismatch`，后续可回流到：
- calibration
- decision minority
- residual bucket seeding

同时，`HASUB-202604240249` 的预估结果说明：
- 小批次里仍存在明显可恢复空间
- 这类 batch 更适合作为 Week 2 的继续消化对象，而不是直接回流 residual

## 4. 仍待完成
Week 2 的其余高 review 批次仍需继续按优先级处理：
- `third_party / HASUB-202605092211`

当前全局清洗态势：
- `accept = 212950`
- `review = 6980`
- `pending = 1931`
- `enrich = 12`

third_party 当前分布：
- `review = 5474`
- `pending = 53`
- `accept = 25316`

historical_db_backfill 当前分布：
- `review = 1506`
- `pending = 1878`
- `accept = 187634`

当前运行中的清洗 job：
- `job_id = 3094`
- `status = succeeded`
- `current_raw_id = 421326`

当前排队中的后续 cleaning job：
无

同时需要决定：
- 是继续批量 reclean
- 还是将更多 residual 样本优先回流成 gold / calibration

## 5. 阶段结论
Week 2 已启动并取得实际数据结果。

当前方向仍符合 20w 数据治理计划：
- 先用运营闭环消化 backlog
- 再把 stubborn residual 变成新的监督样本
- 最终回到 retrain / shadow / gate
