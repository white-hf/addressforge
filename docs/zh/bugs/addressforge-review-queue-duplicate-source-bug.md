# AddressForge 审核队列按 task_type 重复入队导致同一地址被重复审核 Bug

## 问题类型
- 功能性缺陷
- 数据处理逻辑错误
- 人工审核效率损耗

## 问题摘要
当前系统在生成审核队列时，不是按“同一地址是否已经审核过”去重，而是按：

- `workspace_name`
- `source_name`
- `source_id`
- `task_type`

联合去重。

这会导致同一条地址如果在不同轮次中被赋予新的 `task_type`，即使已经人工审核过，也会再次进入审核队列，形成大量重复审核。

## 已确认现象
在 `default` workspace 中，当前队列和 gold 数据已出现明显重复：

- `active_learning_queue` 中同一 `source_id` 出现两次
- `gold_label` 中同一 `source_id` 也出现两次

重复样本包括但不限于：

- `68`
- `213`
- `216`
- `222`
- `223`
- `335`
- `425`
- `583`
- `584`
- `585`
- `600`
- `675`
- `676`
- `687`
- `746`

## 重复的直接机制
这些重复并不是完全相同的任务副本，而是：

- 第一轮作为 `review`
- 第二轮又作为 `commercial` / `single_unit` / `building_type`

再次入队。

例如：

- `213`: `review` -> `commercial`
- `287`: `review` -> `single_unit`
- `670`: `review` -> `single_unit`

这说明系统当前把“同一地址的新 task_type”视为一条新审核任务。

## 根因分析
### 1. 队列表唯一键按 `task_type` 去重
`active_learning_queue` 的唯一键是：

- `(workspace_name, source_name, source_id, task_type)`

见 [addressforge_schema.sql](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/sql/addressforge_schema.sql:158)

这意味着：

- 同一地址 + 同一 task_type 才会命中 `ON DUPLICATE KEY UPDATE`
- 同一地址 + 不同 task_type 会插入新行

### 2. gold 也按 `task_type` 单独存储
`gold_label` 的唯一键也是：

- `(workspace_name, source_name, source_id, task_type)`

见 [addressforge_schema.sql](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/sql/addressforge_schema.sql:111)

因此同一地址如果重复审核且 task_type 改变，会同时造成：

- 审核队列重复
- gold 标签重复

### 3. 入队逻辑没有排除“已有人审 gold 的 source_id”
当前几个主要入队函数：

- `seed_active_learning_queue(...)`
- `seed_active_learning_from_errors(...)`
- `seed_unit_commercial_review_queue(...)`

都会直接尝试入队，但没有先按 `source_id` 排除：

- 已经存在 accepted human gold 的地址
- 已经存在历史审核队列记录的地址

相关代码见：
- [gold.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/gold.py:310)
- [gold.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/gold.py:421)
- [gold.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/gold.py:494)

## 对业务和模型的影响
### 对人工审核
- 同一地址被反复审
- 审核员会误以为是新样本
- 实际上人工时间被浪费在重复确认上

### 对 gold 数据
- 同一地址可能有多条不同 task_type 的 human gold
- gold 规模看起来增长，但真实“新地址覆盖”增长并不大

### 对训练/评测
- 训练集和评测集会被同一地址的多条标签放大
- 样本独立性变差
- 指标改善会被重复样本稀释或扭曲

## 这不是运营问题，而是系统逻辑问题
运营人员并没有做错。  
重复出现是因为系统把：

- “同一地址的新 task_type”

错误地当成了：

- “一条新的需要人工审核的样本”

## 修复必须满足的要求
### 1. 审核队列生成必须按 `source_id` 级别排除已审核样本
默认情况下，只要同一 `source_id` 已有人审 accepted gold，就不应再次自动入队。

### 2. 审核队列生成必须排除已存在的历史队列项
不能因为 `task_type` 改变，就再次把同一地址插入审核队列。

### 3. `freeze gold` / 训练 / 评测 默认应按 `source_id` 去重
即使历史上已经产生了重复 gold，也不应继续把这些重复样本全部当成独立训练样本使用。

### 4. 如需重新审核同一地址，应走显式重开机制
如果后续确实需要重新审核某个地址，不应由自动抽样逻辑隐式重复入队，而应通过明确的重开/强制复审机制触发。

## 最小验收标准
1. 对同一批已审核 `source_id` 再次运行：
   - `seed_active_learning_queue`
   - `seed_active_learning_from_errors`
   - `seed_unit_commercial_review_queue`
   不应再次插入同一地址的新队列项
2. 新一轮队列中不应再出现“上轮已人工 accepted 的同一地址”
3. `freeze gold` 的样本统计应按去重后的 `source_id` 反映，而不是按重复 task_type 叠加

## 当前结论
当前大量“上次已经审过，这次又出现”的根本原因是：

**系统是按 `(source_id + task_type)` 判断是否重复，而不是按“同一地址是否已经完成人工审核”判断是否应再次入队。**
