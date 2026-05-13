# AddressForge 迭代 2 开发任务列表 (Iteration 2 Task List)

> **目标**：建立发布级 Benchmark，并引入错误分桶 (Error Bucketing) 机制，通过量化指标驱动算法优化。

## 1. 核心任务 (Core Tasks)

### 任务 2.1: 错误分桶逻辑升级 (Error Bucketing Enhancement)
- **描述**：升级当前的错误采样逻辑，将单一的错误样本列表转换为结构化的“错误分桶”。
- **要点**：
  - 定义桶分类：MISSING_UNIT, WRONG_BUILDING_TYPE, COMMERCIAL_MISCLASSIFICATION, PARSER_CONFLICT。
  - 在 evaluator.py 中实现自动归类逻辑。

### 任务 2.2: 发布级 Benchmark 报告固化 (Benchmark Reporting)
- **描述**：标准化评估报告输出格式，支持多版本横向对比。
- **要点**：
  - 完善 release_benchmark 指标输出。
  - 支持导出为 Markdown 文档。

### 任务 2.3: Benchmark 测试集增强 (Benchmark Expansion)
- **描述**：丰富 canada_address_benchmark.jsonl，覆盖高频脏文本及边缘 case。

### 任务 2.4: 分析报表自动化 (Analysis Report Automation)
- **描述**：自动将分桶结果转化为可辅助决策的报表。

## 2. 闭环任务 (Feedback Loop Tasks)

### 任务 2.5: 错误驱动的主动学习 (Error-Driven Active Learning)
- **描述**：建立“失败样本 -> 标注队列”的自动化链路。

## 3. 验收标准 (Definition of Done)
- [ ] 量化可比较：报告包含与前一版本 (Baseline) 的 Delta 对比。
- [ ] 分桶清晰：能够通过分桶报告明确指出当前模型最差的类别。
- [ ] 闭环可执行：错误样本集能够一键导出为复核包。
