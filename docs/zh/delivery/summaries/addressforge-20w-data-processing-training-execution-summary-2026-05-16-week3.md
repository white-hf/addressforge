# AddressForge 20w 数据处理与训练执行摘要 2026-05-16 Week 3

## 文档信息
- 项目：AddressForge
- 范围：20w 数据处理与训练闭环
- 周期：Week 3
- 日期：2026-05-16

## 背景
前一轮分析已经确认：
- human gold 没有明显大规模错标，但覆盖偏窄
- `ml_gold` 的 `raw_id_cross_split` 主要来自多任务复用，不是同任务泄漏
- 下一步应优先补强稀有类和边界类，而不是继续无差别扩张 `review`

## 本周已执行
### 1. live residual / review 主桶核对
通过 live MySQL 复核了当前最重的 review 批次与主因：
- `historical_db_backfill / NULL`
- `third_party / HASUB-202605112209`
- `third_party / HASUB-202605072129`
- `third_party / HASUB-202605092211`

当前 review 主因仍然是：
- `Parser confidence is moderate; review is safer.`
- `Address is incomplete and needs manual confirmation.`

### 2. residual bucket 范围化播种
执行了 scoped residual reseed：
- `workspace = default`
- `source_name = third_party`
- `batch_id = HASUB-202605112209`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

执行结果：
- 插入 active learning queue：`150`
- `run_id = 4513`
- 当前 `active_learning_queue` 总量：`2120`

### 3. 第二个 residual bucket 播种
继续对次高优先批次执行 scoped residual reseed：
- `workspace = default`
- `source_name = third_party`
- `batch_id = HASUB-202605072129`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

执行结果：
- 插入 active learning queue：`150`
- `run_id = 4516`
- 当前 queued 队列总量：`957`

### 4. 训练目标收口
已将 Week 3 的执行目标收紧为：
- 优先补强稀有类和边界类
- 重点补样：
  - `decision`
  - `commercial`
  - `hard_correction`
  - `gps_conflict`
  - `reference_review`
  - `calibration_accept`
  - `unit_boost_accept`
- 不再继续无差别扩张已经较厚的 `review` 类

### 5. decision calibration / minority 补样
进一步把补样动作落到更明确的监督边界：
- `decision calibration` 重新播种：`inserted = 40`
- `decision minority` 重新播种：`inserted = 80`
- 合计新增主动学习样本：`120`
- 对应运行：
  - `run_id = 4514`
  - `run_id = 4515`

### 6. 第三个高优先 residual 批次补样
继续对下一个高收益批次执行 scoped residual reseed：
- `workspace = default`
- `source_name = third_party`
- `batch_id = HASUB-202605092211`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

执行结果：
- 插入 active learning queue：`150`
- `run_id = 4520`

### 7. 历史回填源补样
针对 `historical_db_backfill` 继续执行 source-scoped residual reseed：
- `workspace = default`
- `source_name = historical_db_backfill`
- `batch_id = NULL`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

执行结果：
- 插入 active learning queue：`150`
- `run_id = 4517`

### 8. decision minority 再补样
继续补强 decision minority 边界桶：
- `decision calibration` 再次播种：`inserted = 0`
- `decision minority` 再次播种：`inserted = 120`
- 对应运行：
  - `run_id = 4518`
  - `run_id = 4519`

### 9. review queue 预筛
对当前 queued 的 review 样本执行 batch prescreen：
- `workspace = default`
- `limit = 200`
- `overwrite = false`

执行结果：
- 处理样本：`200`
- 命中缓存：`0`
- 跳过：`0`
- `review_prescreen_cache` 总量：`673`

## 验证与证据
- residual reseed 运行完成，返回 `inserted = 150`
- 第二个 residual reseed 运行完成，返回 `inserted = 150`
- 第三个 residual reseed 运行完成，返回 `inserted = 150`
- `historical_db_backfill` source-scoped residual reseed 运行完成，返回 `inserted = 150`
- decision calibration 运行完成，返回 `inserted = 40`
- decision minority 运行完成，返回 `inserted = 80`
- decision calibration 再次播种返回 `inserted = 0`
- decision minority 再次播种返回 `inserted = 120`
- active learning queue 总量确认上升至 `2810`
- `residual_bucket/building_type` queued 队列总量：`714`
- `decision_minority_label/review` queued 队列总量：`204`
- `decision_calibration/review` queued 队列总量：`40`
- batch prescreen 已成功处理 `200` 条 queued review，并写入 `review_prescreen_cache`
- 当前 queued 队列继续增长，说明 Week 3 的补样链已经真正开始回流
- residual_bucket/building_type 仍然是当前最大的未消化补样桶
- 计划文档已同步补充训练纪律：
  - 同一 `sample_type` 内 `train/eval/test` 必须互斥
  - `raw_id_cross_split` 统计需先区分正常多任务复用与真实同任务泄漏

## 残余风险
- 当前补样仍偏向 residual / review 边界样本，`decision` / `commercial` 这类稀有类仍需要后续专门补样
- calibration / minority 已经开始补强，但 `commercial` / `gps_conflict` / `hard_correction` 这类边界类仍需要后续专门补样
- 还需要继续观察 residual bucket 的实际回流效果，再决定是否进入 gold / calibration 重建

## 下一步
- 继续执行 Week 3 的 residual bucket 回流与再播种
- 根据 residual summary 持续补强稀有类与边界类
- 继续补 `decision calibration` 与 `decision minority` 的边界桶
- 进入 Week 4 的 gold / calibration 重建前，先确认补样是否已经形成有效增量
