# AddressForge Phase 22R-1 执行总结

## Runtime Manifest 完整性与 SHA256 发布门禁

## 文档信息

- 日期：2026-07-30
- Phase：22R
- Iteration：22R-1
- 状态：Completed
- 变更类型：Runtime Contract / Training Artifact / Release Gate
- 生产数据操作：仅只读查询
- 生产模型操作：未训练、未晋升、未 reload、未 rollback

## 1. 本轮需求

### 问题

当前发布门禁只检查 manifest 中已经出现的路径。某个必需组件完全缺失时，检查列表可能为空或不完整，候选模型仍可能越过物理产物一致性检查。

同时，现有 manifest 没有文件哈希，无法证明训练、评估和发布消费的是同一份物理文件。

### 目标

建立第一个可执行的 runtime manifest 合同切片：

1. Decision、Reranker、BuildingType 都是必需组件
2. Decision 必须同时具有 model 和 metadata sidecar
3. 新训练产物绑定 SHA256
4. Manifest 身份必须与 registry 身份一致
5. 发布门禁在任何合同问题上 fail-closed
6. 不改变当前在线推理输出

## 2. 开发前生产证据

2026-07-30 对 workspace `default` 进行只读检查：

| 对象 | 当前事实 | 主要问题 |
|---|---|---|
| Workspace | `default_model_id = 1` | registry 中没有 `is_default = 1` |
| Model ID 1 | `canada_default_v1` | 版本化 Decision `.pkl/.json` 缺失，Reranker/BuildingType 未绑定 |
| Model ID 43 | `v1` | 最新评估，但 runtime binding 和三类 artifact 均缺失 |
| Model ID 50 | `v20260517_week4` | 三类物理产物存在，但 manifest 无 schema、bundle ID 和 SHA256 |

ID 1 登记的以下文件不存在：

- `runtime/models/default_canada_default_catboost_canada_default_v1.pkl`
- `runtime/models/default_canada_default_catboost_canada_default_v1.json`

运行时仍存在可变通用文件：

- `runtime/models/decision_catboost_v1.cbm`
- `runtime/models/decision_catboost_v1.pkl`
- `runtime/models/decision_catboost_v1.json`
- `runtime/models/reranker_catboost_v1.cbm`
- `runtime/models/building_type_catboost_v1.cbm`

因此旧指标不能严格证明对应某个不可变 runtime bundle。

## 3. 技术方法

### 3.1 集中式 Manifest 解析

新增统一解析逻辑，按以下优先级合并运行时事实：

1. registry `metrics_json`
2. evaluation artifact 内嵌 `metrics_json`
3. artifact 根对象

解析失败不再被吞掉，而是进入结构化 issue。

### 3.2 明确的必需组件合同

必需物理文件：

| 组件 | 必需文件 |
|---|---|
| DecisionModel | `model_path`、`metadata_path` |
| Reranker | `model_path` |
| BuildingTypeModel | `model_path` |

Legacy path 不计入正式合同完整性。

### 3.3 SHA256 绑定

新训练 manifest 增加：

- `manifest_schema_version = 1.0`
- `runtime_bundle_id`
- `artifact_hash_algorithm = sha256`
- 每个必需物理文件的 SHA256

文件被替换、损坏或路径指向不同内容时，发布门禁会阻塞。

### 3.4 Fail-closed Release Gate

发布门禁现在阻塞：

- manifest schema 缺失或错误
- registry/manifest 身份不一致
- runtime binding 不完整
- 必需组件缺失
- 必需路径缺失
- 物理文件缺失
- SHA256 缺失
- SHA256 不一致

失败结果同时返回结构化 `runtime_manifest_validation`。

## 4. 实现范围

- 新增 `src/addressforge/models/runtime_manifest.py`
- 更新 Trainer，使新产物写入 runtime contract 和 SHA256
- 更新 Registry Release Gate，使用集中式完整性校验
- 新增 manifest、hash、identity 和 nested-evaluation 解析测试
- 增加发布门禁正向与反向测试

本轮没有：

- 改变 API 推理策略
- 改变 Decision/BuildingType/Unit 模型行为
- 修改生产 registry
- 补写或伪造旧模型 SHA256
- 晋升任何模型

## 5. 验证结果

### 5.1 单元与集成测试

- Python compile：通过
- Runtime/Registry/Trainer/Evaluator/Replay 相关测试：`25 passed`
- 正向验证：完整、hash-bound manifest 可以通过模拟 Release Gate
- 反向验证：
  - 必需组件缺失会阻塞
  - artifact 被修改后 hash mismatch 会阻塞
  - registry/manifest identity mismatch 会阻塞
  - evaluation nested metrics 可以恢复完整合同

### 5.2 全测试发现

执行全量 discovery：

- 运行：120
- skipped：2
- failure：1
- errors：17

失败主要来自：

- 沙箱内无法访问本机 MySQL/API
- 测试尝试联网加载 embedding model
- 现有测试桩接口与当前实现不一致
- 旧 Reranker 测试仍调用已不存在的方法

本轮相关的 25 个目标测试全部通过；全测试集目前仍不是可靠的单命令绿色门禁，需要后续单独治理。

### 5.3 真实 Registry 验证

新校验器对生产 registry 只读运行：

| Model ID | Validation | Issue 数量 | 主要 issue |
|---:|---|---:|---|
| 1 | Failed | 7 | 文件缺失、组件缺失、无 schema/hash |
| 43 | Failed | 7 | runtime binding/三类组件缺失 |
| 50 | Failed | 7 | 无 schema、bundle ID、4 个 SHA256 |

结果与开发前人工审计一致。

## 6. 前后对比

| 能力 | 开发前 | 本轮完成后 |
|---|---|---|
| 必需组件 | 仅检查出现的路径 | 三类组件明确必需 |
| Decision sidecar | 局部检查 | 正式合同必需 |
| 文件身份 | 路径存在即可 | 路径 + SHA256 |
| Manifest 身份 | 分散字段 | schema + bundle ID + registry 对齐 |
| 失败输出 | 单一字符串 | 字符串 + 结构化 issues |
| 新训练产物 | 无 hash contract | 自动绑定 SHA256 |
| 在线推理行为 | 当前 fallback 行为 | 未改变 |

## 7. 残余风险

1. Evaluator、Replay、API、Worker 仍各自实现 manifest 合并和 fallback
2. 当前生产 registry 中没有一个模型满足新合同
3. 旧 manifest 不能静默补写哈希，否则会把当前文件误认成历史评估文件
4. Feature schema version 尚未成为所有组件的正式合同字段
5. `decision_policy.json` 仍可能覆盖 manifest 中的不可变 policy
6. Registry 的 active/default 状态不一致属于 Phase 23R，尚未修改

## 8. 下一轮

自动进入 Phase 22R-2：

1. 让 Evaluator 与 Replay 使用同一个 manifest resolver
2. 在指定 model version 时禁止静默 legacy fallback
3. 输出 Active/Candidate 独立 runtime identity
4. 增加 compatibility mode 与 strict governed mode
5. 使用真实 ID 1、43、50 验证 strict mode 的阻塞行为
