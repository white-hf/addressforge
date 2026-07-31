# AddressForge Phase 23R 执行总结

## Registry、Release Gate、Reload 与 Rollback 收口

## 文档信息

- 日期：2026-07-30
- 状态：Implementation completed / operational rehearsal pending
- 生产晋升：未执行
- 生产 rollback：未执行
- Human Gold：未修改

## 1. 真实问题

本轮开始前的真实 Registry 证据：

- `workspace_registry.default_model_id = 1`
- `model_registry` 没有 `is_default = 1`
- 活动模型被 Evaluation 写回为 `evaluated`
- `get_active_model` 在没有 default flag 时会选择“最近更新模型”
- API/Worker reload 和多个 GET 接口会通过 bootstrap 隐式改写 Registry
- 旧 rollback 先 deprecate 当前模型，再单独 promote 旧模型，失败时可能留下无 active 状态

## 2. 实现方法

### 单一事实源

- 活动模型优先且唯一由 `workspace_registry.default_model_id` 解析
- 旧 workspace 仅允许唯一 `is_default = 1` 的显式 compatibility bridge
- 禁止回退到“最近更新模型”
- runtime identity 报告 pointer、default flag 和 lifecycle status 是否一致

### 生命周期保护

- 普通 Training / Evaluation / Shadow 注册只能推进 lifecycle
- `promoted`、`deprecated` 不会被重新写成 `trained` 或 `evaluated`
- Evaluation / Shadow 不再写 `is_default = 0`

### 只读接口

- `/api/v1/model`
- `/api/v1/models`
- `/api/v1/workspaces`

以上 GET 路径不再执行 bootstrap 或隐式写 Registry。

### 结构化 Release Gate

新增完整 readiness report，一次输出：

- 绝对 benchmark 安全下限
- Candidate vs Active 相对门禁
- Replay 成功、失败和回归风险
- Shadow / Assist readiness
- Runtime manifest、物理文件、sidecar 和 SHA256

`dry_run` 不打开写事务。

### 事务化 Promote / Rollback

- Promote 在事务中锁定 workspace
- 支持 `expected_active_model_id` compare-and-swap
- CAS 失败不修改任何 default flag
- Rollback 必须指向明确 model ID 或明确解析出的上一不可变版本
- Rollback target 必须通过 runtime contract
- 当前模型降级、target 激活、workspace pointer 更新在同一事务完成

## 3. 真实候选 Readiness

通过固定命令读取 ID 51 的真实 training + evaluation artifact，未连接数据库、未修改文件：

```text
status = blocked
absolute benchmark floors = passed
runtime manifest / SHA256 = passed
```

三个实际 blocker：

1. Candidate vs Active：`reject_rate` 未通过相对门禁
2. Replay：`processed_samples = 0`，状态为 failed/skipped
3. Assist readiness：
   - `assist_trial_not_worse_than_shadow = false`
   - `eligible_sample_count_sufficient = false`
   - `assist_gold_match_rate_sufficient = false`

Shadow 本身：

- `shadow_advantage = 0.0604`
- `disagreement_rate = 0.0644`
- 通过当前 Shadow 数值门禁

## 4. Artifact 持久化缺口

现有 ID 51 evaluation JSON 单独读取时缺少训练期 runtime contract；Registry metrics 合并视图包含合同，因此此前 governed loader 能通过。

已修复 Evaluator：

- 在写 evaluation artifact 前合并已有 immutable runtime contract
- 后续 evaluation JSON 自身包含 schema、bundle ID、三组件、sidecar 和 hashes
- Registry 与 evaluation artifact 不再依赖读取时补齐

现有 ID 51 文件未被回填或覆盖。

## 5. 验证

- compile：通过
- Registry / Release / Rollback / Runtime / Replay / Evaluator 目标测试：44 passed
- 固定 artifact readiness 命令：成功输出结构化 blocked 结论
- 未使用任意 `python -c`
- 未执行生产 Registry 写入

## 6. 阶段结论

Phase 23R 的实现已完成，但最终“真实 promote → reload → rollback 演练”不能执行，因为 ID 51 未通过 Release Gate。绕过 Gate 演练会违反本项目的证据治理原则。

该验收项保持 pending，待 Phase 24-27 形成合格候选后执行。当前不需要停工，自动进入 Phase 24R，优先补齐 Replay 逐条证据和真实 processed sample。
