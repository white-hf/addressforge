# AddressForge 开源平台设计文档

> 中文：开源、自部署、可训练、可对外提供地址解析 API 的平台设计说明。

> English: Design for an open-source, self-hosted, trainable address platform with public APIs.

# Address Library AddressForge Open Source Platform Design

## 1. 设计目标

AddressForge 的目标不是继续把内部清洗系统做得更强一点，而是把它升级成一个**开源标准系统**：

- 默认附带加拿大 / 北美模型
- 可以在本地或私有服务器自部署
- 可以接入别人的原始地址数据
- 可以训练别人自己的模型
- 可以对外提供地址解析 API
- 可以作为“参考实现”让别人改造成自己的国家 / 地区地址系统

一句话：

> AddressForge 是一个“开源地址智能平台参考实现”，不是 SaaS，也不是多租户托管服务。

## 2. 设计原则

1. **Canada / North America first**
   - 默认能力先做好加拿大 / 北美
   - 再让其他开发者按自己的场景改造

2. **Open source and self-hosted**
   - 代码可下载
   - 模型可替换
   - 数据可自持
   - 不依赖中央云服务

3. **Online API + Offline production separated**
   - 在线 API 负责解析、标准化、校验、建议
   - 离线流水线负责清洗、训练、评估、冻结

4. **Control console as control plane**
   - 控制台负责触发、暂停、观测
   - 后台 worker 负责真实执行

5. **ML / LLM as primary enhancement layers**
   - 规则提供底线
   - ML 提供主决策增强
   - LLM 处理弱标注、解释和部分 review 替代

## 3. 总体架构

AddressForge 建议拆成 6 个层次：

### 3.1 Data Layer

保存所有原始和结果数据：

- raw facts
- normalization results
- parser candidates
- canonical building / unit entities
- validation results
- user facts
- external references
- gold labels
- model runs
- API usage / job records

### 3.2 Cleaning Layer

负责把原始地址变成标准地址：

- normalize
- parse
- publish canonical building / unit
- validate
- build user facts
- generate review tasks

### 3.3 Learning Layer

负责从历史和人工反馈里学习：

- reranker
- unit span detector
- building clustering
- validation triage
- confidence fusion
- active learning
- LLM weak labeling

### 3.4 API Serving Layer

对外提供稳定接口：

- parse
- normalize
- validate
- enrich
- suggest
- explain
- model info / version info

### 3.5 Control Console Layer

提供人机控制界面：

- 开启 / 关闭持续接入
- 触发一次增量清洗
- 触发训练 / 评估 / 冻结
- 查看 job 状态
- 查看运行报告

### 3.6 Workspace / Project Layer

每个用户自部署后，都有自己的 workspace：

- 自己的数据
- 自己的模型
- 自己的 reference
- 自己的 gold set
- 自己的 API 配置

这不是 SaaS 的“租户”，而是本地部署后的项目工作区。

## 4. 核心对象设计

### 4.1 Workspace

workspace 是系统最重要的边界单位。

一个 workspace 包含：

- 数据源配置
- reference 源配置
- 模型配置
- gold 版本
- 评测配置
- API 配置

### 4.2 Model Profile

系统默认提供 Canada profile。

用户可以在自己的 workspace 里定义：

- `base_canada`
- `north_america_custom`
- `user_custom_country`

Profile 决定：

- 用哪些 parser
- 用哪些 reference
- 用哪些规则字典
- 用哪些训练样本
- 用哪些评测集

### 4.3 Address Decision

每条地址决策都要可追踪：

- raw input
- parser outputs
- reference hits
- model scores
- final canonical result
- confidence / reason

## 5. 在线 API 设计

AddressForge 需要提供最少这些接口：

### 5.1 Parse API

输入原始地址，输出结构化结果。

### 5.2 Normalize API

输入原始地址，输出标准化文本和 token 结果。

### 5.3 Validate API

输入地址 + 参考信息，输出：

- accept / enrich / review / reject
- confidence
- unit suggestion
- GPS conflict hint

### 5.4 Explain API

输入地址和系统决策，输出人能看懂的解释。

### 5.5 Model Info API

输出当前模型版本、参考源版本、规则版本。

## 6. 离线训练设计

离线训练应当独立于在线 API：

- 可以在没有网络的情况下训练
- 可以在本地数据集上重放
- 可以冻结 gold
- 可以生成 evaluation report
- 可以 shadow 到线上 API

训练流程：

1. 抽训练样本
2. 生成或确认 gold
3. 切分 train / eval / test
4. 训练模型
5. 评估模型
6. 影子运行
7. 通过控制台发布版本

## 7. 控制台设计

控制台是人和系统的接口。

必须支持：

- 启停增量接入
- 启停持续模式
- 一次性拉取并清洗
- 训练 / 评估 / 冻结
- 报表查看
- 模型版本切换

控制台不能直接承担长时间逻辑，它只能创建 job、展示状态、触发 worker。

## 8. 扩展到其他国家 / 区域的方式

AddressForge 不做全球统一模型，但必须让其他开发者容易改造。

应当支持：

- 替换 parser 配置
- 替换 reference source
- 替换 normalization dictionary
- 替换 gold set
- 替换 model profile
- 替换 API 默认行为

也就是说，系统提供标准骨架，别人替换自己的国家知识。

## 9. 版本边界

AddressForge 的边界是：

- 平台化
- 开源自部署
- 默认加拿大 / 北美
- 支持对外 API
- 支持他人自定义国家 / 区域

AddressForge 不追求：

- 全球一把梭
- 多租户 SaaS
- 中央统一运营

## 10. 设计目标总结

AddressForge 的最终形态应该是：

- 一个标准的开源地址智能平台
- 一个可自部署的加拿大 / 北美默认系统
- 一个可以被他人拿去改造成自己国家 / 区域系统的参考实现
- 一个同时具备离线清洗、在线 API、训练学习、控制台的完整系统

## 11. Ingestion Architecture

Ingestion Service 是平台的第一层输入，不直接依赖仓库内置私有地址样本。

支持两种接入方式：

1. **API Pull**
   - 第三方提供私有 API
   - AddressForge 按 cursor / batch 拉取新增原始数据
   - 适合对方已有服务接口

2. **Database Direct Import**
   - 第三方把原始数据导入自己的数据库表
   - AddressForge 通过配置连接到该表
   - 适合对方更偏数据仓库 / ETL 的场景

设计要求：

- 私有源数据不入 git
- 仓库只保留 schema、示例配置和代码
- ingestion 负责“拿原始数据”，后续清洗由后台流水线负责
