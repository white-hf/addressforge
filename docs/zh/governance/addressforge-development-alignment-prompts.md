# AddressForge 开发方向校准 Prompt

## 文档信息
- 文档类型：Development Alignment Reference
- 适用范围：AddressForge 后续产品与工程开发
- 语言：中文
- 状态：Active

## 用途
这组 prompt 用于在后续开发中持续提醒和校准方向，避免系统陷入局部错例优化、运营系统优先级漂移，或重新退回到主要依赖规则补丁的模式。

## 校准 Prompt
1. **优先服务系统设计目标，不要陷入局部错例优化。**
2. **当前主线是提升加拿大 house 和 apartment 的真实解析准确率，尤其是 apartment unit，但不能退化成只做 unit extractor。**
3. **后续质量提升应越来越多来自 gold 驱动的学习权重、candidate quality 和 hard-sample training，而不是主要来自新增正则。**
4. **每轮优化都要说明提升来自规则、模型、数据密度还是候选质量。**
5. **在提升 `unit_number_f1` 和 `unit_recall` 的同时，必须守住 `building_type_f1`、`decision_f1` 和 house 不回退。**
6. **阶段性优化完成后，要回到 canonical address、reference 融合和标准地址资产沉淀主线。**
7. **运营系统问题可以记录，但核心优先级始终低于数据处理与地址质量主链路。**

## 使用方式
- 当需要重新校准开发方向时，可直接引用整份文档。
- 当任务发生偏移时，可逐条对照检查当前工作是否仍符合系统设计目标。
- 当进入新 phase 时，应以本文件作为方向约束，而不是只围绕局部指标推进。

## 结论
本文件不是产品需求文档，也不是执行计划文档，而是 AddressForge 后续持续开发的方向性约束。任何阶段性的优化、规划或代码实现，都应接受这组校准 prompt 的约束。
