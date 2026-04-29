# AddressForge 模型训练与调优指南

> 这份文档回答三个问题：  
> 1. 如何训练自己的模型  
> 2. 如何调优地址解析准确率  
> 3. 如何通过控制台把训练、评估、冻结和发布串起来

## 1. 这份指南适合谁

这份指南适合已经能跑通 AddressForge 最小闭环的开发者。  
如果你还没有完成下面这几步，建议先看快速开始：

- 初始化数据库
- 导入样例或私有地址数据
- 跑通 API
- 生成一批训练样本

## 2. 训练的目标是什么

AddressForge 的训练不是“为了训练而训练”，而是为了让你的地址系统在自己的数据上越来越准。

常见目标包括：

- 提高 parser 候选排序准确率
- 提高 unit 识别准确率
- 提高 building / unit 分层准确率
- 降低 review rate
- 降低 GPS 冲突误判
- 降低 auto-enrich 错补率

每次训练、规则升级或清洗链路升级后，都应该用一套固定 benchmark 来判断是否值得发布。

推荐先阅读：

- [发布评测标准](./addressforge-release-benchmark.md)

## 3. 先弄清楚你要调什么

训练前先确认你要改善的对象。

### 3.1 解析器

如果问题是：

- `Apt 103`
- `Apart 101`
- `#207`
- `1-133 Main St`

经常识别不对，那优先调：

- parser 候选排序
- unit span 识别

### 3.2 校验层

如果问题是：

- 本来应该通过却被拒
- 应该补 unit 却没补
- 本来是公寓却判断成 house

那优先调：

- validation triage
- building clustering
- reference matching

### 3.3 融合层

如果你发现：

- parser 看起来都对，但最终决策不稳定
- reference 和历史数据冲突时决策不稳

那优先调：

- confidence fusion
- 阈值
- review 路由

## 4. 推荐的训练顺序

建议按下面顺序来，不要一上来就做复杂模型。

### 第 1 步：准备样本

先从你的清洗结果里导出训练样本。

建议优先覆盖这些桶：

- `building_cluster`
- `unit_span`
- `validation`
- `reference_review`

同时也要保留一些典型难样本：

- 多单元公寓
- 只有楼宇没有 unit
- 写字楼 / 商场 / 商业楼
- GPS 冲突
- parser disagreement

### 第 2 步：冻结 gold

在控制台里完成人工审核后，先把样本冻结成稳定版本。

推荐动作：

- 生成下一批
- 人工审核
- 完成本批并冻结

如果你已经有纯人工标签，再做：

- human-only freeze

### 第 3 步：切分 train / eval / test

不要只看一个训练集分数。

至少要有：

- train
- eval
- test

推荐原则：

- 不同 building 尽量不要泄漏到多个集合
- 同一用户的样本尽量不要同时进入 train 和 eval
- 不要只抽容易样本

### 第 4 步：训练 baseline

先训练最简单的 baseline。

目标不是追求最高分，而是确认：

- 输入特征是否正确
- 标签语义是否正确
- 评估流程是否正确

### 第 5 步：shadow 评估

训练后不要直接替换线上结果，先做 shadow。

Shadow 的作用是：

- 不影响线上
- 只记录模型输出
- 和规则结果对比
- 看模型是否真的更稳

### 第 6 步：控制台触发发布

当模型评估稳定后，再通过控制台切换默认模型版本。

这一步应该是控制台动作，不应该是开发者手工改代码。

## 5. 控制台在训练里的作用

控制台不是训练器本身，而是控制平面。

它应该负责：

- 生成训练批次
- 冻结 gold
- 触发训练 job
- 触发 evaluation job
- 触发 shadow job
- 查看 job 状态
- 切换模型版本
- 启动 / 暂停持续模式

控制台不应该：

- 直接承担长时间训练
- 把所有逻辑写在页面请求里
- 让用户通过脚本做日常操作

为了避免歧义，下面这些术语在本项目里含义固定：

- **控制台**：人操作的入口，只负责发起任务、查看状态、切换版本
- **清洗流水线**：真正做 normalize / parse / validate / publish 的后台任务
- **学习流水线**：真正做 freeze gold / train / shadow / evaluate / promote 的后台任务
- **Ingestion**：只负责把第三方原始数据接入系统，不做完整清洗决策

### 5.1 模型注册表

训练完成后，模型不会直接覆盖旧版本，而是先登记到模型注册表中。

模型注册表记录：

- workspace
- model_name / model_version
- 模型状态
- 训练数据版本
- 评估结果
- 默认模型指针

控制台通过注册表来：

- 查看当前默认模型
- 切换候选模型和默认模型
- 回滚到上一版本

## 6. 训练时建议调哪些参数

### 6.1 parser 候选排序

建议调：

- parser 权重
- 置信度阈值
- unit 加分 / 扣分
- postal code 加分

### 6.2 validation triage

建议调：

- `accept`
- `enrich`
- `review`
- `reject`

的边界阈值。

### 6.3 building / unit

建议调：

- `single_unit`
- `multi_unit`
- `unknown`

的判定阈值。

### 6.4 reference fusion

建议调：

- authoritative reference 的权重
- semi-authoritative reference 的权重
- weak reference 的权重
- GPS 冲突触发阈值

## 7. 如何判断训练真的变好了

不要只看训练集分数。

至少看下面这些：

- eval accuracy
- precision / recall / F1
- review rate
- auto-enrich accuracy
- GPS conflict rate
- building split / merge error
- unit precision / recall

如果你有 human gold set，还要单独看：

- human gold precision / recall
- human gold coverage

## 8. 一个推荐的实际闭环

如果你是第一次做训练，建议按这个节奏：

1. 导入少量私有数据
2. 跑一轮清洗
3. 在控制台里人工审一批难样本
4. 冻结 gold
5. 训练 baseline
6. 跑 shadow
7. 看报表
8. 调阈值
9. 再训练
10. 切换默认模型

## 9. 常见建议

- 先让系统在小数据上稳定，再扩到大数据
- 先做单一国家 / 区域，再做多区域
- 先训练一个简单 baseline，再上复杂模型
- 训练和评估要版本化
- 控制台操作要保留审计痕迹

## 10. 如果你要继续升级

当 baseline 稳定后，可以继续考虑：

- 更强的 reranker
- 更好的 unit span 模型
- 更稳的 building adjudication
- 更强的 confidence fusion
- LLM 辅助标注和 review 替代

## 11. 结论

训练与调优的核心不是“把模型训出来”，而是：

- 用控制台驱动整个流程
- 用 gold 保证标签质量
- 用 eval / shadow 验证效果
- 用版本号保证可回滚

AddressForge 的训练应该是一个可持续循环，而不是一次性脚本。
