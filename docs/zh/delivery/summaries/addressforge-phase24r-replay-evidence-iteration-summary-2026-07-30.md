# AddressForge Phase 24R 执行总结

## Replay 逐条证据持久化

## 文档信息

- 日期：2026-07-30
- 状态：Implementation completed / live migration and replay pending
- 模型行为变更：无
- 生产数据库迁移：未执行
- 生产 Replay：未执行

## 1. 真实问题

代码和 schema 核对发现：

- `historical_replay_result` 表已存在，但 Replay 从未写入
- 只在内存保留最多 50 条 mismatch
- failure 只增加计数，不保存 raw ID 和错误
- 返回值没有 `failures`
- Evaluator 用截断后的 mismatch list 长度作为总数
- 0 条成功处理时 `consistency_score = 1.0`
- 业务 readiness endpoint 使用比 Promote 更宽松的另一套 Gate

因此旧 Replay 即使显示 completed，也无法回答“哪一条变了、为什么失败、使用了什么 runtime”。

## 2. 技术方法

### Run-level evidence

`historical_replay_run` 增加：

- Candidate / Active model ID
- requested / processed / failure / disagreement count
- run status 和 error
- Candidate / Active runtime identity JSON
- completed timestamp

### Row-level evidence

`historical_replay_result` 对每条样本保存：

- current / candidate / active 三方字段和完整 JSON
- Candidate vs Active 差异
- Candidate vs Current 差异
- Active vs Current 差异
- processing status
- error text

成功和失败都作为证据写入。

### 原子持久化

- run summary 和全部 row evidence 在同一事务提交
- 重跑同一 run ID 使用 upsert
- mismatch 内存数组只作为 50 条预览
- 正式 mismatch 总数来自 `disagreement_count`
- failure 可单独查询

### Schema 前向迁移

- canonical schema 已更新
- `pipelines.schema` 增加幂等列和索引迁移
- 迁移不会由 Replay 隐式执行

### 单一 Readiness

业务 readiness endpoint 改为调用与 Promote 相同的完整 governed Gate，不再只检查三个指标。

## 3. 验证

目标测试：

- 48 passed
- 覆盖成功行、失败行、summary、runtime identity、schema migration、统一 readiness、Evaluator 总数

广泛测试：

- 148 total
- 1 failure、17 errors、2 skipped
- 失败集中于：
  - 需要本地 MySQL 或 8011 服务的集成 / 性能测试
  - sandbox 中无法下载 HuggingFace 模型
  - 旧 Reranker 测试调用已移除方法
  - DummyVectorEngine 测试桩未接受 latitude / longitude

因此本轮目标回归通过，但仓库全量测试基线尚未绿色，不能宣称全量回归通过。

## 4. 为什么没有运行生产 Replay

正式 Replay 要求 Active 和 Candidate 都使用 governed runtime。

当前：

- Candidate ID 51：合同有效
- Active ID 1：合同无效

允许 Active 静默 compatibility 会违反 Phase 22R 合同；直接 backfill Active 合同会改变生产运行路径，需要独立的安全迁移和行为等价证明。

此外生产 Replay 表尚未执行 Phase 24R schema 迁移。

因此本轮不绕过门禁，live migration 和真实 Replay 保持 pending。

## 5. 下一步

进入 Phase 25 前并行保留两个前置项：

1. 设计 Active ID 1 的只读合同等价报告和安全 backfill 方案
2. 在允许的维护窗口执行 Replay schema migration

Phase 25 将先检查 Gold 分布、冻结集与字段标签可信度，不依赖修改生产 active。
