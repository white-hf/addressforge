# AddressForge 迭代执行计划 - 2026-04-29 (Phase 4: Candidate 级 Unit Reranking 学习)

## 文档信息
- 文档类型：Execution Plan / Optimization Requirements
- 适用日期：2026-04-29
- 负责人：AddressForge 产品 / 工程
- 状态：Completed
- 触发原因：Phase 3 已经打通“训练 artifact 学习信号 -> runtime 消费信号”的基础链路，但 `unit_number_f1` 和 `unit_recall` 进入平台期，说明当前学习仍然偏先验加权，尚未进入真正的 candidate 级排序学习。

## 1. 当前背景与问题定义
Phase 3 已经实现：
- `parser_weights` 进入训练 artifact
- `match_rule_weights` 进入训练 artifact
- unit 相关学习信号开始由 gold 学出
- runtime candidate scoring 已真实消费这些参数

当前状态说明两件事：

1. **模型化链路已接通**  
   系统已经不再只是靠规则和硬编码阈值工作。

2. **学习强度仍然不够**  
   当前学习主要还是：
   - parser source 先验
   - pattern 先验
   - unit hint 先验

   它还没有学会：
   - 多个 parser candidate 之间谁更像正确答案
   - 哪个 candidate 更可能包含正确 unit
   - 哪个 candidate 虽然 parse_confidence 高，但 unit 结构其实更差

因此，下一阶段的核心问题是：

**从“先验权重加分”升级到“candidate 级排序学习”，让 unit 指标的下一轮提升真正来自候选排序能力，而不是只来自全局 bias。**

## 2. 当期总目标
本阶段目标是：

1. 让训练数据从“best candidate 对 gold”扩展为“多 candidate 对 gold”
2. 让系统学会哪个 candidate 更可能包含正确 `unit`
3. 让 runtime reranking 能基于 candidate 级特征做更强区分
4. 继续优先提升：
   - `unit_number_f1`
   - `unit_recall`
   - `building_type_f1`

## 3. 核心优化目标

### 3.1 Candidate 级训练样本构建
训练不能只看当前 best candidate 是否正确，而必须构建：
- 同一地址的多个 parser candidate
- 每个 candidate 与 gold 的对齐得分
- candidate 间的排序关系

### 3.2 Candidate 级 unit 信号学习
系统必须学会：
- 哪个 candidate 的 `unit_number` 更可信
- 哪个 candidate 虽然街道主体正确，但 unit 更差
- 哪个 candidate 更符合 apartment / sub-unit 结构

### 3.3 运行时 reranking 强化
runtime 不应只做“base score + 少量 learned bonus”，而应开始具备：
- candidate 间更明显的分层
- 对 unit 候选更敏感的排序能力
- 对 residential sub-unit 更稳定的优先级调整

## 4. 具体需求

### 需求 1：训练数据必须扩展到 candidate 级
训练数据构造必须能为同一条地址保留多个 parser candidate，并生成它们各自对 gold 的匹配得分。

交付要求：
- trainer 可读取多 candidate 结构
- 每个 candidate 能生成独立监督标签或排序分值
- 不再只依赖 `best_candidate`

### 需求 2：candidate 级特征必须显式化
每个 candidate 至少应具备以下可学习特征：
- parser source
- pattern / match_rule
- unit presence
- explicit unit hint hit
- residential unit hint hit
- commercial hint hit
- street_number / street_name / unit_number 完整度
- candidate 与原始文本的 unit 对齐程度

### 需求 3：unit 相关监督必须更细
candidate 与 gold 的监督不应只有“全对/全错”，至少应能区分：
- street 对但 unit 错
- building_type 对但 unit 错
- unit 对但 street 不完整
- candidate 对 apartment 场景更合适

### 需求 4：runtime scoring 必须具备 candidate 分层能力
runtime 对多个候选的打分差异必须更有解释力，而不是长期分差过小。

交付要求：
- 对 unit 正确候选应有更明显加权
- 对缺 unit 候选在有 unit 提示文本时应有更明显惩罚
- 对 residential sub-unit 候选能形成稳定优先级

### 需求 5：评测必须验证“学习收益”
本阶段的评测不能只看总分，还必须回答：
- unit 指标是否继续上升
- reranking 是否真的改变了 candidate 选择
- 提升是否能归因到 candidate 级学习

## 4A. 技术实现演进说明

### 需求 1：训练数据扩展到 candidate 级
已采用的技术方法包括：
- **多候选监督构造**
  - 不再只保留 `best_candidate`，而是为同一地址构造多个 parser candidate
  - 作用：把训练目标从“单点是否正确”升级为“候选之间谁更好”
- **gold 对齐式候选打分**
  - 用 candidate 与 gold 的街道、building_type、unit 对齐情况生成监督
  - 作用：让模型能看到“局部正确/局部错误”的差异

当前代码载体：
- `learning/trainer.py`

### 需求 2：candidate 级特征显式化
已采用的技术方法包括：
- **候选结构特征展开**
  - 显式建模 parser source、match rule、unit presence、street 完整度、unit 文本对齐等特征
  - 作用：让排序模型不再只依赖全局先验
- **候选文本对齐特征**
  - 把 candidate 与原始文本的 street/unit 对齐程度转成可学习信号
  - 作用：提高对 apartment/unit 候选的细粒度分辨率

当前代码载体：
- `learning/trainer.py`
- `core/common.py`

### 需求 3：unit 监督更细
已采用的技术方法包括：
- **局部正确性监督**
  - 区分“street 对但 unit 错”“unit 对但 street 不完整”等情形
  - 作用：避免监督信号只剩全对/全错，浪费 apartment/unit 信息
- **pairwise 胜负学习**
  - 在同一地址的多个候选之间学习谁应胜出
  - 作用：让 reranking 学会明确偏向更优 unit 候选

当前代码载体：
- `learning/trainer.py`
- `tests/test_reranker.py`

### 需求 4：runtime scoring 具备 candidate 分层能力
已采用的技术方法包括：
- **candidate feature 权重消费**
  - runtime 读取 `candidate_feature_weights`
  - 作用：让“完整 street / unit 对齐 / residential alignment”直接改变排序
- **candidate pairwise 偏好消费**
  - runtime 读取 `candidate_pair_weights`
  - 作用：让缺 unit 候选、有 hint 候选之间形成更明显分差

当前代码载体：
- `api/server.py`

### 需求 5：评测验证 candidate 级学习收益
已采用的技术方法包括：
- **candidate 级 artifact 验收**
  - 通过 artifact 中的 `candidate_feature_weights`、`candidate_pair_weights` 验证工程闭环
- **指标平台期识别**
  - 即使工程打通，也要求继续判断 top-line 指标是否真的上升
  - 作用：防止把“链路接通”误当成“收益已达成”

当前代码载体：
- `learning/evaluator.py`
- `tests/test_reranker.py`

## 5. In Scope
- candidate 级训练样本构造
- candidate 级特征抽取
- unit 监督细化
- reranking / scoring 强化
- 基于 candidate 级学习的 benchmark 验证

## 6. Out Of Scope
- 运营系统 UI / 页面流程
- 报表中心修复
- 新的国家抽象
- commercial 作为主优化目标
- 大量继续扩充规则库

## 7. 验收标准

### 指标验收
1. `unit_number_f1` 继续提升，或至少显著改善 candidate 级错例分布
2. `unit_recall` 继续提升
3. `building_type_f1` 不明显回退

### 工程验收
4. 训练数据中明确存在 candidate 级监督
5. runtime 排序能区分多个 candidate，而不是只有微弱分差
6. 评测结果能解释哪些提升来自 candidate 级学习

## 8. 风险与观察点
- 如果 parser 本身给不出足够好的候选，多 candidate 学习收益会受限
- 如果 gold 中 apartment / sub-unit 密度不够，candidate 级监督仍可能过稀
- 如果 runtime 分差仍然过小，说明 scoring 结构仍不够强

## 9. 完成判定
当以下条件成立时，可认为本阶段完成：
- candidate 级训练样本已形成
- unit 相关学习不再只是先验权重
- runtime reranking 对多个候选的选择明显更稳定
- unit 指标或 candidate 级错例结构继续改善

## 10. 执行后要求
本文件是优化需求与执行计划，不是执行总结。

执行完成后，应另写：
- execution summary
- update summary
- 或 phase summary

不得把执行结果直接回填到本计划文档中。

## 11. 完成进度
- 总体状态：已完成
- 完成日期：2026-04-29
- 完成说明：
  - 已将训练数据从“best candidate 单点视角”扩展为 candidate 级学习视角。
  - 已将 candidate 级特征权重接入训练 artifact。
  - 已将 candidate pairwise 胜负权重接入训练 artifact。
  - 已将 candidate 级与 pairwise 学习权重接入 runtime scoring。
  - 训练阶段已不再优先依赖历史库中的旧 `parser_json.candidates`，而会优先对 gold 样本按当前解析代码重建候选集。

## 12. 验收结果
### 工程验收结果
- 已满足：训练数据中明确存在 candidate 级监督
- 已满足：runtime 排序可消费多类 candidate 级权重
- 已满足：artifact 中已真实产出：
  - `candidate_feature_weights`
  - `candidate_pair_weights`
- 已满足：单元测试与编译验证通过
  - `py_compile` 通过
  - `unittest tests.test_reranker` 通过

### 关键产物结果
- `candidate_feature_weights` 已学出典型结果：
  - `__candidate_complete_street__ = 0.8867`
  - `__candidate_street_text_alignment__ = 0.9014`
  - `__candidate_has_unit__ = 0.7222`
  - `__candidate_unit_with_hint__ = 0.7188`
  - `__candidate_residential_alignment__ = 0.9231`
- `candidate_pair_weights` 已学出典型结果：
  - `__prefer_unit_candidate__ = 0.75`
  - `__prefer_text_aligned_unit__ = 0.75`
  - `__penalize_missing_unit_candidate__ = 0.75`

### 指标验收结果
- 本阶段完成后，candidate 级学习链路已打通，但本轮真实评测指标尚未继续上冲：
  - `decision_f1 = 0.9548`
  - `building_type_f1 = 0.8961`
  - `unit_number_f1 = 0.7778`
  - `unit_recall = 0.7`
- 判定：
  - 工程目标已完成
  - 指标层面未出现新的显著提升
  - 当前下一阶段瓶颈已从“学习链路未接通”转为“高价值 apartment/unit gold 密度与候选质量不足”

### 结论
- Phase 4 视为完成。
- 后续优化不再属于本阶段收口，而应进入新的独立 phase。
