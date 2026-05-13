# AddressForge 迭代执行计划 - 2026-05-12 (Phase 14-18: Next-Generation ML System Completion)

## 文档信息
- 文档类型：Execution Plan / Architecture Delivery Plan
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 总目标：**100% 完成下一代 ML 系统**
- 关联文档：
  - [下一代机器学习系统设计文档](../../ml/addressforge-next-generation-ml-system-design-2026-05-08.md)
  - [机器学习技术演进说明](../../ml/addressforge-ml-evolution-overview-2026-05-08.md)
  - [Phase 8 执行计划](./addressforge-iteration-execution-plan-2026-05-05-phase8.md)

---

## 1. 文档目的

本文件不是继续补充单点优化，而是把当前剩余的下一代 ML 实现工作，拆分成一组**可连续交付、可循环开发、可逐步验收**的迭代。

这份计划回答 4 个问题：

1. 下一代 ML 系统距离“完成”还差什么
2. 这些差距应该按什么顺序收口
3. 每一轮迭代的交付边界是什么
4. 高级开发如何在不推翻现有系统的前提下，把下一代 ML 做到 100%

---

## 2. 当前实现状态判断

根据当前代码、训练产物、review/gold 闭环和 runtime 行为，下一代 ML 已完成的部分主要是：

1. `DecisionModel baseline` 已跑通  
   - 已有 `CatBoost` baseline
   - 已有人审少数类样本补强
   - 已能和 heuristic 做离线 compare

2. review / gold / freeze / eval / shadow 基础闭环已存在  
   - 已能持续把人工审核结果反馈到训练与评测

3. retrieval 能力已接入  
   - 已有 FAISS + embedding 检索层
   - 已能给 parser/reranker 提供 semantic anchors

但距离“100% 完成下一代 ML 系统”仍然有 6 个核心缺口：

1. **训练与在线推理的特征 schema 未统一**
2. **DecisionModel 还没有真正进入 shadow-assist serving**
3. **CandidateRerankerModel 还没有形成真正的监督学习闭环**
4. **BuildingTypeModel baseline 还没有正式落地**
5. **retrieval 仍是 assist，不是稳定融合层**
6. **ML serving / gate / rollout / rollback 还没有形成完整运营闭环**

因此，后续目标不是再做零散 phase8 延伸，而是进入：

- `Phase 14`：统一 ML 基础设施
- `Phase 15`：完成 DecisionModel runtime 化
- `Phase 16`：完成 CandidateRerankerModel
- `Phase 17`：完成 BuildingTypeModel 与 retrieval 融合
- `Phase 18`：完成上线闭环与正式替代策略

---

## 3. 总体完成定义

只有当下面这些条件同时成立时，才可以认定“下一代 ML 系统 100% 完成”：

1. 训练和推理共用同一特征 schema
2. `DecisionModel` 能稳定进入 shadow-assist，并具备受控启用能力
3. `CandidateRerankerModel` 有真实训练、真实模型产物、真实在线消费链
4. `BuildingTypeModel` 有 baseline、compare、shadow 结果，并具备是否接入 runtime 的判断依据
5. retrieval 从“提示层”升级为“稳定融合层”
6. release gate 能同时评估：
   - heuristic 主链
   - supervised model layer
   - shadow delta
   - rollback safety
7. 控制台/流水线/worker 在模型切换后，能真正保证新模型被 runtime 使用
8. 人工审核、少数类补样、样本去重、结构化纠正，能持续为 ML 提供高质量监督

---

## 4. 迭代拆分总览

| Phase | 核心主题 | 目标 |
| :--- | :--- | :--- |
| **Phase 14** | ML 基础设施收口 | 统一特征 schema、统一 artifact contract、统一训练/推理接口 |
| **Phase 15** | DecisionModel Runtimeization | 让 `DecisionModel` 从离线 baseline 升级到 shadow-assist serving |
| **Phase 16** | CandidateRerankerModel Completion | 用真正监督学习模型替代当前统计权重式 reranking |
| **Phase 17** | BuildingTypeModel + Retrieval Fusion | 完成 building_type baseline，并把 retrieval 接入稳定融合层 |
| **Phase 18** | Rollout, Gate, Operations Completion | 完成发布、监控、回滚、自动重清洗、运行时切换闭环 |

---

# Phase 14：ML 基础设施收口

## 14.1 目标

把当前“能训练、能比较、但训练/在线不一致”的 ML 基础设施收口到工程可控状态。

## 14.2 当前问题

1. `DecisionModel` 训练特征和在线特征不一致
2. UFM 没有真正成为训练/推理共用 schema
3. artifact 类型不统一：
   - `.json`
   - `.pkl`
   - `.cbm`
   当前缺少统一 contract
4. `ModelService / RerankerService / trainer` 对模型文件名和载入协议耦合混乱

## 14.3 需求

### 需求 14-1：统一特征 schema
必须建立一个正式的 `FeatureSchema v1`。

交付要求：
- `DecisionModel` 训练与推理必须共用同一特征定义
- `CandidateRerankerModel` 必须使用同一候选特征 schema
- 所有特征必须有：
  - 名称
  - 类型
  - 缺失值策略
  - 版本号

### 需求 14-2：统一模型 artifact contract
必须统一模型训练产物格式。

交付要求：
- 每个模型至少输出：
  - metadata json
  - binary model artifact
  - feature schema reference
  - metrics summary
- 不允许服务层硬编码未知产物格式

### 需求 14-3：统一服务层模型加载协议
必须统一：
- model path resolution
- model version selection
- fallback strategy

### 需求 14-4：统一 shadow compare 结构
离线 compare / shadow 输出必须统一成可复用结构，供后续 gate 使用。

## 14.4 技术方法

- **FeatureSchema registry**
  - 在 `core/features.py` 之上建立正式 schema 定义，不再让训练和 serving 各自拼字段。
- **Artifact manifest**
  - 为 `DecisionModel / RerankerModel / BuildingTypeModel` 定义统一 artifact manifest。
- **Model loader abstraction**
  - 用统一加载器替代当前 `ModelService`/`RerankerService` 的各自硬编码。
- **Schema-validated inference**
  - 在线推理前先校验特征维度、特征顺序和类别列是否一致。

## 14.5 交付物

- `FeatureSchema v1`
- 统一 artifact manifest
- 统一 model loader
- DecisionModel 训练/推理 schema 对齐验证
- Phase 14 implementation notes

## 14.6 完成标准

当以下条件成立时，Phase 14 完成：

1. 训练与在线推理使用相同 schema
2. `DecisionModel` 的在线特征不再与训练特征漂移
3. Reranker / BuildingType 后续模型可复用同一 artifact contract

---

# Phase 15：DecisionModel Runtimeization

## 15.1 目标

让 `DecisionModel` 从“离线 baseline”升级到“可控 shadow-assist runtime”。

## 15.2 当前问题

1. `DecisionModel` 目前只是 compare / shadow baseline
2. 在线 `decision` 仍主要由规则链决定
3. 还没有清晰的：
   - shadow-assist
   - assist-only
   - guarded-override
   三阶段上线策略

## 15.3 需求

### 需求 15-1：DecisionModel shadow-assist serving
必须让 runtime 真正消费新模型输出，但先不直接替换规则。

交付要求：
- runtime 可输出：
  - heuristic decision
  - model decision
  - disagreement reason
- 所有请求都能进入 shadow logging

### 需求 15-2：Decision boundary calibration
必须继续优化：
- `review/reject` 少数类 precision
- `OVER_SENSITIVE_REVIEW`
- `false review`

### 需求 15-3：Decision rollout policy
必须定义何时允许从：
- shadow -> assist
- assist -> guarded override

## 15.4 技术方法

- **Shadow-assist policy layer**
  - 规则链先保留，模型输出作为并行建议。
- **Disagreement bucket logging**
  - 对 `heuristic != model` 的样本做分桶与人工回流。
- **Minority-label closed loop**
  - 继续使用少数类批次抽样，但严格地址文本去重。
- **Threshold tuning with safety guards**
  - 基于 live gold 调整模型阈值，但不能伤 apartment/unit 主线。

## 15.5 交付物

- DecisionModel shadow-assist runtime
- disagreement artifact
- threshold tuning artifact
- rollout readiness summary

## 15.6 完成标准

1. `DecisionModel` 已进入在线 shadow-assist
2. live compare 明确优于 heuristic
3. 有正式 rollout boundary，不再只是实验性 compare

---

# Phase 16：CandidateRerankerModel Completion

## 16.1 目标

把当前“统计权重式 candidate reranking”升级为真正监督学习 reranker。

## 16.2 当前问题

1. `RerankerService` 期待 CatBoost 模型，但训练链不闭环
2. 当前 reranking trainer 仍主要是统计权重
3. semantic alignment 已进入特征，但没有形成稳定监督收益

## 16.3 需求

### 需求 16-1：真实监督式 reranker 训练
必须定义真正的 candidate 监督样本。

交付要求：
- 明确 winner/loser 或 candidate score label
- 输出真正的 `.cbm` reranker artifact
- 能被 `RerankerService` 正常加载

### 需求 16-2：Candidate feature schema v1
必须建立 candidate 级特征 schema。

### 需求 16-3：Reranker compare / shadow
必须能衡量：
- 新 reranker 是否真的提升 best candidate 选择
- 是否改善 unit/building_type 主线

## 16.4 技术方法

- **Pairwise / pointwise reranker baseline**
  - 先从 CatBoost baseline 开始，不直接上神经网络 reranker。
- **Semantic alignment as structured feature**
  - retrieval 结果继续作为特征，而不是直接替代 parser。
- **Candidate disagreement audit**
  - 分析错误 best candidate 的模式，回流人工与 gold。

## 16.5 交付物

- `CandidateRerankerModel v1`
- `.cbm` reranker artifact
- reranker compare report
- reranker shadow report

## 16.6 完成标准

1. `RerankerService` 真正消费监督模型
2. reranking 不再依赖旧权重法作为主逻辑
3. 对 best candidate 选择有可量化提升

---

# Phase 17：BuildingTypeModel + Retrieval Fusion

## 17.1 目标

完成 `BuildingTypeModel` baseline，并把 retrieval 从“辅助提示”升级成“稳定融合输入”。

## 17.2 当前问题

1. `BuildingTypeModel` 还没有正式 baseline
2. retrieval 还不是稳定主锚点，只是 semantic assist
3. commercial / incomplete / prefix-noise 仍大量依赖手工规则

## 17.3 需求

### 需求 17-1：BuildingTypeModel baseline
必须建立：
- `single_unit`
- `multi_unit`
- `commercial`
三分类 baseline 与 compare

### 需求 17-2：Retrieval fusion policy
必须明确 retrieval 在 runtime 里的职责边界：
- 什么时候只是提示
- 什么时候作为强 anchor
- 什么时候必须被规则保护

### 需求 17-3：Commercial/incomplete ML support
必须让模型开始学习：
- commercial prefix noise
- incomplete vs recoverable incomplete

## 17.4 技术方法

- **Building-type structured classifier**
  - 基于 parser/reference/hint 特征做 baseline。
- **Retrieval confidence gating**
  - 用向量分数和结构一致性共同决定 retrieval 影响力。
- **Commercial/incomplete review buckets**
  - 将剩余 review 桶中的 commercial/incomplete 残余纳入监督学习。

## 17.5 交付物

- `BuildingTypeModel v1`
- retrieval fusion policy
- commercial/incomplete benchmark buckets

## 17.6 完成标准

1. `BuildingTypeModel` 有 baseline / compare / shadow
2. retrieval 在 runtime 中有明确、可审计的融合边界
3. commercial/incomplete 不再只依赖规则硬切

---

# Phase 18：Rollout, Gate, Operations Completion

## 18.1 目标

完成下一代 ML 系统的上线闭环，让它成为真正可运营、可回滚、可持续迭代的生产能力。

## 18.2 当前问题

1. 模型训练、worker 重载、runtime 生效之间还有断点
2. `run_evolution_cycle` 类脚本与真实 runtime 生效还不完全一致
3. release gate 还没有把新的 supervised model layer 纳入完整判定

## 18.3 需求

### 需求 18-1：模型生效链闭环
必须确保：
- 训练完成
- artifact 落盘
- worker/API 正确加载新模型
- cleaning / validation 真正使用新模型

### 需求 18-2：Release gate 2.0
必须扩展 gate，使其能同时评估：
- heuristic baseline
- supervised model delta
- shadow disagreement
- rollback risk

### 需求 18-3：Rollback / safe deploy
必须定义：
- 如何启用 assist
- 如何开启 guarded override
- 如何快速回滚

### 需求 18-4：持续学习运营闭环
必须把：
- minority-label seeding
- structured review correction
- feature schema evolution
- shadow disagreement review
接成长期循环

## 18.4 技术方法

- **Model activation contract**
  - 模型切换后必须有统一 reload/activate 流程。
- **Gate by layer**
  - Decision / Reranker / BuildingType 分层看指标，不再混成单一 gate。
- **Safe rollout stages**
  - `shadow -> assist -> guarded_override -> default_on`
- **Operational feedback loop**
  - 将生产中的 disagreement / review 回流到下一轮训练。

## 18.5 交付物

- Release Gate 2.0
- Model activation contract
- rollback procedure
- next-gen ML operations guide

## 18.6 完成标准

1. supervised model layer 可稳定上线
2. runtime 真正吃到新模型
3. gate / rollback / review feedback 构成完整生产闭环
4. 下一代 ML 系统达到“可持续自治优化”的生产状态

---

## 5. 迭代执行顺序

必须严格按下面顺序推进：

1. `Phase 14`
2. `Phase 15`
3. `Phase 16`
4. `Phase 17`
5. `Phase 18`

原因：
- 如果先不统一 schema，后续 runtime ML 都不可靠
- 如果 `DecisionModel` 不先 runtime 化，无法建立 ML serving 主线
- 如果 reranker 不闭环，retrieval 和 building_type 的收益无法稳定传导
- 如果 rollout/gate 不完成，下一代 ML 就不算生产可用

---

## 6. 高级开发执行规则

高级开发在执行本计划时，必须遵守：

1. 每一轮迭代先更新对应执行计划文档
2. 每完成一步，都要验证：
   - 这一步是否真的增强了 ML 能力
   - 这一步是否真的朝系统目标前进
   - 这一步是否是当前阶段最正确的 ML 设计
3. 不允许跳过：
   - live data validation
   - compare/shadow
   - release reasoning
4. 不允许把“新增规则很多”误判成“下一代 ML 已完成”
5. 不允许在训练与推理 schema 不一致时推进 runtime replace

---

## 7. 最终判定

当 `Phase 14-18` 全部完成后，才可以宣布：

**AddressForge 下一代 ML 系统 100% 完成。**

在那之前，系统只能被视为：

- 已进入下一代 ML 实施阶段
- 但仍处于部分完成状态
