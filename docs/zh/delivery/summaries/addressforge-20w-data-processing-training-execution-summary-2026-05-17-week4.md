# AddressForge 20w 数据处理与训练执行摘要 2026-05-17 Week 4

## 文档信息
- 项目：AddressForge
- 范围：20w 数据处理与训练闭环
- 周期：Week 4
- 日期：2026-05-17

## 本周已开始执行
### 1. 冻结新的 human gold 基线
已冻结新的 gold snapshot 作为 Week 4 gold / calibration 重建基线：
- `gold_set_version = gold_v20260517`
- `split_version = v20260517`
- `snapshot_id = 27`
- `sample_count = 1406`
- `train/eval/test = 1126 / 154 / 126`

### 2. queued review batch prescreen
对当前 queued review 再做一轮 batch prescreen：
- `workspace = default`
- `limit = 200`
- `processed = 79`
- `cached = 121`
- `skipped = 0`

当前 `review_prescreen_cache` 总量已上升到：
- `673`

### 3. building_type 边界样本补强
使用现有边界样本播种函数补强 Week 4 的 building_type edge cases：
- `semantic_disambiguation`：`inserted = 3`
  - `run_id = 4524`
- `label_consistency`：`inserted = 8`
  - `run_id = 4525`

当前 `review_prescreen_cache` 总量已上升到：
- `752`

### 4. decision minority 再次补强
继续补强 `decision minority` 边界桶：
- `inserted = 120`
- `run_id = 4526`

### 5. decision minority 再补一轮
继续扩充 `decision minority` 队列：
- `inserted = 154`
- `run_id = 4529`

当前 `decision_minority_label / review` queued 队列总量：
- `598`

### 6. queued review 再次预筛
继续对 queued review 进行 batch prescreen：
- `processed = 55`
- `cached = 145`
- `skipped = 0`

当前 `review_prescreen_cache` 总量：
- `938`

### 7. DecisionModel runtime contract hardening
修复了 Week 4 baseline evaluation 中暴露的 DecisionModel sidecar 推理契约问题：
- 决策推理 frame 对 categorical 列做了强制字符串规整，避免 CatBoost 将 categorical 位置误读为浮点值
- worker hot-reload 改为显式跟随当前 active manifest，避免重新刷回 legacy compatibility mode

### 8. City fallback recovery 收口
修复了加拿大地址解析中 city 被默认写成 `Halifax` 的问题：
- `_finalize_parsed()` 不再把缺失 city 强制补成默认城市
- 解析器新增 locality recovery，从原始文本中恢复 `New Glasgow`、`Dartmouth` 等真实 city
- 历史样例 `Granville Street 285, New Glasgow, NS, B2H4Y8, CA` 现在会保留为 `New Glasgow`，而不是回退成 `Halifax`

### 9. Live Baseline 结论
Week 4 candidate 已完成 live baseline evaluation：
- `decision_f1 = 0.2991`
- 对照当前 active `canada_default_v1` 的 `decision_f1 = 0.7214`
- `release_comparison.promote_recommended = false`
- 主要错误桶：`OVER_SENSITIVE_REVIEW`

结论：
- **Week 4 candidate 不进入 promote**
- **当前 active 版本继续保留**

## 意义
这一步把 Week 3 的 residual / calibration / minority 补样结果收敛到了一个新的可训练基线，后续可以在该基线上继续做：
- `decision minority` 重建
- `decision calibration` 重建
- `building_type edge cases` 复查
- 重复地址文本和冲突标签复查
- 继续验证 DecisionModel sidecar / runtime identity 在 live evaluation 中是否与训练产物严格一致
- 继续清理历史数据中被默认 city 误写成 `Halifax` 的记录

## 下一步
- 基于 `gold_v20260517` 继续重建 `decision minority`
- 基于 `gold_v20260517` 继续重建 `decision calibration`
- 复查 `building_type edge cases`
- 检查重复地址文本与冲突标签
