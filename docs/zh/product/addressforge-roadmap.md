# AddressForge 开源平台路线图

> 中文：开源自部署地址智能平台的实施路线图。

> English: Implementation roadmap for the open-source, self-hosted address platform.

# Address Library AddressForge Open Source Platform Roadmap

## 1. 路线图目的

这份路线图回答的是：  
**怎样把当前系统演进成一个可开源、自部署、可训练、可对外提供 API 的标准平台。**

它不是再做一个局部功能，而是把系统整理成：

- 入口清晰
- 架构清晰
- 模型清晰
- 数据清晰
- API 清晰
- 可复用、可修改、可部署

## 2. 路线图原则

1. **先固化加拿大 / 北美默认模型**
   - 开源系统必须开箱可用
   - 默认能力先服务当前最成熟的加拿大 / 北美场景

2. **先标准化，再开放**
   - 先把内部数据层、训练层、API 层标准化
   - 再开放给其他开发者改造

3. **先有平台骨架，再扩展国家/地区**
   - 平台骨架必须先完整
   - 其他国家 / 地区只是替换配置、参考源、词典和模型

4. **先离线，再在线**
   - 先把清洗、训练、评估跑稳
   - 再暴露稳定 API

5. **先可用，再可改**
   - 先让别人可以直接用
   - 再让别人容易改造成自己的系统

## 3. Phase 0: Platform Foundation

### Goal

把系统从“内部清洗项目”整理成“开源平台骨架”。

### Deliverables

- 默认 Canada / North America 模型入口
- workspace / project 配置层
- API 服务骨架
- 控制台控制骨架
- 模型版本注册骨架
- 数据层命名和目录规范

### Exit Criteria

- 系统可以明确区分 platform / workspace / model / dataset
- 代码结构适合别人 fork 后改造

## 4. Phase 1: Default Canada Model Packaging

### Goal

把现有加拿大能力整理成默认模型包。

### Deliverables

- Canada parser profile
- Canada reference profile
- Canada cleaning pipeline profile
- Canada evaluation set
- Canada gold set / human gold snapshot

### Exit Criteria

- 默认部署后能直接处理加拿大 / 北美地址
- 模型和规则版本能被明确识别

## 5. Phase 2: Public Address APIs

### Goal

把地址能力正式对外输出成 API。

### Deliverables

- parse API
- normalize API
- validate API
- explain API
- model info API

### Exit Criteria

- 用户可以用 HTTP 调用地址解析能力
- API 输出结构化结果
- API 结果可追踪到模型和 reference 版本

## 6. Phase 3: Self-Hosted Training Workflow

### Goal

让别人可以在自己的部署实例上训练自己的模型。

### Deliverables

- sample export
- gold split
- model training
- evaluation
- shadow deployment
- model publish / activate

### Exit Criteria

- 用户可以在本地数据集上完成完整训练闭环
- 用户可以选择默认加拿大模型或自训模型

## 7. Phase 4: Adaptation Hooks for Other Regions

### Goal

让其他开发者容易改造成他们自己的国家 / 区域系统。

### Deliverables

- reference source adapter
- parser profile adapter
- normalization dictionary adapter
- locale/country config
- gold set adapter

### Exit Criteria

- 用户能够换掉加拿大 profile，接入自己的区域知识

## 8. Phase 5: Console / Job / Continuous Mode

### Goal

把系统运行方式标准化成控制台驱动的持续平台。

### Deliverables

- job manager
- ingestion control
- continuous mode
- training / freezing jobs
- report jobs

### Exit Criteria

- 控制台可以控制系统状态
- 后台 worker 可以持续执行
- 不依赖人工脚本操作

## 9. Phase 6: Documentation and Reference Project

### Goal

把系统做成一个可学习、可参考、可修改的开源项目。

### Deliverables

- English docs
- Chinese docs
- architecture docs
- API docs
- deployment guide
- training guide

### Exit Criteria

- 开发者看文档就能部署、训练、接 API
- 文档和代码口径一致

## 10. 当前状态

当前系统已经具备：

- 加拿大历史数据清洗主链路
- building / unit 双层模型
- ML / LLM 学习链路
- 控制台和持续模式

接下来要做的是把这些能力**平台化**：

- 从“项目内部系统”变成“开源标准平台”

## 11. Ingestion Service 里程碑

后续路线里，Ingestion Service 的目标是：

- 支持 API Pull
- 支持 Database Direct Import
- 支持私有源配置不入 git
- 和后台清洗流水线解耦

这意味着：

- 第三方可以把自己的数据留在自己的系统里
- AddressForge 只负责接入和清洗
- 后续训练、评估、API 输出都围绕同一套私有数据闭环运行
