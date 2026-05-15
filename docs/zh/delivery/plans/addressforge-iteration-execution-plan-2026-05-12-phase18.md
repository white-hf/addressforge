# AddressForge 迭代执行计划 - 2026-05-12 (Phase 18: Rollout, Gate, And Operations Completion)

## 文档信息
- 文档类型：Execution Plan / Production Readiness Plan
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 高级工程
- 状态：Planned
- 目标：完成下一代 ML 系统的生产上线闭环

## 1. 当前背景与问题定义
即使模型训练得更好，如果没有：
- 正确激活
- 正确加载
- 正确 gate
- 正确 rollback

那么下一代 ML 仍然不能算真正完成。

## 2. 当期总目标
1. 打通模型生效链
2. 建立 Release Gate 2.0
3. 建立 rollback 和运营闭环
4. 完成下一代 ML 系统的生产可用化

## 3. 具体需求

### 需求 18-1：模型生效链闭环
交付要求：
- 训练完成后的 artifact 能被 worker/API 正确加载
- cleaning/validation 运行时能证明自己使用了新模型

### 需求 18-2：Release Gate 2.0
交付要求：
- gate 能同时评估：
  - heuristic baseline
  - supervised model delta
  - shadow disagreement
  - rollback risk

### 需求 18-3：Safe rollout / rollback
交付要求：
- 明确：
  - shadow
  - assist
  - guarded override
  - default on
  的切换条件
- 建立快速回滚流程

### 需求 18-4：持续学习运营闭环
交付要求：
- minority-label seeding
- structured correction
- disagreement review
- feature schema evolution
能够进入长期生产循环

### 需求 18-5：脏地址运营诊断列表
交付要求：
- 控制台可直接查看新导入数据中的脏地址
- 支持按 `source_name` 和 `batch_id` 过滤
- 重点暴露：
  - `missing_unit`
  - `gps_conflict`
  - `reference_gap`
  - `parser_disagreement`
  - `manual_review`
- 每条记录都展示系统建议纠正后的结构化字段，便于人工复核与回流训练

## 4. 技术方法
- **Model activation contract**
  - 统一训练后激活、worker reload、API reload 行为。
  - `/reload` 前必须清理 registry TTL 缓存，避免继续读取旧 active/workspace 视图。
- **Gate by layer**
  - 对 Decision / Reranker / BuildingType 分层看 gate。
  - `DecisionModel` consistency gate 不仅检查 `model_path`，还必须检查 `metadata_path` sidecar。
- **Safe rollout stages**
  - `shadow -> assist -> guarded_override -> default_on`
- **Operational feedback loop**
  - 将生产 disagreement 与 review 再回流训练。
- **Dirty address diagnostics**
  - 将 `validation_json` / `reference_json` / `parser_json` 中已有的诊断结构产品化为控制台专门列表。
  - 优先支持按 `batch_id` 查看 API 刚导入并清洗完成的一批新数据。

## 5. 预期收益
- 让下一代 ML 从“工程原型”变成“生产能力”
- 让模型升级具备可控、可回滚、可审计特性

## 6. 交付物
- Release Gate 2.0
- model activation contract
- rollback playbook
- next-gen ML operations guide

## 7. 完成标准
1. supervised model layer 可稳定上线
2. runtime 真正吃到新模型
3. gate / rollback / feedback 构成完整闭环
4. 下一代 ML 系统达到生产可用状态

## 8. 最终判定
Phase 18 完成时，可宣布：

**AddressForge 下一代 ML 系统 100% 完成。**
