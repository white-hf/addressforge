# AddressForge 迭代 3 开发任务列表 (Iteration 3 Task List)

> **目标**：强化训练信号，构建主动学习 (Active Learning) 闭环。

## 1. 核心任务 (Core Tasks)

### 任务 3.1: Gold Label 治理与冻结 (Gold Label Governance)
- **描述**：完善 Human Gold Label 的获取、冻结与版本控制。
- **要点**：
  - 实现从 review_task_action 到 ml_gold_label 的自动化同步。
  - 增加 Gold Set 冻结版本机制，确保训练集的可复现性。

### 任务 3.2: 错例驱动的主动学习队列 (Active Learning Queue)
- **描述**：将评估阶段发现的高频“错误分桶”样本自动推入待人工审核队列。
- **要点**：
  - 开发自动筛选器：从评估结果中按错误桶 (Error Bucket) 优先级抽取样本。
  - 自动插入到 active_learning_queue 表中供人工复核。

### 任务 3.3: Benchmark 样本扩展 (Benchmark Expansion)
- **描述**：基于生产环境最新高价值数据，扩充 Benchmark 核心集。
- **要点**：
  - 引入多样化的 Canada 地区地址分布 (含长尾变体)。
  - 定期更新 Gold 标准集，作为后续训练的核心基线。

## 2. 闭环任务 (Feedback Loop Tasks)

### 任务 3.4: 弱标注回流 (Weak Labeling Feedback)
- **描述**：将 LLM 辅助复核的结果自动转化为训练的“弱信号”。
- **要点**：
  - 建立 LLM 输出 -> 结构化 Gold Label 映射表。
  - 确保 LLM 解释能被持久化到 ml_gold_label 中作为证据。

## 3. 验收标准 (Definition of Done)
- [ ] 训练信号强：系统能够明确标识哪些样本是“高价值训练数据”。
- [ ] 闭环可用：错误驱动采样不再是手工任务，而是评估后自动化的子流水线。
- [ ] Gold 可追溯：所有 Gold 样本均带版本标签和来源说明。
