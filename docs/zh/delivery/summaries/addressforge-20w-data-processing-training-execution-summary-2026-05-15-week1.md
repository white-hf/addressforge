# AddressForge 20w 数据处理与训练执行摘要 - 2026-05-15 Week 1

## 文档信息
- 文档类型：Execution Summary / Baseline Result
- 对应计划：[addressforge-20w-data-processing-training-execution-plan-2026-05-15.md](../plans/addressforge-20w-data-processing-training-execution-plan-2026-05-15.md)
- 状态：Completed
- 范围：Week 1 - 数据盘点与冻结基线

## 1. 总体结论
Week 1 已完成。

本周完成了两个核心动作：
1. 对现网 20w 数据做了真实基线盘点
2. 为当前 human gold 建立了新的冻结 snapshot，作为后续训练的固定 holdout 基线

## 2. 已完成内容
### 2.1 真实数据基线盘点
通过 live MySQL 查询，当前 workspace `default` 的核心状态为：
- `raw_address_record`：`221,873`
- `address_cleaning_result`：`221,873`
- `gold_label` 人工已接受：`1,406`
- `active_learning_queue` 总量：`1,850`
- `active_learning_queue` queued：`417`

清洗结果分布：
- `accept = 212,950`
- `review = 8,911`
- `enrich = 12`

review 主因：
- `Parser confidence is moderate; review is safer.`：`7,591`
- `Address is incomplete and needs manual confirmation.`：`1,286`
- `Commercial-looking address parsed well, but unit details may need confirmation.`：`22`
- `Reference matched a commercial address; suite or unit details may be missing.`：`12`

### 2.2 Top batch 盘点
当前 review 压力最大的批次主要来自 `third_party` 来源，前三个 batch 为：
- `HASUB-202605112209`
- `HASUB-202605072129`
- `HASUB-202605092211`

这些批次的 review 比例大约在 `28% ~ 31%` 区间，适合作为 Week 2 的优先消化对象。

### 2.3 Holdout Freeze
已执行新的 gold freeze：
- `gold_set_version = gold_v20260515`
- `split_version = v20260515`
- `snapshot_id = 26`
- `sample_count = 1,406`
- `train_count = 1,145`
- `eval_count = 129`
- `test_count = 132`

该 snapshot 作为后续 20w 数据训练的固定基线，不再随 backlog 处理随意漂移。

## 3. 验证结果
### 3.1 数据侧验证
盘点结果与系统当前的运营闭环一致：
- review 主桶仍是 moderate-confidence 住宅地址
- backlog 主要集中在少数高 review 批次
- gold 规模足以支撑新的 holdout 冻结

### 3.2 训练侧验证
`freeze_gold_set()` 已成功完成，新的 snapshot 已入库，可供后续训练使用。

## 4. 仍待完成
Week 2 起进入 review backlog 消化：
- `Preview Top Batches`
- `Reclean Top Batches`
- `Load Evidence`
- `Load Residual Buckets`

后续将把 residual bucket 继续回流到 gold / calibration，并据此进入 retrain / shadow / gate。

## 5. 阶段结论
Week 1 已完成。

后续工作应严格按计划推进，不再新增功能，只消化现有 20w 数据并提升模型可靠性。

