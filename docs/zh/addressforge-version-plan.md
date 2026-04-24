# AddressForge 开源平台版本计划

> 中文：开源自部署地址智能平台的版本计划。

> English: Version plan for the open-source, self-hosted address platform.

# Address Library AddressForge Open Source Platform Version Plan

## 1. 版本目标

把当前系统推进成一个标准开源平台：

- 默认加拿大 / 北美可用
- 开源可部署
- 可接入别人的数据
- 可训练别人的模型
- 可提供别人的 API

## 2. 版本原则

1. 先平台化，再区域扩展
2. 先默认加拿大模型，再开放给其他区域改造
3. 先离线训练闭环，再在线 API
4. 先可运行，再可扩展
5. 先参考实现，再优化体验

## 3. 版本地图

### AddressForge.0 Platform Skeleton

- platform / workspace / model / dataset 结构
- job 管理
- 统一配置
- 统一版本记录

### AddressForge.1 Default Canada Model

- 默认加拿大解析模型
- 默认 reference profile
- 默认清洗和评估配置

### AddressForge.2 Online API Layer

- parse / normalize / validate / explain API
- model info API
- 结构化输出

### AddressForge.3 Self-Hosted Training Loop

- sample export
- gold split
- training
- evaluation
- shadow deployment
- model activation

### AddressForge.4 Regional Adaptation Hooks

- parser adapter
- reference adapter
- dictionary adapter
- gold adapter

### AddressForge.5 Console and Continuous Operations

- 增量接入控制
- 持续模式
- 训练 / 冻结 / 报表按钮

### AddressForge.6 Documentation and Examples

- 英文文档
- 中文文档
- 快速开始
- API 示例
- 自定义国家 / 地区示例

## 4. Release Policy

- 每个版本都必须可自部署
- 每个版本都必须可回滚
- 每个版本都必须有文档
- 每个版本都必须有最小示例

## 5. What Should Be Used Today

今天默认可用的是：

- 加拿大 / 北美默认模型
- 当前已有的清洗与学习能力
- 控制台和持续模式

但最终目标不是只用内部系统，而是让它成为一个开源平台骨架。

## 6. Ingestion Version Focus

Ingestion 的第一阶段版本目标是：

- 支持 API Pull
- 支持 Database Direct Import
- 不把第三方私有数据写进 git
- 让 raw 数据进入统一清洗流水线

这个阶段先不追求全球化，也不追求复杂联邦模式，只把“可接入、可清洗、可训练”打通。
