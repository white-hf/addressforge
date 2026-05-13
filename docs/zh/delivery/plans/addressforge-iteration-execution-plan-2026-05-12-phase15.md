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

这一切的目的不是立即启用 override，而是回答：
- 哪些 disagreement 已具备进入 assist 的安全前提
- 这些 assist recommendation 在最新 human gold 上的命中率如何

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
