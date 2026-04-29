# AddressForge 迭代版本计划

> 中文：以加拿大地址质量为核心的迭代开发计划。

> English: Iteration plan focused on Canada address quality first.

## 1. 当前目标

AddressForge 当前阶段不再优先追求“平台外壳更完整”，而是优先完成：

- 加拿大 / 北美地址清洗做准
- 模型训练与调优做实
- gold / active learning 做强
- 发布级 benchmark 做成默认评测标准
- 标准地址沉淀可用于历史库重清与在线 API

这意味着后续版本优先级调整为：

1. 地址清洗准确率
2. 模型训练与调优
3. gold / active learning
4. 评估体系
5. building / unit / reference 质量提升

控制台、平台化抽象、第三方二次开发友好性继续保留，但不再作为主开发线。

## 2. 版本原则

1. 先把加拿大地址做准，再考虑其他国家
2. 先把 benchmark 做实，再做 promote
3. 先修高频真实错型，再补长尾
4. 先形成标准地址资产，再扩平台体验
5. 每个版本都必须能量化说明“比上一版更好还是更差”

## 3. 迭代地图

### Iteration 1: Canada Parsing Baseline

目标：

- 收住加拿大高频地址模式
- 让 parser 和 validate 不再明显漏掉 unit / building type / commercial

范围：

- `apt / suite / rm / fl / #`
- `basement / lower / upper`
- `rear / front / side`
- `main floor / ground floor / gf`
- `2nd/3rd floor`
- `penthouse / ph`
- `building / bldg`
- `house / multi_unit / commercial` 边界
- 加拿大无逗号尾巴、street tail 脏文本

退出标准：

- Canada benchmark 的核心示例集可以稳定通过
- 解析错误不再集中出现在这些高频模式上

### Iteration 2: Canada Benchmark and Error Buckets

目标：

- 建立发布级 benchmark
- 用错误分桶驱动后续优化，而不是靠感觉改规则

范围：

- `decision`
- `building_type`
- `unit_number`
- `commercial`
- `accept/review/reject rate`
- 失败样本分桶

退出标准：

- evaluator 固定输出发布级核心指标
- candidate 和 active 可以按同一标准比较

### Iteration 3: Gold and Active Learning

目标：

- 把训练信号做强
- 让系统知道“最值得人工看、最值得学习”的样本

范围：

- human gold
- freeze
- active learning queue
- 错例驱动采样
- benchmark 样本扩展

退出标准：

- 有一批代表性足够的 Canada gold
- active learning 不再只是存表，而能服务训练样本迭代

### Iteration 4: Training, Evaluation, Shadow, Promote

目标：

- 把模型训练闭环做成真正提升准确率的主线

范围：

- train
- eval
- shadow
- promote
- release benchmark gate

退出标准：

- 新模型上线必须经过固定 benchmark
- candidate vs active 的比较结果可复现

### Iteration 5: Canonical Address and Reference Quality

目标：

- 把清洗结果从“解析输出”变成“标准地址资产”

范围：

- canonical building
- canonical unit
- reference-first 决策
- building / unit 去重与沉淀

退出标准：

- 同一地址的不同写法能稳定沉淀到同一资产
- reference 与 parser 的冲突有明确处理策略

### Iteration 6: Historical Replay and Release Readiness

目标：

- 让系统具备重清历史库、发布新版本、量化验收的能力

范围：

- 历史数据回放
- 发布级 benchmark 报告
- 版本间对比
- release gate

退出标准：

- 可以对一整批历史数据重跑并给出量化对比
- 可以明确判断某次发布是否值得 promote

### Iteration 7: Country Abstraction After Canada

目标：

- 在加拿大实现完整、稳定后，再抽象国家插件层

范围：

- Canada profile 固化
- parser / reference / benchmark 的 country adapter
- 其他国家作为后续可插拔能力

退出标准：

- 加拿大逻辑不再散落在核心流程里
- 系统开始具备迁移到其他国家的结构基础

### Iteration 8: Canada Decision Fusion and Real Training

目标：

- 把当前“策略学习”推进成真正会影响候选排序和决策的训练链路
- 让训练产物不再只是版本登记，而是可以被 benchmark、shadow、replay 真实使用

范围：

- parser feature vector 标准化
- parser reranker / parser weight 学习
- decision calibration
- 训练 artifact 与推理路径强绑定
- candidate model 按版本参与 benchmark / evaluation / replay
- 修复当前训练/推理主链路里的占位与断裂点：
  - `RerankerArtifactLoader` 缺失
  - `AddressRequest.reranker_version` 缺失
  - reranking trainer 与当前 schema 不一致
- parser weight 学习必须来自真实 gold 对比，而不是常量正确标签

具体任务要求：

1. Reranker runtime 收口
- 补齐 `RerankerArtifactLoader`
- 给 `AddressRequest` 增加 `reranker_version`
- `parse()` 能按请求版本或 active 版本加载 reranker artifact
- 若 artifact 缺失，必须有明确 fallback，不允许运行时报错

2. 训练数据抽取与 schema 对齐
- `reranking_trainer` 不再读取不存在的列
- 从 `parser_json` / `validation_json` 中抽取可用特征
- 从 `gold_label` 与 `address_cleaning_result` 对比中生成真实监督标签
- 去掉任何 `target_is_correct = 1` 之类的伪标签逻辑

3. parser feature vector 标准化
- 明确 parser 级特征字段
- 明确 validation 级特征字段
- 特征名和数据类型固定，供 trainer / benchmark / replay 共用

4. 决策策略学习
- `decision_policy` 不仅学习阈值
- 要包含可解释的 parser weight / disagreement weight / reference weight
- 训练 artifact 中必须可见这些参数

5. 版本绑定
- benchmark / shadow / replay 必须能加载指定 model version 的 runtime
- 不能再出现“评测挂在候选版本号上，但实际跑的是默认行为”

退出标准：

- 新训练版本会真实改变推理行为
- candidate 与 active 的差异可以在 benchmark / shadow / replay 中复现
- 不再存在“训练成功但模型行为没有变化”的情况
- parse 主链路不会因为 reranker 相关缺失而运行时报错

### Iteration 9: Canada Gold Expansion and Review Quality

目标：

- 扩大加拿大代表性 gold
- 让 active learning 和 review 结果真正持续喂给训练

范围：

- house / multi-unit / commercial 的代表性 gold 扩样
- missing unit / parser disagreement / reference conflict 样本补齐
- review -> gold_label -> active_learning_queue 的闭环质量检查
- 错例驱动的 active learning 排序
- benchmark 样本集继续扩展
- 修复和验证：
  - review 结果与 gold label 的一致性
  - active learning 排队理由是否来自真实错例分桶
- LLM 证据是否真正影响 review / gold，而不是只写说明字段

具体任务要求：

1. gold 扩样设计
- house
- multi-unit
- commercial
- missing unit
- parser disagreement
- reference conflict
- rural / low-confidence 长尾样本

2. review 闭环质量
- review 提交后必须稳定写入 `gold_label`
- `active_learning_queue` 状态必须正确推进
- review 样本要能追溯来源、原因、风险点

3. active learning 排序
- priority 不能只看置信度
- 要叠加错误分桶、parser disagreement、reference conflict、商业楼/公寓边界等因素

4. benchmark 扩展
- benchmark 不只保留 curated happy path
- 加入真实错例回放样本
- benchmark 样本要覆盖 release gate 关注的核心错型

退出标准：

- gold 样本对加拿大主要地址类型具有代表性
- active learning 队列不再只是存表，而能持续产生高价值训练样本
- evaluator 的错误分桶能稳定回推到 review 和采样策略

### Iteration 10: Canonical Asset Consolidation at Scale

目标：

- 把解析结果稳定沉淀成 building / unit 标准地址资产
- 在大批量数据上验证 canonical 合并和 reference-first 语义

范围：

- canonical building / canonical unit 最终 schema 收口
- workspace 维度的 canonical 资产隔离
- building / unit merge key 与去重策略
- reference provenance 与冲突优先级
- asset promotion 幂等与新增统计修正
- 对 canonical 表与当前业务代码的兼容层进行清理，避免长期“双语义”状态

具体任务要求：

1. canonical schema 收口
- 明确 `canonical_building` / `canonical_unit` 的最终字段
- 明确 workspace 维度主键/唯一键
- 明确 source attribution 和 reference provenance 结构

2. 资产合并规则
- building merge key
- unit merge key
- 同地址不同写法的规范化合并逻辑
- building + unit 的拆分与回收敛逻辑

3. promotion 语义修正
- `new_buildings` / `new_units` 必须是新增资产数
- 不能把重复 upsert 当作新增
- promotion 必须幂等

4. reference-first 落地
- parser 与 reference 冲突时的优先级
- reference 缺失时的 fallback 策略
- 商业建筑、多单元住宅、独栋住宅的 canonical 规则差异

退出标准：

- 同一地址不同写法能稳定沉淀到同一资产
- canonical promotion 不会跨 workspace 混入
- promotion 统计反映真实新增资产，而不是重复尝试

### Iteration 11: Historical Replay at Canada Scale

目标：

- 对加拿大历史数据做真实 replay
- 用 replay 结果量化版本升级是否值得发布

范围：

- replay run / result 全量持久化
- candidate vs active 的 replay 对照
- mismatch buckets
- replay 汇总报表
- replay 指标并入 release benchmark / release report
- 替换当前 replay 模拟逻辑，要求：
  - 真正执行 candidate runtime
  - 真正执行 active runtime
  - 不允许使用模拟决策或伪造一致性分数
- replay 失败必须可见、可阻断 promote

具体任务要求：

1. replay runtime
- active runtime 必须真实加载 active model
- candidate runtime 必须真实加载 candidate model
- 不允许使用模拟 decision / 模拟一致性分数

2. replay 持久化
- `historical_replay_run` 记录汇总信息
- `historical_replay_result` 记录逐条对比
- mismatch 样本必须可查询、可分桶

3. replay 指标
- decision match rate
- building type match rate
- unit number match rate
- candidate vs active disagreement rate
- replay failure count

4. release 集成
- replay 结果必须进入 evaluation artifact
- replay 失败、runtime 加载失败、样本不足都必须明确写进 release report

退出标准：

- 可以对一整批加拿大历史数据重跑并产出量化对比
- replay 结果能直接用于 promote / keep_active 决策
- 发布评测不再只依赖小样本 benchmark
- replay 主链路不存在占位实现或未定义变量

### Iteration 12: Canada Release Gate and Production Quality

目标：

- 建立真正的加拿大版本发布门槛
- 让模型、规则、reference 升级都必须通过同一套 release gate

范围：

- release benchmark 与 replay gate 合并
- promote / keep_active / rollback 规则收紧
- decision_f1 / building_type_f1 / unit_number_f1 / unit_recall / commercial_f1 固定门槛
- accept / review / reject rate 漂移检查
- 失败发布的回退语义
- 修正当前 release gate 的失败策略：
  - benchmark / replay 解析失败必须阻断 promote
  - 指标缺失不能视为通过
- regression risk 和 shadow gate 必须一起生效

具体任务要求：

1. gate 失败策略
- 指标缺失 -> block
- benchmark 解析失败 -> block
- replay 解析失败 -> block
- shadow 结果缺失 -> block

2. 固定门槛
- `decision_f1`
- `building_type_f1`
- `unit_number_f1`
- `unit_recall`
- `commercial_f1`
- `review_rate`
- `reject_rate`
- `regression_risk`

3. promote / rollback 规则
- promote 需要同时满足 benchmark + replay + shadow
- keep_active 要保留失败原因
- rollback 需要明确回滚到哪个 active 版本

4. release report
- 每次版本发布必须输出统一格式报告
- 报告必须同时包含 benchmark、shadow、replay、drift

退出标准：

- 每次加拿大版本发布都有固定量化报告
- promote 决策可复现、可解释
- regression 风险能在发布前被拦住

### Iteration 13: Canada Profile Extraction and Future Country Boundary

目标：

- 在加拿大系统做完整、做准之后，再抽国家边界
- 让未来其他国家的接入基于稳定骨架，而不是提前抽象

范围：

- `CanadaProfile` 固化
- parser / reference / benchmark / normalization 的 Canada pack
- 将加拿大特有逻辑从 core 主链路里收口到 profile
- 为后续其他国家保留插件边界，但不提前实现其他国家逻辑
- 去掉当前 import-time 单例 profile 语义，改成：
  - request/model/workspace 可显式选择 profile
- 同一进程内可并存多个 profile runtime
- profile 不只是响应字段，而是真正参与解析/标准化/校验

具体任务要求：

1. runtime profile 传递
- request 级 profile
- model artifact 级 profile
- workspace 默认 profile
- 三者优先级必须明确

2. core 去单例化
- 去掉 `common.py` / `utils.py` 中 import-time `_ACTIVE_PROFILE`
- 解析、标准化、校验都改成显式接收 profile runtime

3. Canada pack 收口
- Canada parser patterns
- Canada normalization
- Canada reference rules
- Canada benchmark rules
- Canada-specific 决策逻辑

4. 未来扩展边界
- 只保留 profile / parser / reference / benchmark 的扩展接口
- 不提前实现其他国家逻辑
- 不影响当前加拿大主链路性能和准确率

退出标准：

- 加拿大特有逻辑不再散落在 core
- AddressForge 对外呈现为“加拿大默认实现 + 后续国家可插拔边界”
- 不影响当前加拿大质量主线
- profile 选择不会再被环境变量单例写死

## 4. 2026-04-28 后的当前状态

根据 `AddressForge Iteration Summary - 2026-04-28` 以及当前代码状态，可以更准确地描述为：

- Iteration 1 已经形成可用的加拿大解析基线
- Iteration 2 的 benchmark / error bucket 基础已经存在
- Iteration 3 到 Iteration 7 有部分地基已经落地，但并未全部收口
- 当前最重要的不是继续扩平台外壳，而是把这些地基收成一个真正可发布的加拿大系统

已经落地的代表性成果包括：

- 加拿大高频 unit / building / commercial 模式解析增强
- release benchmark 指标框架
- training / evaluation / shadow / replay 的基础骨架
- review -> gold_label 与 replay 持久化的主链路
- `BaseCountryProfile` / `CanadaProfile` 的初步边界

但仍未完全收口的关键点包括：

- 训练仍需继续向真实 reranking / calibration 发展
- replay 和 release gate 还需要在更大规模加拿大数据上验证
- canonical 资产还需要完成最终 schema 和大规模合并验证

因此，后续正式开发从 **Iteration 8** 开始，目标是把前面 1-7 的部分地基收成完整、可发布的加拿大系统。

## 5. 基于 2026-04-28 审查的当前优先顺序

在继续执行 Iteration 8-13 时，先按下面顺序收口关键阻塞点：

0. **先修主链路稳定性断裂**
- `create_run()` / `etl_run` 字段名必须与 schema 一致
- `simple_parse_address()` / `normalize_province()` / `_finalize_parsed()` 的新旧签名必须统一
- 任何会导致 `normalize/parse/validate` 直接 `TypeError` 的改动必须先清零

1. **Iteration 8 先修真实训练/推理断裂**
- 补齐 reranker runtime 缺失
- 让训练产物真正进入 parse/validate 主链路
- 修正训练数据与 schema 不一致问题

2. **Iteration 11 去掉 replay 模拟实现**
- candidate vs active 必须真实执行
- replay 结果必须真实落库并参与 release report

3. **Iteration 12 收紧 release gate**
- 任何评测缺失、解析失败、replay 异常都必须阻断 promote

4. **Iteration 13 重新做 profile runtime 边界**
- 先把 Canada profile 真正做成 runtime 可选
- 再谈未来其他国家

## 6. 当前代码审查新增阻塞项

以下问题已经通过代码审查确认，会直接阻断 8-13 迭代的完成判定：

1. **请求主链路存在运行时断裂**
- `simple_parse_address()` 仍按旧签名调用 `_finalize_parsed()`
- `api/server.py` 仍按旧签名调用 `normalize_province()`
- profile runtime 改造已部分进入代码，但主路径尚未收口

2. **reranker runtime 仍未闭合**
- `RerankerArtifactLoader` 仍缺失
- `AddressRequest.reranker_version` 仍缺失
- 候选版本解析仍无法真正按版本加载权重

3. **reranking trainer 仍与 schema 不一致**
- 仍读取不存在的 `unit_source` / `feature_vector` 列
- 仍使用 `target_is_correct = 1` 伪监督

4. **historical replay 仍未完成真实 runtime 绑定**
- `_load_model_runtime()` 仍是占位
- replay 中 active / candidate 仍未真正加载各自 runtime
- 目前的 candidate 差异仍主要依赖未落地的 reranker version 路径

5. **release gate 仍未完全达到文档要求**
- 已经收紧了缺失指标处理
- 但尚未对 `building_type_f1`、`unit_number_f1`、`unit_recall`、`commercial_f1`、`review_rate`、`reject_rate` 全部执行硬门槛

## 7. 8-13 迭代的更细执行顺序

### Phase A: Runtime Stabilization

先完成下面 4 个动作，再继续往后推进：

1. 对齐 `etl_run` 运行记录接口与 schema
2. 对齐 `common.py` / `api/server.py` 的 profile 与 normalize/parse 函数签名
3. 去掉所有会导致请求主链路直接异常的残留旧调用
4. 用最小 smoke test 验证 `normalize -> parse -> validate` 可运行

### Phase B: Iteration 8 Completion

1. 实现 `RerankerArtifactLoader`
2. 给 `AddressRequest` 增加 `reranker_version`
3. 让 active/candidate 模型都能加载对应 artifact
4. 修正 `reranking_trainer` 特征抽取与监督标签
5. 用真实 gold 样本重训 parser weights

### Phase C: Iteration 11 Completion

1. 把 replay 改成真正的 active runtime vs candidate runtime
2. replay 输出 building / unit / decision 三层对比
3. replay 失败、样本不足、runtime 加载失败都要落库
4. replay 结果进入 evaluation artifact 和 release report

### Phase D: Iteration 12 Completion

1. 扩完整套 release gate 指标
2. shadow / replay / benchmark 三者共同决定 promote
3. 指标缺失、解析失败、回放失败全部 block
4. 明确 rollback 的版本选择和记录语义

### Phase E: Iteration 13 Completion

1. 去掉 import-time 单例 profile
2. 建立 request/model/workspace 三级 profile 优先级
3. 让 Canada profile 真正贯穿 normalization / parsing / validation
4. 最后再保留未来国家扩展边界

## 8. 开发节奏

后续开发按下面方式执行：

1. 只做当前迭代相关任务
2. 一个迭代内部连续完成多个相关任务，不中断切题
3. 一个迭代完成后再做总结
4. 总结后立即进入下一个迭代

这意味着：

- 不再在同一阶段频繁切去做控制台或平台外壳
- 先把加拿大地址主线完整做成
