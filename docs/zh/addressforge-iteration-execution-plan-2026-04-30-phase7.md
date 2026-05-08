# AddressForge 迭代执行计划 - 2026-04-30 (Phase 7: Canonical Address Quality, Reference Fusion, And Assetization Convergence)

## 文档信息
- 文档类型：Execution Plan / Optimization Requirements
- 适用日期：2026-04-30
- 负责人：AddressForge 产品 / 工程
- 状态：Completed
- 触发原因：Phase 6 已经完成 residential label consistency 与 semantic disambiguation 主线，当前下一阶段瓶颈已从 parser/unit 边界进一步上移到 canonical quality、reference-backed convergence 和标准地址资产沉淀质量。

## 1. 当前背景与问题定义
经过 Phase 5 与 Phase 6：
- apartment/unit 的核心解析指标已明显提升
- `building_type` 语义边界已被稳定
- label pollution 与 `Upper/Lower` 语义噪音已被显式纳入训练和 runtime 处理

当前状态说明两件事：

1. **地址解析主链路已经达到可持续优化状态**
   系统不再主要被 parser/unit 基础能力阻塞。

2. **下一阶段问题转向 canonical 与 reference 质量**
   当前系统还需要更明确地回答：
   - 高置信清洗结果有多少正在稳定沉淀为 canonical building / unit
   - reference-backed 样本和 non-reference 样本的收敛质量是否一致
   - 资产提升过程里是否存在弱 reference、重复归并或 unit 漏沉淀

因此，下一阶段核心问题是：

**把“能解析”进一步推进到“能稳定沉淀标准地址资产”，并让 reference fusion 与 canonical convergence 可量化、可诊断、可持续提升。**

## 2. 当期总目标
本阶段目标是：

1. 建立 canonical building / unit 质量诊断能力
2. 建立 reference-backed 与 non-reference assetization 的对比统计
3. 量化 asset promotion 中的收敛质量、覆盖率与高风险缺口
4. 为后续 reference-first 优化与 canonical merge 策略调整提供可执行诊断依据

## 3. 核心优化目标

### 3.1 Canonical Asset Quality Diagnostics
系统必须能量化当前 canonical 资产沉淀质量，包括：
- eligible accepted rows
- unique building keys / unit keys
- reference-backed canonical convergence
- multi-unit 行里 unit 沉淀缺口

### 3.2 Reference Fusion Visibility
系统必须能区分：
- 由 external reference 驱动收敛的 building / unit
- 只能依赖 base-address-key 的 building / unit
- 高置信但仍无 reference 支撑的 accepted 结果

### 3.3 Assetization Risk Surfacing
系统必须能显式暴露：
- multi-unit 但缺少 unit 沉淀的高风险样本
- accepted 但无 reference 的 canonical promotion 候选
- building/unit 可能收敛不足的热点键

## 4. 具体需求

### 需求 1：新增 canonical/reference 质量诊断服务
系统应能输出一份面向资产沉淀质量的诊断结果。

交付要求：
- 能量化 accepted + promotable rows
- 能区分 reference-backed 与 non-reference-backed 的 building / unit 候选
- 能统计 unique building keys、unique unit keys、rows-per-key 收敛水平
- 能输出高风险样本示例

### 需求 2：新增 asset quality 报告
系统应生成独立的 canonical/reference 质量报告。

交付要求：
- 报告可落盘到 `runtime/reports`
- 报告至少覆盖：
  - promotion coverage
  - reference-backed ratio
  - multi-unit without unit gap
  - canonical convergence indicators
- 报告内容可被后续 phase 直接引用

### 需求 3：asset promotion 结果需具备可解释统计
资产提升过程不能只返回 building/unit 数量，还应补充：
- reference-backed promotion coverage
- unresolved accepted rows
- duplicate-heavy building key hotspots

### 需求 4：后续 reference-first 优化必须建立在可观测诊断上
本阶段先建立质量诊断与可观测基础，不直接大改 merge 策略。

交付要求：
- 下一轮 merge/reference 优化必须能基于本阶段产出的诊断结果解释收益

## 5. 预期收益映射

### 任务 1：canonical/reference 质量诊断服务
- 预期收益：
  - 让 canonical gap 从“只有数量差异”变成“可解释的质量缺口”
  - 让后续 merge/reference 优化不再依赖盲调
- 主要指标：
  - `canonical_building_gap`
  - `canonical_unit_gap`
  - `promotion_skip_reason_counts`
- 次级指标：
  - `reference_backed_building_ratio`
  - `reference_backed_unit_ratio`

### 任务 2：asset quality 报告
- 预期收益：
  - 让 canonical/reference 主线具备可复查、可归档、可对比的阶段产物
  - 让后续迭代能直接基于报表选择优化重点
- 主要指标：
  - report 是否稳定生成
  - report 是否包含样本级例子
- 次级指标：
  - high-risk examples 覆盖度
  - gap 分桶可读性

### 任务 3：asset promotion observability enhancement
- 预期收益：
  - 让资产沉淀过程可解释，而不是只看到最终 building/unit 数量
  - 能区分 reference-backed 与 non-reference 的沉淀贡献
- 主要指标：
  - `reference_backed_rows_processed`
  - `non_reference_rows_processed`
  - `unique_building_keys_processed`
  - `unique_unit_keys_processed`
- 次级指标：
  - `rows_with_units_processed`
  - `avg_rows_per_building_key`

### 任务 4：canonical gap 原因分桶与样本级例子
- 预期收益：
  - 让“为什么没进 canonical”可以直接转成下一轮可执行修复任务
  - 让 locality 缺失、reference 缺失、unit 沉淀缺口被分开处理
- 主要指标：
  - `promotion_skip_reason_counts`
  - `multi_unit_without_unit_examples`
  - `no_reference_examples`
- 次级指标：
  - `duplicate_building_key_hotspots`
  - `multi_unit_unit_coverage`

## 6. 技术实现演进说明

本节用于说明：同一需求可以通过多轮不同技术实现逐步达成。  
后续继续开发时，必须把新增优化挂到对应需求下面，而不是只写“phase7 又优化了一轮”。

### 需求 1：canonical/reference 质量诊断服务
已采用的技术方法包括：
- **可提升资产池筛选**
  - 不是把所有 accepted 行都当成 canonical 候选，而是先基于 accepted + high-confidence 结果建立“可提升资产池”
  - 作用：把资产质量问题和低质量解析结果分开，避免报表被噪音稀释
- **结构字段多来源提取**
  - 同时读取 normalize 结果、best candidate parse 结果、validation 结果中的 locality 和 street 字段
  - 作用：减少单一结构来源缺字段时的误诊断
- **原文 locality 回补**
  - 当 city/province 在结构化结果里缺失时，回到原始地址文本做 locality 恢复
  - 作用：减少因为字段丢失导致的假 canonical gap
- **city -> province 保守映射**
  - 当只恢复出 city、未恢复出 province 时，用现有数据源中的稳定城市映射做保守补全
  - 作用：继续压缩 locality 类阻塞
- **样本级 gap 证据输出**
  - 不只给 gap 数量，还输出 `no_reference_examples`、`multi_unit_without_unit_examples`、`skipped_examples`
  - 作用：让诊断直接转成下一步修复对象

当前代码载体：
- `asset_service.py::_derive_asset_quality_diagnostics()`
- `asset_service.py::_classify_promotion_row()`
- `asset_service.py::_extract_structured_fields()`
- `asset_service.py::_recover_locality_from_raw_text()`
- `asset_service.py::_load_city_to_province_map()`

技术演进要求：
- 后续如果继续优化这一需求，必须说明是：
  - 新增诊断维度
  - 提高样本解释粒度
  - 还是修复 locality / skip-reason 的已有误判

### 需求 2：asset quality 报告
已采用的技术方法包括：
- **独立质量报表产物**
  - 不把 canonical/reference 质量混在普通 evaluation 报表里，而是单独生成 asset quality report
  - 作用：把“资产沉淀质量”从“模型评测质量”里拆出来单独治理
- **热点行级证据挂载**
  - 对 hotspot building key / unit key 挂出 raw row 级样本明细
  - 作用：从聚合统计直接落到可人工判断的具体地址
- **canonical 本体信息联查**
  - 在热点里同时展示 canonical building detail、canonical unit values
  - 作用：判断问题到底在 source row、merge、还是 canonical 本体写入
- **风险视角持续扩展**
  - 报表已逐步加入：
    - `reference_gap_reason_summary`
    - `reference_gap_hotspot_details`
    - `unit_convergence_quality_summary`
  - 作用：让报表从“结果展示”进化成“修复导航”

当前代码载体：
- `asset_service.py::generate_asset_quality_report()`
- `asset_service.py::_fetch_hotspot_row_details()`
- `asset_service.py::_attach_hotspot_details()`

技术演进要求：
- 后续报告增强必须明确属于：
  - 新增风险视角
  - 新增样本级证据
  - 或让 report 字段更接近可执行修复任务

### 需求 3：asset promotion 可解释性增强
已采用的技术方法包括：
- **promotion 过程可观测化**
  - promotion 返回 reference-backed / non-reference / unique building key / unique unit key 等处理统计
  - 作用：不再只看到最终 building/unit 数量，而能知道资产是怎么沉淀出来的
- **promotion 前 row 级分类**
  - 在写 canonical 前，先对每条 row 做可提升/跳过/缺口类型判断
  - 作用：把 write-path 失败原因显式化
- **locality fallback 写入前补救**
  - 在 promotion 前先做 raw-text locality 恢复和 `city -> province` 保守补全
  - 作用：减少本可沉淀但因 locality 缺失被跳过的样本
- **reference fallback 融合**
  - 对 street tail mismatch、弱 locality split 的样本，用保守 reference fallback 选出可接受的参考对象
  - 作用：减少“并非真无 reference，只是结构切分失配”的 non-reference hotspot
- **authoritative canonical refresh**
  - 当 fallback/reference 命中时，用 authoritative reference 刷新 canonical building 的 street/locality 字段
  - 作用：避免 building_key 已 reference-backed，但 canonical 本体仍保留污染字段
- **canonical unit 规范化写入**
  - 在 canonical unit 写入前做 unit 值标准化，如 `NUMBER 2904 -> 2904`
  - 作用：减少 canonical unit 尾部脏值

当前代码载体：
- `asset_service.py::promote_results_to_assets()`
- `asset_service.py::_classify_promotion_row()`
- `asset_service.py::_recover_locality_from_raw_text()`
- `asset_service.py::_load_city_to_province_map()`
- `asset_service.py::_select_reference_fallback_candidate()`
- `asset_service.py::_apply_reference_fallback_enrichment()`
- `asset_service.py::_normalize_canonical_unit_value()`

技术演进要求：
- 后续这类优化必须说明是在改善：
  - promotion coverage
  - reference fusion correctness
  - 还是 canonical building / canonical unit write-path correctness

### 需求 4：基于诊断的 reference-first / merge 优化
已采用的技术方法包括：
- **hotspot 风险分层**
  - 不是所有重复 key 都算 merge 风险，而是按 reference-backed、unit 分布、重复模式区分成：
    - 正常重复
    - likely reference gap
    - likely merge review
    - likely multi-unit convergence
  - 作用：避免大面积误报 merge 问题
- **reference gap 原因分解**
  - 把“non-reference hotspot”继续分解成：
    - 真无 reference
    - locality mismatch
    - street-tail mismatch
    - street conflict
  - 作用：把 reference 问题从单一桶拆成可执行子问题
- **unit convergence 质量分层**
  - 把 multi-unit hotspot 再细分成：
    - 正常多单元聚合
    - unit 规范化问题
    - building_type 混入
    - commercial unit convergence
  - 作用：明确当前尾部问题是在 building merge、reference、还是 unit normalization
- **canonical unit 最终值联查**
  - 读取 canonical unit 最终值来判断问题是否已在写入路径被修正
  - 作用：避免只根据原始 row 文本误判 hotspot 风险
- **同构 single_unit 重复样本降级**
  - 当同一 building key 下只是同一 `single_unit` 地址被重复采集，且无 unit 分裂时，将其降级为 `low_risk_repeat`
  - 作用：避免把重复采样误报成 reference gap 或 merge risk

当前代码载体：
- `asset_service.py::_classify_hotspot_risk()`
- `asset_service.py::_derive_reference_gap_diagnostics()`
- `asset_service.py::_classify_unit_convergence_quality()`
- `asset_service.py::_fetch_canonical_unit_values()`

技术演进要求：
- 后续这类优化必须明确说明是在：
  - 收敛 reference gap
  - 收敛 merge risk
  - 还是收敛 canonical unit 质量尾部问题

## 7. 当前剩余优化焦点

截至当前阶段，`phase7` 的大部分高层目标已经基本达成。  
当前剩余工作主要不是新的 canonical gap，而是尾部质量收口：

1. residual `mixed_building_type_review`
- 对应技术方法：
  - multi-unit hotspot 的 building_type 混入识别
  - hotspot 样本级明细挂载
- 重点场景：
  - 同一 canonical building 下仍混入少量 `single_unit`
  - 但整体又明显是 multi-unit convergence
- 当前问题：
  - report 已能识别 mixed hotspot
  - 但还没有把 benign noise 和真正需要 relabel 的 building_type 污染完全分开
- 目标：
  - 区分 benign single-unit noise vs 真正需要 relabel 的 building_type 污染

2. residual `true no_reference_candidate_found`
- 对应技术方法：
  - reference gap 原因分解
  - 保守 reference fallback 尝试
- 当前 reference gap 主线已大幅收口
- 剩余的这类样本更接近真正的 reference coverage 问题，而不是 street-tail miss
- 目标：
  - 为后续 phase 提供 reference expansion 清单，而不是继续误归类为 merge 问题

3. residual `reference_candidate_found_but_street_conflict`
- 对应技术方法：
  - parser-street / base-key 冲突诊断
  - hotspot 风险分层与 row-level detail 对照
- 当前问题：
  - 少量样本不是完全无 reference，而是 parser street 提取与 reference street 仍存在冲突
- 目标：
  - 继续区分真实 street conflict 与 benign repeat
  - 为后续 reference fusion 或 parser-street 收口提供样本清单

## 8. In Scope
- canonical asset quality diagnostics
- reference-backed vs non-reference assetization statistics
- asset quality report generation
- asset promotion observability enhancement
- high-risk canonical gap examples

## 9. Out Of Scope
- 运营系统 UI 大改
- release center / reports center 已知缺陷修复
- 多国家 canonical 策略
- 大规模资产 schema 重构
- 重新回到 parser/unit 作为主线

## 10. 验收标准

### 质量可观测性验收
1. 系统可输出 canonical/reference 质量诊断
2. 系统可区分 reference-backed 与 non-reference assetization 覆盖
3. 系统可量化 multi-unit 资产沉淀缺口

### 报表与工程验收
4. 生成独立的 asset quality report
5. 诊断结果可提供样本级例子，而不是只有聚合计数
6. 后续 phase 可直接基于这些诊断推进 merge/reference 优化

## 11. 风险与观察点
- 如果 canonical 质量不可观测，后续 merge/reference 优化会重新回到盲调
- 如果只统计 building 数量，不统计收敛质量，会掩盖资产沉淀问题
- 如果 reference-backed 与 non-reference 样本不分开看，后续很难判断 reference fusion 的真实收益

## 12. 完成判定
当以下条件成立时，可认为本阶段完成：
- canonical/reference 质量诊断服务稳定可用
- asset quality report 可生成并包含高风险样本示例
- reference-backed 与 non-reference assetization 差异可被量化解释
- 后续 merge/reference 优化已具备可观测基线

## 13. 执行后要求
本文件是优化需求与执行计划，不是执行总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 phase summary

执行结果不得直接回填到本计划文档中。
