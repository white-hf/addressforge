# AddressForge 迭代执行计划 - 2026-05-05 (Phase 8: Incremental Data Intake, Reference Coverage Expansion, And Fresh-Data Quality Validation)

## 文档信息
- 文档类型：Execution Plan / Optimization Requirements
- 适用日期：2026-05-05
- 负责人：AddressForge 产品 / 工程
- 状态：Planned
- 触发原因：Phase 7 已完成 canonical/reference 质量基线建立，当前系统已具备较稳定的地址解析、资产沉淀、reference fusion 与质量诊断能力。下一阶段问题不再是“内部已知样本如何继续收口”，而是“新增增量地址数据进入系统后，如何稳定处理、扩展 reference 覆盖，并在 fresh data 上验证真实收益”。

## 1. 当前背景与问题定义
经过 Phase 3 到 Phase 7：
- unit 相关解析质量已显著提升
- human gold -> training -> evaluation -> replay -> shadow -> gate 已接通
- canonical gap、locality gap、actionable reference gap 已基本清零
- asset quality report 已能区分 benign convergence 与真实质量风险

当前状态说明三件事：

1. **系统内部已知样本的主链路已基本稳定**
   继续只在现有 review pool 上打转，收益会明显递减。

2. **下一阶段必须转向新数据验证**
   如果不引入新的增量地址数据，就无法确认当前模型、reference fusion 与 canonical 策略在 fresh data 上是否仍然稳健。

3. **reference 覆盖会再次成为真实瓶颈**
   在新数据接入后，系统会遇到：
   - 新 locality / building / unit 模式
   - 当前 reference 缺失的区域或 building
   - 当前 canonical 规则未覆盖的新尾部样本

因此，下一阶段核心问题是：

**把当前系统从“在已有数据上做准”推进到“能够稳定接入新增增量地址数据、扩展 reference 覆盖、并在新数据上持续验证解析与资产沉淀质量”。**

## 2. 当期总目标
本阶段目标是：

1. 建立可控的增量地址数据接入与处理能力
2. 建立 fresh data 上的解析质量与 canonical/reference 质量验证机制
3. 识别并量化新数据带来的 reference coverage gap
4. 为后续 reference expansion、fresh-gold 扩样、以及新数据质量治理建立基础

## 3. 核心优化目标

### 3.1 Incremental Intake Stability
系统必须能稳定处理新增地址数据，而不是只在历史样本上工作。

### 3.2 Fresh-Data Quality Validation
系统必须能明确区分：
- 在历史已知数据上表现良好
- 与在新增 fresh data 上仍然表现良好

### 3.3 Reference Coverage Expansion Readiness
系统必须能在新数据进入后迅速识别：
- 真正的 no-reference coverage gap
- locality / street normalization mismatch
- 解析正确但 reference 缺失的 building / unit

### 3.4 Incremental Assetization Confidence
新数据进入后，canonical/reference 主线必须继续保持：
- 稳定 asset promotion
- 可解释 canonical convergence
- 不因增量导入导致质量监控失效

## 4. 具体需求

### 需求 1：新增增量地址数据必须支持受控接入
系统必须支持按批次导入第三方增量地址数据，并对每一批进行独立处理和追踪。

交付要求：
- 增量数据可按批次进入 ingestion / cleaning / assetization 主链路
- 每批新数据应具备可区分的处理范围与结果
- 不允许新增数据与历史数据混在一起而无法做 fresh-data 分析

### 需求 2：新增 fresh-data 质量验证
系统必须建立专门针对新导入数据的质量验证视角。

交付要求：
- 能区分新导入数据与历史数据的处理结果
- 能量化新数据上的：
  - decision 质量
  - building_type 稳定性
  - unit 恢复质量
  - canonical/reference 收敛质量

### 需求 3：新增 reference coverage gap 识别
系统必须在新数据进入后识别 reference coverage 缺口，而不是只看 parse 成功率。

交付要求：
- 能区分：
  - no reference candidate
  - weak locality/street normalization mismatch
  - parse 正确但 reference 缺失
- 能输出 sample-level fresh-data gap evidence

### 需求 4：新增 fresh-data canonical/reference 报表
系统必须能为新增批次生成独立的 fresh-data asset/report 视图。

交付要求：
- report 至少覆盖：
  - fresh rows processed
  - fresh accepted rows
  - fresh reference-backed ratio
  - fresh canonical gap
  - fresh no-reference examples
- report 必须可与历史总体结果并列对照

### 需求 5：新增 fresh-gold 扩样准备
系统必须能从新增数据中筛出最值得进入人工审核与 gold 的高价值样本。

交付要求：
- 能在 fresh data 中识别：
  - 新的 apartment/unit hard cases
  - 新的 reference coverage gap
  - 新的 building_type 边界样本
- 这些样本能直接进入下一轮 review / gold / training

### 需求 6：新增平衡式人工样本抽取
系统必须支持将人工审核样本拆成“纠错池”和“校准池”，而不是继续让 hardest cases 单独主导全部审核输入。

交付要求：
- 系统能区分：
  - hardest correction samples
  - calibration samples close to real production distribution
  - fresh-data-specific high-value samples
- 系统能按目标配比抽样，例如：
  - 常规 `single_unit`
  - 常规 `multi_unit`
  - apartment/unit hard cases
  - double-number house 边界样本
  - numbered-road / highway 样本
  - reference gap 样本
- 生成的 review 批次必须带有样本池类别与抽样原因
- 训练前能量化本轮 gold 的样本池结构，避免 hardest-case 过度集中

### 需求 7：新增 decision 边界校准与历史 gold 语义去污染
系统必须在 apartment/unit 主线恢复后，专门校准 `accept/review/reject` 决策边界，并隔离历史 gold 中非语义任务标签对训练的污染。

交付要求：
- 系统能区分：
  - 用于训练语义的真实任务类型
  - 仅用于采样/流程追踪的历史池标签
- `decision` 阈值学习必须能读取：
  - task_type
  - notes/sample_pool
  - raw_text
  - building_type
  等上下文，而不是只基于裸 confidence
- 历史 `review` hardest-case 样本不能继续无差别地主导 `decision` 阈值学习
- 优化后必须重点验证：
  - `decision_f1`
  - `review_rate`
  - 同时不回退 `building_type_f1 / unit_number_f1 / unit_recall`

## 5. 预期收益映射

### 任务 1：增量数据受控接入
- 预期收益：
  - 让系统从“历史数据优化系统”转向“可持续处理新增数据的生产系统”
- 主要指标：
  - fresh batch processed count
  - fresh batch accepted count
- 次级指标：
  - batch-level processing completeness

拟采用的技术方法包括：
- **DB 历史数据回灌配置化**
  - 支持将控制台 ingestion 从 API 模式切换到 DB 模式，直接指向 `address_raw_history` 这类历史地址表。
  - 收益：不需要额外脚本就能把历史大盘逐步接入主处理链路。
- **控制台 ingestion 配置切换**
  - 在控制台中直接切换 `API / DB` 导入模式，并维护 DB 表、游标列、tie-breaker 列与字段映射配置。
  - 收益：让历史回灌和日常第三方增量可以在同一控制台里安全切换，而不是依赖人工改 `.env.local`。
- **复合游标分页**
  - 对存在大量重复 `created_at` 的历史表，使用 `created_at + order_id` 这类复合游标分页，而不是单列时间游标。
  - 收益：避免 18w 回灌时因为相同时间戳分页而漏数。
- **历史回灌专用 source_name 隔离**
  - 为历史 DB backfill 使用单独 source_name，避免和第三方 API 增量流混淆。
  - 收益：便于后续按来源验证 fresh/historical 分布与训练影响。

### 任务 2：fresh-data 质量验证
- 预期收益：
  - 明确当前模型与规则是否在新数据上泛化
- 主要指标：
  - fresh decision quality
  - fresh building_type quality
  - fresh unit recovery quality
- 次级指标：
  - fresh review rate
  - fresh reject rate

### 任务 3：reference coverage gap 识别
- 预期收益：
  - 把 reference 覆盖问题从“感觉缺”变成“可量化、可抽样、可扩展”
- 主要指标：
  - fresh no-reference count
  - fresh reference-backed ratio
- 次级指标：
  - reference gap reason buckets
  - fresh hotspot evidence count

### 任务 4：fresh-data canonical/reference 报表
- 预期收益：
  - 让新增数据质量与历史基线形成直接对照
- 主要指标：
  - fresh canonical gap
  - fresh asset quality report generation stability
- 次级指标：
  - fresh hotspot explainability

### 任务 5：fresh-gold 扩样准备
- 预期收益：
  - 让下一轮训练从新数据中获得真正高价值监督
- 主要指标：
  - fresh hard-sample candidate count
  - fresh review candidate count
- 次级指标：
  - new pattern discovery count

### 任务 6：平衡式人工样本抽取
- 预期收益：
  - 防止人工审核数据被 hardest cases 过度主导，从而把模型训练方向带偏
  - 让 gold 同时承担“纠错监督”和“分布校准”两种作用
- 主要指标：
  - correction-pool sample count
  - calibration-pool sample count
  - fresh balanced review candidate count
- 次级指标：
  - hard-case ratio in new gold
  - calibration coverage ratio
  - double-number-house negative-sample count

### 任务 7：decision 边界校准与历史 gold 语义去污染
- 预期收益：
  - 提升 `decision_f1`，避免在 apartment/unit 主线恢复后继续被历史 review 流程标签拖低 gate
  - 防止非语义 task_type 污染 decision 阈值学习
- 主要指标：
  - `decision_f1`
  - `review_rate`
- 次级指标：
  - `reject_rate`
  - `GENERAL_MISMATCH` error bucket count
  - `OVER_SENSITIVE_REVIEW` error bucket count

## 6. 技术实现演进说明

### 需求 1：增量地址数据受控接入
拟采用的技术方法包括：
- **批次隔离式导入**
  - 将第三方增量数据按批次进入 ingestion 和 cleaning
  - 作用：确保新数据可单独分析与追踪
- **批次级处理状态关联**
  - 把 ingestion / cleaning / assetization 结果与 batch 级范围绑定
  - 作用：避免新旧数据结果混杂

预期代码载体：
- `ingestion/service.py`
- `pipelines/import_csv.py`
- `services/business_service.py`

### 需求 2：fresh-data 质量验证
拟采用的技术方法包括：
- **fresh-data 子集统计**
  - 基于 batch/source 范围单独计算新数据上的 parsing / validation / assetization 指标
  - 作用：区分“历史表现”和“新增数据表现”
- **fresh-data 对照视图**
  - 将 fresh subset 指标与总体/active baseline 并列
  - 作用：判断新数据是否引入真实泛化回退

预期代码载体：
- `learning/evaluator.py`
- `services/business_service.py`
- `api/routes/business.py`

### 需求 3：reference coverage gap 识别
拟采用的技术方法包括：
- **fresh no-reference 分桶**
  - 对新数据中的 no-reference、street/locality mismatch、parse-correct-but-reference-missing 做分解
  - 作用：避免把新数据 reference 缺口误归到 parser 问题
- **fresh sample-level gap evidence**
  - 对新数据的 gap 样本输出 row-level 证据
  - 作用：让后续 reference expansion 有具体输入

预期代码载体：
- `services/asset_service.py`
- `core/reference.py`

### 需求 4：fresh-data canonical/reference 报表
拟采用的技术方法包括：
- **fresh scope report**
  - 基于 batch/source 生成新数据独立 report
  - 作用：把新数据质量从总体质量中拆出来
- **历史基线并列**
  - 在 report 中同时展示 fresh subset 和当前总体基线
  - 作用：帮助判断系统泛化是否稳定

预期代码载体：
- `services/asset_service.py`
- `api/routes/business.py`

### 需求 5：fresh-gold 扩样准备
拟采用的技术方法包括：
- **新模式候选发现**
  - 在 fresh data 中识别新的 apartment/unit hard cases、reference gap 和 building_type 边界样本
  - 作用：让下一轮 gold 不再只来自旧数据
- **fresh review seeding**
  - 针对新数据生成 review/gold 候选队列
  - 作用：将新增数据直接接入持续学习闭环

预期代码载体：
- `learning/gold.py`
- `api/routes/review.py`

## 7. In Scope
- 增量地址数据接入与批次追踪
- fresh-data parsing / assetization 质量验证
- fresh reference coverage gap 识别
- fresh-data canonical/reference 报表
- fresh-gold review 候选准备

## 8. Out Of Scope
- 运营系统大规模 UI 重构
- release center / reports center 旧缺陷修复
- 多国家 canonical 策略
- 全量 reference 平台重构
- 再次回到 parser/unit 规则作为主线

## 9. 验收标准

### Fresh-Data Quality Acceptance
1. 系统可区分新数据与历史数据的处理结果
2. 系统可输出 fresh-data canonical/reference 质量报告
3. 系统可量化 fresh-data reference gap

### Engineering Acceptance
4. 增量数据可按批次受控进入处理链路
5. fresh-data gap 诊断具备 sample-level 证据
6. fresh-data review/gold 候选可直接进入后续持续学习闭环

## 10. 技术实现演进说明

本节用于说明：同一需求可以通过多轮不同技术实现逐步达成。  
后续继续开发时，必须把新增优化挂到对应需求下面，而不是只写“phase8 又优化了一轮”。

### 需求 1：新增增量地址数据必须支持受控接入
拟采用的技术方法包括：
- **批次隔离式导入**
  - 第三方增量地址数据不直接混入历史 processing 范围，而是先形成独立批次，再进入 ingestion 和 cleaning。
  - 收益：可以明确知道“这批新数据处理后变成了什么”，不会和历史数据结果混在一起。
- **批次级处理范围绑定**
  - 将 ingestion、cleaning、assetization 的处理结果显式绑定到 batch / source scope。
  - 收益：后续 fresh-data 报表、review、reference gap 分析都有稳定过滤范围。
- **增量导入幂等控制**
  - 对同一批第三方数据增加去重键、导入状态或 source-level 唯一约束，避免重复导入导致 fresh-data 统计失真。
  - 收益：保证“新增批次”是真新增，而不是重复处理旧数据。

当前代码载体：
- `ingestion/service.py`
- `pipelines/import_csv.py`
- `services/business_service.py`

技术演进要求：
- 后续如果继续优化这一需求，必须说明是在：
  - 扩大批次隔离范围
  - 增强导入幂等
  - 还是增强批次与后续 cleaning/assetization 的结果绑定

### 需求 2：新增 fresh-data 质量验证
拟采用的技术方法包括：
- **fresh-data 子集统计**
  - 在 evaluation / business metrics 中引入按 batch/source 过滤的新数据子集指标。
  - 收益：可以明确区分“系统在历史数据上稳定”和“系统在新数据上仍稳定”。
- **fresh-vs-baseline 对照视图**
  - 在同一份质量视图中并列展示 fresh subset 与 current baseline。
  - 收益：方便快速判断泛化是否下降，而不是只看全局平均值。
- **fresh acceptance funnel**
  - 将 fresh rows 从 ingest -> cleaned -> accepted -> promotable 的过程拆成漏斗。
  - 收益：可以判断问题出在解析、decision、canonical 还是 reference。

当前代码载体：
- `learning/evaluator.py`
- `services/business_service.py`
- `api/routes/business.py`

技术演进要求：
- 后续必须说明是在增强：
  - fresh 子集指标覆盖
  - baseline 对照能力
  - 还是 processing funnel 的阶段解释性

### 需求 3：新增 reference coverage gap 识别
拟采用的技术方法包括：
- **fresh no-reference 分桶**
  - 将 fresh-data 里的 non-reference / no-reference 样本继续细分成真正无覆盖、street/locality mismatch、parse 正确但 reference 缺失。
  - 收益：避免把 reference 覆盖缺口误当成 parser 质量问题。
- **fresh sample-level gap evidence**
  - 输出 fresh 样本级 gap 证据，包括 raw text、structured fields、candidate locality/street 线索。
  - 收益：reference expansion 可以直接从样本出发，不需要再次人工回溯。
- **fresh reference hotspot 聚类**
  - 对 fresh no-reference 样本按 locality/building/street pattern 聚合。
  - 收益：让后续 reference 扩展优先补“高收益热点”，而不是零散修补。

当前代码载体：
- `services/asset_service.py`
- `core/reference.py`

技术演进要求：
- 后续必须说明是在：
  - 增强 gap 原因分解
  - 增强样本证据
  - 还是增强 hotspot 聚类能力

### 需求 4：新增 fresh-data canonical/reference 报表
拟采用的技术方法包括：
- **fresh scope report**
  - 基于 batch/source 生成新数据独立报表，而不是继续只看 global asset quality。
  - 收益：fresh-data 的 canonical/reference 问题不会被历史大盘掩盖。
- **历史基线并列**
  - 在同一报表中展示 fresh subset 与当前系统整体基线。
  - 收益：能直接观察新数据是否引入回退，而不需要跨多份报告人工拼接。
- **fresh actionable evidence**
  - 报表中直接给出 fresh no-reference examples、fresh review candidates、fresh hotspot buckets。
  - 收益：报表不是只展示结果，而是直接成为下一轮处理任务输入。

当前代码载体：
- `services/asset_service.py`
- `api/routes/business.py`

技术演进要求：
- 后续必须说明是在增强：
  - fresh 范围报表
  - baseline 对照
  - 还是 report 的行动性证据输出

### 需求 5：新增 fresh-gold 扩样准备
拟采用的技术方法包括：
- **新模式候选发现**
  - 从 fresh data 中专门发现新的 apartment/unit hard cases、building_type 边界样本、reference coverage gap 样本。
  - 收益：后续训练不再只依赖历史 hard cases，能持续吸收新分布。
- **fresh review seeding**
  - 直接按 fresh subset 生成 review/gold 候选队列。
  - 收益：新数据可以立即进入人工审核与 gold 闭环。
- **fresh hard-sample density profiling**
  - 对 fresh review/gold 候选做模式分桶与密度统计。
  - 收益：知道新导入数据究竟带来了哪些新问题，而不是只知道“有一些待审核样本”。

当前代码载体：
- `learning/gold.py`
- `api/routes/review.py`

技术演进要求：
- 后续必须说明是在增强：
  - 新模式发现
  - review seeding
  - 还是 fresh hard-sample 画像能力

### 需求 6：新增平衡式人工样本抽取
拟采用的技术方法包括：
- **双样本池抽样**
  - 将人工审核样本拆成：
    - 纠错池：模型最容易错、最有价值的 hardest cases
    - 校准池：更接近真实生产分布的常规样本
  - 收益：防止 hardest cases 单独主导新 gold。
- **分层配比抽样**
  - 对 `single_unit`、`multi_unit`、double-number house、numbered-road、reference gap 等分层设置目标配比。
  - 收益：让人工审核结果既能修边界，也能保持训练分布稳定。
- **fresh/historical 分开抽样**
  - 将新导入数据与历史存量数据分开采样，再按统一配比合并。
  - 收益：避免 fresh data 验证被旧 review pool 淹没。
- **负样本显式补强**
  - 对“看起来像 unit 但其实不是 unit”的地址建立负样本池，如 double-number house、numbered-road house。
  - 收益：直接修复 apartment/unit 主线最容易学偏的边界。
- **样本池结构画像**
  - 在 freeze gold 或训练前输出本轮新增 gold 的样本池结构摘要。
  - 收益：提前暴露“本轮 hardest-case 占比过高”的训练风险。

当前代码载体：
- `learning/gold.py`
- `services/review_service.py`
- `api/routes/review.py`
- `learning/trainer.py`

技术演进要求：
- 后续必须说明是在增强：
  - 样本池拆分能力
  - 分层配比控制
  - 负样本补强
  - 还是训练前样本结构诊断

### 需求 7：新增 decision 边界校准与历史 gold 语义去污染
拟采用的技术方法包括：
- **历史非语义 task_type 归一化**
  - 将 `calibration_accept`、`unit_boost_accept`、`hard_correction_pending` 等历史流程标签从训练语义中剥离，只保留其作为 sample-pool 证据。
  - 收益：避免训练把“样本来自哪个流程”误当成“它属于什么语义任务”。
- **decision 阈值上下文补全**
  - 在 decision policy 学习时补入：
    - task_type
    - notes/sample_pool
    - raw_address_text
    - building_type
  - 收益：让 `accept/review/reject` 阈值不再只由 confidence 驱动，而能真正利用样本上下文。
- **legacy review 降权**
  - 对历史 `review` hardest-case 样本，尤其是无 sample_pool、仅代表旧审核流程的样本，降低其对 decision 阈值的影响。
  - 收益：防止当前模型继续被早期 hardest-case 审核流带偏。
- **decision-only 回归验证**
  - 在每轮训练后单独检查：
    - `decision_f1`
    - `GENERAL_MISMATCH`
    - `OVER_SENSITIVE_REVIEW`
  - 收益：把“地址解析对了但决策边界没收好”从 apartment/unit 主线中分离出来。
- **legacy review 接受恢复**
  - 对历史 `review` 池中已经被人工确认应 `accept` 的样本，专门增强：
    - 不完整候选降权
    - 完整 street 候选提升
    - 前缀/后缀噪音清洗后的结构恢复
    - single-unit parser_disagreement 放松
    - decision calibration 复审核批次生成
    - ordinal street + trailing residential keyword recovery
    - compound residential unit keyword recovery
  - 收益：直接压缩 `OVER_SENSITIVE_REVIEW`，且不回退 apartment/unit 主线。

当前代码载体：
- `learning/trainer.py`
- `learning/evaluator.py`
- `services/review_service.py`

技术演进要求：
- 后续必须说明是在增强：
  - 历史 task_type 归一化
  - decision 阈值上下文
  - legacy review 降权
  - 还是 decision-only 回归验证

## 11. 当期执行顺序

1. 先完成增量批次隔离与 batch-level 结果绑定。
2. 再建立 fresh-data subset 质量统计和 baseline 对照。
3. 在 fresh subset 上补 reference gap 分桶与 sample-level 证据。
4. 生成 fresh-data canonical/reference 独立报表。
5. 从 fresh subset 中抽取 high-value review / gold 候选，接入后续持续学习闭环。
6. 在 review/gold 入口引入平衡式样本池与分层配比控制，防止 hardest cases 过度主导新 gold。
7. 在 apartment/unit 主线恢复后，单独收口 `decision_f1`，并清理历史 gold 的非语义 task_type 对 decision 训练的污染。

## 12. 当前残余问题与进入 Phase 8 的原因

Phase 7 已经把内部已知数据上的 canonical/reference 主线基本收住，但还没有解决以下问题：

1. **系统尚不能稳定区分 fresh data 与历史数据**
   - 当前大部分质量判断仍以全局数据为主。
   - 这会掩盖新数据上的真实泛化问题。

2. **reference coverage 的下一个瓶颈会在新数据上重新暴露**
   - Phase 7 已清掉当前库内已知样本的 actionable gap。
   - 但新增第三方地址进入后，reference coverage 会重新出现真实缺口。

3. **持续学习闭环还缺“新数据来源”**
   - 当前 review/gold/training 主体仍然主要来自历史处理池。
   - 如果不把 fresh data 接进来，系统会逐渐失去对新分布的适应能力。

4. **当前人工审核样本明显偏 hardest cases**
   - 这类样本适合做纠错，但不适合单独代表整体训练分布。
   - 如果不引入校准池和配比控制，模型会更容易被边界样本带偏。

## 13. 风险与关注点

1. **批次隔离不严格**
   - 如果 fresh 数据和历史数据混写，后续所有 fresh-data 报表都会失真。

2. **新数据评估只看全局均值**
   - 这会让系统误以为“整体稳定”，但 fresh subset 实际已回退。

3. **reference gap 与 parser 问题混淆**
   - 如果 fresh no-reference 不做原因分桶，后续会误把 coverage gap 当成解析能力问题。

4. **fresh review 候选回退成旧数据重复样本**
   - 如果 seeding 逻辑没有 fresh-data 过滤，系统会再次回到旧 review pool 打转。

5. **校准样本不足导致训练分布偏移**
   - 如果新 gold 继续由 review/hardest-case 主导，模型会在 apartment/unit 与 double-number house 边界上反复学偏。

6. **历史流程标签继续污染 decision 阈值**
   - 如果 `calibration_accept`、`unit_boost_accept`、`hard_correction_pending` 这类旧 task_type 继续直接进入训练语义，`decision_f1` 会被错误拉低，即使 apartment/unit 主线已经恢复。

## 14. 完成标准

当以下条件同时满足时，Phase 8 可判定为完成：

1. 增量第三方地址数据可以按批次稳定导入并进入处理链路。
2. fresh subset 的 processing / quality / assetization 结果可独立查看。
3. fresh reference gap 可以按原因分桶并输出样本证据。
4. fresh canonical/reference 报表可以稳定生成并与历史基线并列。
5. fresh-data review/gold 候选可被稳定生成，且不是历史重复样本的简单重复派发。
6. fresh-gold review 样本可直接供后续人工审核与训练使用
7. 新人工审核批次可按纠错池 / 校准池明确生成，且训练前能量化新 gold 的样本结构。
8. `decision_f1` 恢复到可与 active 基线直接竞争，且不以牺牲 `building_type_f1 / unit_number_f1 / unit_recall` 为代价。

## 10. 风险与观察点
- 如果新数据不能按批次隔离，fresh-data 分析会失真
- 如果只导入但不建立 fresh-data 质量视角，系统会误把新增问题当成总体噪音
- 如果 reference coverage gap 不拆分，后续 reference expansion 仍会变成盲修

## 11. 完成判定
当以下条件成立时，可认为本阶段完成：
- 新增增量数据可稳定接入处理链路
- fresh-data canonical/reference 质量可独立观测
- fresh reference gap 可量化并附带样本证据
- fresh review/gold 候选可进入后续持续学习闭环

## 12. 执行后要求
本文件是优化需求与执行计划，不是执行总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 phase summary

执行结果不得直接回填到本计划文档中。
