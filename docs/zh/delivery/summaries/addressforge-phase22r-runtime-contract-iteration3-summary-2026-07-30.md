# AddressForge Phase 22R-3 执行总结

## API / Worker 运行时合同收口

## 文档信息

- 日期：2026-07-30
- Phase / Iteration：22R-3
- 状态：Completed
- 生产模型变更：无
- Registry 变更：无
- Human Gold 变更：无

## 1. 需求

22R-2 已使 Evaluator、Replay、Shadow 使用共享 Governed Runtime Bundle，但 API 启动、API reload 和 Worker reload 尚未完全遵循同一合同。

本轮要求：

1. API 对合同有效模型只加载 governed bundle
2. 当前活动模型合同无效时，启动保持显式 compatibility，避免生产行为突变
3. API reload 在合同无效时 fail-closed，并保留原内存服务
4. Worker reload 使用共享 governed loader
5. 运行状态同时报告 registry、contract 和实际 artifact source
6. 真实环境检查不使用任意内联 Python，改为固定、可审计入口

## 2. 技术方法

- API 启动先解析 active registry row，再构建独立 governed bundle
- governed 加载成功后不再读取兼容 manifest，也不接受本地 policy 覆盖
- 服务实例保存自身 workspace，reload 不再隐式使用全局 workspace
- reload 先完成合同与物理加载校验，再原子替换当前服务
- Worker reload 在刷新索引前验证完整 bundle；校验失败时索引保持不动
- 修正 ModelService artifact source：
  - manifest 描述符加载：`manifest`
  - 配置路径加载：`configured_path`
  - 旧 CBM 回退：`legacy_path`
- 新增 `scripts/inspect_runtime_state.py`，用于固定格式的只读启动身份和 reload 保持性检查

## 3. 真实运行证据

变更前已对当前 workspace 运行真实启动与 reload 检查：

- 当前活动模型合同无效
- API 启动进入显式 `compatibility`
- Decision 实际来自通用配置文件
- reload 返回 `runtime_manifest_invalid`
- reload 失败后原 Decision / Reranker 服务对象保持不变

该结果符合本轮保护目标：未改变当前在线选择，也未把 fallback 伪装成 governed runtime。

真实候选 ID 51 在 22R-2 已通过相同共享 loader 的完整合同、SHA256 和三组件加载校验，因此 API 对合同有效模型的行为由同一工厂和测试覆盖，而不是另一套拼装逻辑。

## 4. 自动化验证

- Python compile：通过
- Runtime / API reload / Worker reload / Registry Gate / Replay / Evaluator 目标测试：31 passed
- 覆盖场景：
  - governed startup
  - governed reload
  - invalid contract fail-closed
  - reload 失败保留当前服务
  - workspace 隔离
  - Worker 在索引 reload 前阻塞
  - configured path 与 manifest source 不混淆

## 5. 结论

Phase 22R 的 Runtime Bundle 消费路径已完成代码层收口：

- Training、Evaluator、Replay、Shadow、API、Worker 共享合同语义
- 正式路径禁止静默 fallback
- compatibility 被明确标识
- Active / Candidate 可使用独立实例
- runtime identity 可暴露实际来源

当前生产仍处于 compatibility，不是因为 API 继续容忍模糊合同，而是活动 registry 指向的旧模型本身没有完整版本化合同。该问题进入 Phase 23R，由活动模型单一事实源、状态一致性和安全迁移处理。

## 6. 下一轮

自动进入 Phase 23R-1：

1. 修复 Evaluation 覆盖活动模型发布状态的问题
2. 明确 `workspace_registry.default_model_id` 为活动选择入口
3. 校验 `is_default`、`status` 与 workspace pointer 的一致性
4. 增加事务化 activation 和结构化 readiness report
5. 不执行生产 promote，直到质量、Replay、Shadow 和人工门禁满足
