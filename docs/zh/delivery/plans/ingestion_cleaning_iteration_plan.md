# AddressForge Ingestion & Cleaning Pipeline Milestone & Iteration Plan
## 第三方导入新数据处理系统版本定义与迭代实施排期

本计划与 [ingestion_cleaning_evolution_spec.md](file:///Users/whitetang/Desktop/work/AddressesSystem/addressforge/docs/zh/architecture/ingestion_cleaning_evolution_spec.md) 保持一致，定义了围绕定期新数据导入管道的里程碑演进、开发迭代以及质量防线原则。

---

## 1. 里程碑版本规划 (Roadmap & Milestones)

针对后端第三方定期导入新数据的高精度 ML 清洗系统，我们规划了以下三个核心演进版本：

| 版本代号 | 阶段特征 | 核心特性与变更 | 质量验收标准 (Exit Criteria) |
| :--- | :--- | :--- | :--- |
| **v2.1-Alpha** | **模型与管道联动打通** | 1. 增量 API/DB 导入组件与 Control Worker 全自动联动。<br>2. 接入最新的 CatBoost Decision, Reranker 和 BuildingType 决策模型。<br>3. 引入 LLM Address Refiner 在线局部纠错组件。 | **验收标准**：<br>- 自动跟随清洗机制（Job Chain）在 Ingest 成功后成功触发并执行。<br>- 单元测试通过率 100% (包括 Canadian 地址测试防线)。 |
| **v2.1-Beta** | **高价值特征提取与策略抽样** | 1. 清洗结果表中自动计算并标记高价值地址特征标志位（双地址、公路、显式单元词等）。<br>2. 新增针对这些标志位的主动学习（Active Learning）筛选与智能抽样机制。<br>3. 实现对于 Disagreement（启发式与模型决策不一致）数据的在线导出。 | **验收标准**：<br>- 主动学习队列可按 feature_flags 组合条件成功完成提取。<br>- 人工/LLM 标注的银牌/金牌数据自动回流机制运行顺畅。 |
| **v2.1-Release** | **完全切流与 Shadow 重放测试** | 1. 保留人工触发模式，在控制台（Console）或脚本中触发一次性增量拉取清洗任务。<br>2. 影子管道（Shadow Mode）持续与线上并行跑 14 天，统计决策一致率与运行时间差。 | **验收标准**：<br>- 连续运行期间系统零崩溃。<br>- 清洗单条地址平均时间增长值 $\le 10\text{ms}$。<br>- 影子流水线在决策不一致样本上的推荐准确率 $\ge 92\%$。 |

---

## 2. 详细迭代开发排期 (Detailed Iteration Schedule)

整体项目预计开发周期为 **2 周（1 个标准迭代周期）**。

### 📅 第 1 周：模型整合与流水线联动 (v2.1-Alpha 阶段)
* **[Day 1-2]：Ingestion-to-Cleaning Job Chain 健壮性增强**
  - 增强 `control/jobs.py` 中 `_run_ingestion_job` 在发生失败时的自动调度重试逻辑，优化游标断点保存稳定性。
  - 引入并发锁控制，确保针对同一个 Workspace，同一时间只有一个 `cleaning_once` 运行，防止内存 FAISS 重载和数据库写锁竞争。
* **[Day 3-4]：ML 模型运行时加载与 Override 验证**
  - 验证清洗流水线能够无缝从 `runtime/models` 中动态加载 CatBoost Reranker、Decision 和 BuildingType 侧边栏辅助策略。
  - 编写并运行轻量级 shadow 测试验证，校验 BuildingType override (强力覆盖) 逻辑在订单数据上的实际转换成功率。
* **[Day 5]：局部 LLM Refiner 防线集成**
  - 打通 `LLMAddressRefiner` 在 Cleaning 循环中的应急纠错防线。
  - 验证 LLM 预测结果的 label 来源在落库时严格限定为 `llm_draft`，拒绝转录为 `human` 来源。

### 📅 第 2 周：高价值特征打标与主动学习策略抽样 (v2.1-Beta / Release 阶段)
* **[Day 6-7]：主动特征提取与 Feature Flags 打标**
  - 在 `cleaning.py` 的 `_upsert_stage_result` 步骤中编写高性能正则特征解析方法，对清洗后的数据打标 `has_double_number`，`is_numbered_road`，`has_explicit_unit` 并写入 json 特征字段。
  - 优化特征提取模块的性能，确保大规模批量清洗下的计算耗时在 $\le 1\text{ms}$/条。
* **[Day 8-9]：主动学习智能抽样与审查导出**
  - 基于新提取的 feature_flags，在 Console 管理端提供针对性的审核筛选查询功能，帮助运营团队挑选最困难、最具代表性的“双地址”或“单元号召回困难”样本进行人工金牌打标。
* **[Day 10]：全链路阴影（Shadow）重放测试与发布准备**
  - 开启影子验证流并进行指标统计，对照前一迭代的基线指标，统计 acceptance rate、review rate 和 building_type F1。
  - 单元测试运行验证，全链路性能验收，打包发布 v2.1-Release。

---

## 3. 开发原则与开发红线记录 (Development Principles & Redlines)

为了确保开发过程中的最高系统安全，所有开发工作必须严格遵守以下原则：

1. **红线一：严禁修改 API 游标导致漏单**  
   - 禁止在未编写回滚机制的情况下，直接手动清空或大范围改写 `source_ingestion_cursor` 的游标记录，这可能导致外部第三方系统订单在同步中被永久漏掉。
2. **红线二：严禁未经验证的模型热推广**  
   - 任何新版 CatBoost 模型的更新，必须先产生包含运行身份标识（runtime_identity）的 eval 评测和 shadow 重放结果。严禁跳过 RC 版本在 worker 节点强行推广未记录的模型版本。
3. **红线三：先文档、后代码**  
   - 所有核心 pipeline 重构，必须先修改对应的技术设计文档，取得团队架构评审通过后，方可开展代码变更。
