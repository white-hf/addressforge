# AddressForge Phase 22R-2 执行总结

## Governed Runtime Bundle 与真实候选闭环

## 文档信息

- 日期：2026-07-30
- Phase / Iteration：22R-2
- 状态：Completed
- 生产数据：只读使用现有 Human Gold
- 新候选：model ID 51
- 发布操作：未晋升、未 reload、未 rollback

## 1. 需求

22R-1 建立了 manifest 完整性和 SHA256 门禁，但 Evaluator、Replay 等入口仍各自拼装 manifest，并可能静默进入 legacy/heuristic fallback。

本轮要求：

1. 建立共享 Runtime Bundle Loader
2. 区分 `governed` 与 `compatibility` 模式
3. Evaluator、Replay、Shadow 对指定版本使用 governed 模式
4. Active 与 Candidate 使用独立服务实例
5. Governed runtime 禁止本地 `decision_policy.json` 覆盖
6. 用真实训练和评估证明合同能穿过完整生命周期

## 2. 技术方法

- 新增共享 `runtime_bundle` 服务
- Governed 模式加载前校验 schema、身份、组件、文件和 SHA256
- 加载后校验 Decision、BuildingType、Reranker 均真实载入且来源为 manifest
- Compatibility 模式保留旧行为，但输出 contract issues 和 fallback identity
- Evaluator、Replay、Shadow 统一使用 governed loader
- AddressPlatformService 新增 `allow_local_policy_override=False`，保护 governed policy 不可变
- Trainer 将 schema、bundle ID、hash algorithm 同步写入 registry metrics，防止 Evaluation 更新 artifact_path 后合同丢失

## 3. 真实验证

### 3.1 旧模型入口一致性

ID 1、43、50 在 governed 模式下均被阻塞。

Replay 和 Evaluator 对 ID 50 返回相同结果：

- `reason = runtime_manifest_invalid`
- 缺 manifest schema
- 缺 bundle ID
- 缺四个 SHA256

ID 1 在 compatibility 模式下明确报告：

- Decision：`legacy_path`
- Reranker：`legacy_path`
- BuildingType：`fallback`

### 3.2 新合同候选

使用 1,740 个 distinct Human Gold 训练：

- training run ID：4694
- registry model ID：51
- model：`canada_candidate`
- version：`v_phase22r_contract_20260730_2217`
- status：训练后 `trained`
- is_default：0

训练后 governed validation：

- contract：通过
- SHA256：全部匹配
- Decision：manifest / non-legacy
- BuildingType：manifest / loaded
- Reranker：manifest / loaded
- runtime load issues：0

### 3.3 Governed 真实评估

- evaluation run ID：4698
- Gold：1,748
- Replay：为隔离合同验证暂时跳过

评估完成后：

- registry status：`evaluated`
- is_default：0
- artifact_path 更新为 eval artifact
- governed contract：仍通过
- runtime load issues：0

## 4. 指标比较

| 指标 | ID 43 最新旧评估 | ID 51 合同候选 | Delta |
|---|---:|---:|---:|
| Decision F1 | 0.9416 | 0.9031 | -0.0385 |
| Building Type F1 | 0.8700 | 0.8689 | -0.0011 |
| Unit F1 | 0.8392 | 0.8369 | -0.0023 |
| Unit Precision | 0.9325 | 0.9300 | -0.0025 |
| Unit Recall | 0.7628 | 0.7607 | -0.0021 |
| Commercial F1 | 0.3010 | 0.2886 | -0.0124 |

ID 51 的作用是验证 runtime contract，不是质量晋升。由于所有核心指标均未优于 ID 43，且缺 Replay/Shadow 证据，本候选不应晋升。

## 5. 测试

- Python compile：通过
- Runtime Manifest / Bundle / Registry / Replay / Evaluator / Trainer 目标测试：31 passed
- 双实例隔离、合同前阻塞、加载后阻塞、compatibility 证据、policy 不覆盖均有测试

## 6. 新发现

训练 run 约耗时 15 分钟。主要瓶颈不是 CatBoost，而是四类派生权重对同一批 Gold 重复执行完整解析，并在样本循环中反复初始化服务和加载模型。

这证明训练闭环存在显著重复计算，但不改变本轮合同完成结论。

## 7. 残余与下一轮

自动进入 22R-3：

1. API 启动时，合同有效模型使用 governed bundle
2. 当前合同无效活动模型保持显式 compatibility，避免在线行为突变
3. Reload 对无效合同 fail-closed，不再重建 fallback 服务
4. Worker reload 使用同一 governed loader
5. Runtime status 输出 registry identity、contract 状态、实际 artifact source
