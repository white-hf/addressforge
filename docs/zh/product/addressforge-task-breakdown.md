# AddressForge 开源平台任务拆分

> 中文：开源自部署地址智能平台的任务拆分。

> English: Task breakdown for the open-source, self-hosted address platform.

# Address Library AddressForge Open Source Platform Task Breakdown

## 1. 任务目的

把 AddressForge 拆成可以执行、可以验收、可以交付的工作项。

## 2. 工作流

### 2.1 平台骨架

任务：

- 定义 platform / workspace / model / dataset 的目录结构
- 统一配置读取
- 统一模型版本登记
- 统一 job 状态记录

验收标准：

- fork 后可以直接看懂系统结构
- 不会把内部清洗系统和对外 API 混成一团

### 2.2 默认加拿大模型

任务：

- 打包现有加拿大 parser / reference / cleaning 配置
- 固化默认模型版本
- 固化默认 gold / eval 集

验收标准：

- 默认部署可直接用于加拿大 / 北美地址

### 2.3 在线 API

任务：

- parse API
- normalize API
- validate API
- explain API
- model info API

验收标准：

- 任何开发者都可以直接调用
- 输出结构化、可追踪、可版本化

### 2.4 离线训练

任务：

- 样本导出
- gold 生成
- train/eval/test 切分
- 模型训练
- 评估和影子运行

验收标准：

- 可以在本地数据上完成训练到发布的闭环

### 2.5 区域适配

任务：

- parser 配置适配
- reference 配置适配
- 词典适配
- gold set 适配

验收标准：

- 别人可以把系统改成自己的国家 / 地区版本

### 2.6 控制台与持续运行

任务：

- 启动 / 暂停增量接入
- 启动 / 暂停持续模式
- 触发一次增量清洗
- 看 job 状态和最近结果
- 触发训练 / 冻结 / 报表

验收标准：

- 操作员无需脚本即可完成日常操作

## 3. 任务依赖

推荐顺序：

1. 平台骨架
2. 默认加拿大模型
3. 在线 API
4. 离线训练
5. 区域适配
6. 控制台和持续运行

## 4. DoD

任务完成的标准：

- 代码可运行
- 文档同步
- 输出可追踪
- 版本可冻结
- 可以回滚

## 5. Ingestion 任务拆分

Ingestion 子任务拆成两条可独立实现的路径：

1. **API Pull**
   - 配置私有 API 地址
   - 按 cursor / batch 拉取新增数据
   - 写入平台 raw 表

2. **Database Direct Import**
   - 配置第三方数据库连接
   - 从对方控制的源表读取新增记录
   - 写入平台 raw 表

验收标准：

- 不需要把第三方私有数据提交到 git
- 第三方可以自行选择 API 或数据库直导
- 后续清洗流水线可以直接消费 raw 表数据
