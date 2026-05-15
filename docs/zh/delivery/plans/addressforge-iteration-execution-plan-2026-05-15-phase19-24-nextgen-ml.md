# AddressForge 迭代执行计划 - 2026-05-15 (Phase 19-24: Next-Gen ML Completion)

## 文档信息
- 文档类型：Execution Plan / Delivery Plan
- 适用日期：2026-05-15
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：把下一代 ML 系统从“可运行”推进到“可持续运营、可持续学习、可稳定上线”

## 1. 当前系统状态
当前系统已经具备：
- `DecisionModel` shadow-assist
- versioned runtime bundle
- `BuildingTypeModel` guarded override
- review backlog 的 scoped reclean / preview / evidence / opportunity leaderboard
- release gate / reload / rollback 基础闭环

但距离“100% 完成下一代 ML 系统”仍缺少三类收口：
1. backlog 运营闭环需要稳定落盘并能直接反哺 gold / training
2. residual bucket 需要驱动下一轮阈值和样本重采样
3. runtime / gate / rollback / observability 需要形成最后的生产级一致性

## 2. 总目标
1. 让 review backlog 从“人工可见”升级为“可批量运营、可证据回流”
2. 让 residual bucket 成为下一轮 gold / training / calibration 的正式输入
3. 让 runtime bundle、gate、reload、rollback、shadow、assist 形成一致的生产闭环
4. 让下一代 ML 系统达到长期可运营、可审计、可回滚状态

## 3. Phase 划分

### Phase 19：Batch Recovery Summary 收口
目标：
- 把当前 `preview-top-review-opportunities` 从“总预估”升级为稳定的 batch-level recovery summary
- 让运营能直接比较 top batch 的预估收益，而不是只看合并总数

代码触点：
- `src/addressforge/api/routes/cleaning.py`
- `templates/reports.html`
- `tests/test_cleaning_route.py`

技术方法：
- 为 leaderboard top batch 输出 per-batch recovery summary
- 固化以下字段：
  - `sampled_rows`
  - `accept / enrich / review`
  - `projected_recovery_rate`
  - `projected_remaining_review_rate`
  - `reason_counts`
  - `batch_summaries`
- 让 UI 可比较每个 top batch 的收益排序

完成标准：
- 运营能直接通过控制台比较多个 batch 的预估收益
- 预估逻辑与实际 reclean 逻辑一致
- 测试覆盖 batch-level summary 和总 summary 的一致性

### Phase 20：Residual Bucket -> Gold Re-seeding
目标：
- 将 residual review 主桶回流为新的 gold / calibration / training 输入
- 让 stubborn bucket 不只是被展示，而是变成监督数据

代码触点：
- `src/addressforge/learning/gold.py`
- `src/addressforge/learning/trainer.py`
- `tests/test_gold_sampling.py`

技术方法：
- 按 residual bucket 生成定向 re-seed 样本
- 支持按以下维度采样：
  - `reason`
  - `building_type`
  - `parser_disagreement_kind`
  - `reference_gap_reason`
- 对 `raw_address_text` 做全局去重，避免同址重复灌 gold
- 将 residual review 直接回流到：
  - `decision minority`
  - `decision calibration`
  - `building_type edge cases`

完成标准：
- residual bucket 可生成新的监督样本
- 新样本不重复、不污染旧 gold
- 训练/评测能看到 residual 采样后的真实增益

### Phase 21：DecisionModel Assist 阈值再校准
目标：
- 用真实 backlog 结果和 shadow-assist 证据重新校准 DecisionModel 的 assist 边界
- 让 `assist_trial` 更接近可控生产

代码触点：
- `src/addressforge/learning/evaluator.py`
- `src/addressforge/learning/trainer.py`
- `src/addressforge/api/server.py`

技术方法：
- 围绕当前真实剩余桶重调：
  - `assist_accept_score_threshold`
  - `assist_accept_parse_score_threshold`
  - `assist_review_score_threshold`
  - `assist_review_parse_score_threshold`
  - `assist_review_reference_score_threshold`
- 明确区分：
  - `review -> accept`
  - `review -> enrich`
  - `accept -> review`
- 让评估报告持续输出：
  - `decision_shadow_assist`
  - `decision_assist_rollout_readiness`
  - `decision_threshold_tuning_hints`
  - `assist_trial_advantage`

完成标准：
- assist trial 的阈值调整有结构化提案
- 训练会消费上一轮评测提案
- 下一轮评测能看到可量化变化，而不是只看感知结果

### Phase 22：Reranker / BuildingType 版本化收口
目标：
- 确保 replay / shadow / evaluator / API / worker 对同一 model version 使用同一 runtime bundle
- 防止 active / candidate 串版本

代码触点：
- `src/addressforge/services/replay_service.py`
- `src/addressforge/services/model_service.py`
- `src/addressforge/services/reranker_service.py`
- `src/addressforge/api/server.py`

技术方法：
- 为 reranker / building_type 继续补齐 manifest 绑定
- 让 runtime bundle 返回完整 identity
- 让 replay/shadow/evaluator 输出完整 runtime identity
- 保持 `BuildingTypeModel` 的安全守卫：
  - `building_type_assist_enabled`
  - `building_type_assist_min_confidence`
  - `building_type_assist_allowed_transitions`

完成标准：
- 任一评测都能回溯到物理模型文件和 manifest
- candidate / active / replay / shadow 的模型版本不会混用

### Phase 23：Release Gate / Reload / Rollback 最终一致性
目标：
- 让 promote / reload / rollback 三个动作在生产上真正可靠

代码触点：
- `src/addressforge/models/registry.py`
- `src/addressforge/api/server.py`
- `tests/test_registry_release_gate.py`
- `tests/test_reload_sync.py`

技术方法：
- `promote_model()` 只认：
  - `status == "ready_for_assist_trial"`
  - `checks` 全真
- consistency gate 检查完整 sidecar：
  - `decision_model_artifact.model_path`
  - `decision_model_artifact.metadata_path`
  - `reranker_model_artifact.model_path`
  - `building_type_model_artifact.model_path`
- `/reload` 前清理 registry cache，确保读取的是最新 manifest
- `/rollback` 需要与内存态 reload 一致

完成标准：
- 运维能明确知道为什么不能 promote
- reload 生效路径可验证
- rollback 安全且可审计

### Phase 24：生产化观测与回归
目标：
- 把系统从“可跑”变成“可长期运营”

代码触点：
- `src/addressforge/services/business_service.py`
- `src/addressforge/api/routes/business.py`
- `templates/reports.html`
- `tests/test_business_dirty_addresses.py`

技术方法：
- 把以下内容统一到控制台和报表：
  - `dirty address diagnostics`
  - `review opportunity leaderboard`
  - `batch recovery summary`
  - `residual bucket summary`
  - `release readiness`
- 建立回归测试覆盖：
  - batch preview
  - batch reclean
  - evidence
  - residual buckets
  - promote gate
  - reload / rollback

完成标准：
- 控制台能解释“为什么 review 高、重跑值不值、重跑后降了多少、剩余问题是什么”
- 生产回归能稳定复现关键运营动作

## 4. 执行顺序
推荐顺序：
1. Phase 19
2. Phase 20
3. Phase 21
4. Phase 22
5. Phase 23
6. Phase 24

## 5. 成功判定
下一代 ML 系统只有在同时满足以下条件时才算 100% 完成：
- 自动处理能力明显提升
- review backlog 可持续消化
- residual bucket 能回流训练
- runtime bundle 可追溯
- release gate / reload / rollback 完整闭环
- 控制台和报表能解释生产问题

