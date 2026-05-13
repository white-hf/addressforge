# AddressForge 迭代执行计划 - 2026-05-12 (Phase 14: ML Foundation Alignment)

## 文档信息
- 文档类型：Execution Plan / Architecture Delivery Plan
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：统一下一代 ML 的训练、特征和 artifact 基础设施

## 1. 当前背景与问题定义
当前系统已经具备：
- `DecisionModel` CatBoost baseline
- review/gold/freeze/eval 闭环
- retrieval 与 reranker 服务层入口

但 ML 基础设施仍未收口：
- 训练特征与在线推理特征不一致
- artifact contract 不统一
- 模型加载协议分散
- runtime 不能可靠证明“在线吃到的就是训练出的模型”

因此，Phase 14 的任务不是再加功能，而是先把 ML 的基础设施做对。

## 2. 当期总目标
1. 建立统一 `FeatureSchema v1`
2. 建立统一模型 artifact contract
3. 建立统一 model loader / activation 协议
4. 为 Phase 15-18 提供稳定基础

## 3. 具体需求

### 需求 14-1：统一训练与推理特征 schema
交付要求：
- `DecisionModel` 训练和在线推理必须共用同一 schema
- `CandidateRerankerModel` 也必须复用同一 schema 注册机制
- 所有特征必须定义：
  - 名称
  - 类型
  - 缺失值策略
  - 版本号

### 需求 14-2：统一 artifact contract
交付要求：
- 每个模型至少产出：
  - metadata json
  - binary artifact
  - feature schema reference
  - metric summary
- 不允许 runtime 依赖隐式文件名猜测模型含义

### 需求 14-3：统一模型加载协议
交付要求：
- 统一 model path resolution
- 统一 active/shadow version 选择
- 统一 fallback 策略

### 需求 14-4：统一 shadow/compare 输出结构
交付要求：
- `DecisionModel` compare、shadow、artifact summary 输出格式统一
- 为后续 gate 直接消费做准备

## 4. 技术方法
- **FeatureSchema registry**
  - 在 `core/features.py` 之上建立正式 schema 注册层。
- **Artifact manifest**
  - 为各模型定义稳定 manifest，而不是各自散落的 `.json/.pkl/.cbm` 协议。
- **Model loader abstraction**
  - 统一 `DecisionModel / RerankerModel / BuildingTypeModel` 的加载入口。
- **Schema-validated inference**
  - 在线推理前验证特征顺序、类别列、数值列与训练一致。

当前优先实现切片：
- **DecisionModel 训练/推理 schema 对齐**
  - 先为 `DecisionModel` 补一个训练/推理共用的 inference feature builder。
  - 让 `ModelService` 直接按训练 metadata 的 schema 组织在线输入，而不再继续使用旧的 28 维数值向量。
  - 训练主链需要同时落标准化 runtime sidecar：
    - `decision_catboost_v1.json`
    - `decision_catboost_v1.pkl`
    - 保证 serving 不再只依赖裸 `.cbm` 文件。
  - 收益：先解决当前最危险的 runtime 漂移，再向统一 schema registry 推进。

## 5. 预期收益
- 消除训练/推理漂移
- 让 online ML 结果变得可信
- 为后续 runtime 替代和 gate 提供硬基础

## 6. 交付物
- `FeatureSchema v1`
- artifact manifest
- unified model loader
- schema validation report
- Phase 14 execution summary

## 7. 完成标准
当以下条件成立时，Phase 14 完成：
1. `DecisionModel` 训练与推理 schema 完全一致
2. runtime 能从 artifact manifest 正确加载模型
3. compare/shadow 输出可被后续 gate 直接消费

## 8. 后续衔接
Phase 14 完成后，才能进入：
- `Phase 15: DecisionModel Runtimeization`
