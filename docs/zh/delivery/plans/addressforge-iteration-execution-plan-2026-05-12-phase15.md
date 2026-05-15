# AddressForge 迭代执行计划 - 2026-05-12 (Phase 15: DecisionModel Runtimeization)

## 文档信息
- 文档类型：Execution Plan / ML Runtime Delivery Plan
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：让 `DecisionModel` 从离线 baseline 升级为可控在线能力

## 1. 当前背景与问题定义
`DecisionModel` 已经离线证明优于 heuristic，但当前仍主要停留在：
- baseline training
- compare artifact
- shadow 级验证

它还没有真正进入 runtime 的 assist/override 主链。

## 2. 当期总目标
1. 将 `DecisionModel` 接入 shadow-assist
2. 建立 model-vs-heuristic disagreement 闭环
3. 收口 `review/reject` 少数类边界

## 3. 具体需求

### 需求 15-1：DecisionModel shadow-assist serving
交付要求：
- runtime 同时输出：
  - heuristic decision
  - model decision
  - disagreement reason
- 所有请求进入 shadow logging

### 需求 15-2：Decision boundary calibration
交付要求：
- 针对 `review/reject` 少数类继续优化：
  - false review
  - false reject
  - over-sensitive review

### 需求 15-3：Decision rollout policy
交付要求：
- 定义：
  - shadow
  - assist
  - guarded override
  三阶段策略

## 4. 技术方法
- **Shadow-assist policy layer**
  - 在保持规则主链的前提下，让模型输出进入并行裁决视图。
- **Disagreement bucket logging**
  - 对 `heuristic != model` 样本分桶并回流。
- **Minority-label reinforcement**
  - 继续定向补少数类人审样本。
- **Threshold tuning with safety guards**
  - 在不伤 apartment/unit 主线的前提下校准 decision 边界。

当前优先实现切片：
- **Gold-backed DecisionModel shadow-assist compare**
  - runtime 返回：
    - heuristic decision
    - ml shadow decision
    - disagreement reason
  - evaluator 直接基于最新 human gold 计算：
    - heuristic decision metrics
    - ml shadow decision metrics
    - disagreement buckets
    - shadow advantage
  - 收益：先证明“在线 shadow 结果”和“离线 baseline”一致，再进入 assist/guarded override。

当前验证结果（2026-05-12）：
- active runtime 的 live gold compare 已跑通：
  - heuristic `decision_f1 = 0.6268`
  - ml shadow `decision_f1 = 0.6752`
  - `shadow_advantage = +0.0484`
  - `disagreement_rate = 0.0861`
- 主分桶：
  - `MODEL_MORE_AGGRESSIVE_ACCEPT = 100`
  - `MODEL_MORE_CONSERVATIVE_REVIEW = 21`
- 当前 blocker：
  - 已完成代码级 serving contract 切换
  - live retrain 后日志已确认 active runtime 从：
    - `runtime/models/decision_catboost_v1.json`
    - `runtime/models/decision_catboost_v1.pkl`
    成功载入，不再落入 legacy `.cbm` compatibility mode
  - 当前剩余工作变为：
    - 等本轮轻量 evaluation 产出完整 artifact
    - 再基于新 artifact 进入 assist rollout 门槛判断

当前实现推进（2026-05-13）：
- 已新增 `guarded assist recommendation`，但仍保持 `shadow-only`
- runtime 现在除了输出：
  - `heuristic_decision`
  - `model_decision`
  - `disagreement_reason`
  之外，还会输出：
  - `assist_eligible`
  - `assist_recommended_decision`
  - `assist_guard_reason`
  - `assist_policy_mode`
- evaluator 现在会额外统计：
  - `assist_readiness.eligible_count`
  - `assist_readiness.recommended_decision_counts`
  - `assist_readiness.guard_reason_counts`
  - `assist_readiness.gold_match_rate`
- evaluator 现在还会产出正式 artifact：
  - `decision_assist_rollout_readiness`
  - 其中包含：
    - `status`
    - `checks`
    - `shadow_advantage`
    - `disagreement_rate`
    - `eligible_count`
    - `assist_gold_match_rate`
- evaluator 现在还会进一步产出：
  - `decision_threshold_tuning_hints`
  - 用于把主分桶直接映射到：
    - `assist_accept_score_threshold`
    - `assist_accept_parse_score_threshold`
    - `assist_review_score_threshold`
    - `assist_review_parse_score_threshold`
    - `assist_review_reference_score_threshold`
  等候选调参点
- evaluator 现在还会做：
  - `assist trial simulation`
  - 也就是在不改线上 final decision 的前提下，模拟：
    - 如果按当前 `assist_eligible + assist_recommended_decision`
      试运行 assist，decision 指标会如何变化
- 当前会新增：
  - `assist_trial`
  - `assist_trial_advantage`
  - readiness check:
    - `assist_trial_not_worse_than_shadow`
- evaluator 现在还会产出：
  - `decision_policy_calibration_proposal`
  - 直接给出：
    - 应调哪些 threshold
    - 调整方向
    - 建议步长
    - 调整理由
  - 当前仍保持：
    - `apply_now = false`
  - 即：
    - proposal 由评测系统生成
    - 实际阈值变更由训练链显式消费并写回 artifact / registry

当前实现推进（继续）：
- `trainer` 现在已会读取 active model 最新的：
  - `decision_policy_calibration_proposal`
- 并将受支持的 threshold merge 进新的：
  - `decision_policy`
- 当前已纳入 merge 的 assist 阈值包括：
  - `assist_accept_score_threshold`
  - `assist_accept_parse_score_threshold`
  - `assist_review_score_threshold`
  - `assist_review_parse_score_threshold`
  - `assist_review_reference_score_threshold`
- 训练产物与 registry 会额外记录：
  - `decision_policy_calibration`
  - 包含：
    - source model
    - source version
    - applied changes
- 同时会保留：
  - `decision_policy_before_calibration`
  - `decision_policy`
  这样每轮训练后都可以直接比较：
  - calibration 前阈值
  - calibration 后阈值
- 为了让后续快速循环训练/评测更稳定，现在已新增正式环境开关：
  - `ADDRESSFORGE_SKIP_CANADA_BENCHMARK=1`
- 该开关可用于：
  - training
  - evaluation
- 作用：
  - 跳过 Canada benchmark
  - 先更快验证：
    - `decision_shadow_assist`
    - `assist_rollout_readiness`
    - `assist_trial`
    - `decision_policy_calibration`
- 此外，`AddressPlatformService` 现在已改为：
  - lazy-load vector retrieval engine
- 收益：
  - 评测 / replay / shadow 只在真正需要检索时才初始化向量引擎
  - 避免 `DecisionModel` 轻量训练/评测被向量模型初始化拖慢

这一切的目的不是立即启用 override，而是回答：
- 哪些 disagreement 已具备进入 assist 的安全前提
- 这些 assist recommendation 在最新 human gold 上的命中率如何
- 当前是否已经达到：
  - `ready_for_assist_trial`
  - 还是仍然应该保持：
  - `shadow_only` / `needs_more_assist_calibration`

当前实现推进（2026-05-15）：
- 为了直接压当前最大的 `review` 桶，runtime decision policy 已新增两条保守自动恢复规则：
  - `single_unit_moderate_accept_threshold`
  - `multi_unit_missing_unit_enrich_threshold`
- 目标不是放开所有 moderate-confidence 地址，而是只收：
  - 结构完整、无 reference、无 parser disagreement、无 alternate unit 候选的 `single_unit` 住宅地址
  - 结构完整、无 reference、无 parser disagreement 的 `multi_unit` 缺 unit 住宅地址
- 当前行为：
  - `single_unit + moderate confidence + complete structure` 可直接 `accept`
  - `multi_unit + moderate confidence + missing unit` 可直接 `enrich`
- 设计意图：
  - 优先减少 `Review Suggested` 中最大的住宅 `moderate confidence` 桶
  - 不依赖把整个 runtime 直接切到 `assist_trial`
  - 保持：
    - commercial 守卫
    - parser disagreement 守卫
    - incomplete 守卫

当前实现推进（继续）：
- 已将 `parser_disagreement` 拆分为：
  - `soft disagreement`
  - `hard disagreement`
- 当前判定逻辑：
  - 若 close candidates 仅在同一 base address 上对 `unit_number` 有分歧，则视为：
    - `parser_disagreement = true`
    - `hard_parser_disagreement = false`
    - `parser_disagreement_kind = unit_only`
  - 若 close candidates 连 `street_number / street_name / city / province` 主体都冲突，则视为：
    - `hard_parser_disagreement = true`
    - 继续保守 `review`
- 当前收益：
  - `single_unit` 住宅地址在 soft disagreement 下可继续进入自动 `accept`
  - `multi_unit` 缺 unit 地址在 soft disagreement 下可继续进入 `enrich`
  - 只有真正的 base-address 硬冲突才继续进入 `review`

## 5. 预期收益
- 让 ML 从“离线更好”进化成“在线可观察、可对比”
- 为后续真正替代 heuristic 做证据积累

## 6. 交付物
- DecisionModel shadow-assist runtime
- disagreement report
- threshold tuning artifact
- rollout readiness summary

## 7. 完成标准
1. DecisionModel 已进入在线 shadow-assist
2. disagreement 可被统计、审核和回流
3. assist 阶段具备可启用条件

## 8. 后续衔接
Phase 15 完成后，进入：
- `Phase 16: CandidateRerankerModel Completion`
