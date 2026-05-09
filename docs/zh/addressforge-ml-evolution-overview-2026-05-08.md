# AddressForge 机器学习技术演进说明（面向非 ML 专家）

## 1. 文档目的
这份文档面向：

- 不是机器学习专家，但有扎实工程背景的技术负责人
- 需要理解 AddressForge 为何引入机器学习
- 需要判断当前系统的 ML 设计是否合理
- 需要决定下一版本 ML 技术如何演进

这份文档会回答 4 个核心问题：

1. 这个项目一开始为什么要用机器学习
2. 这个项目里机器学习是如何一步步被设计和接入的
3. 当前系统的 ML 层为什么还比较弱
4. 下一版本最合理的 ML 演进方向是什么

---

## 2. 一句话总结

**AddressForge 当前并不是“没有用机器学习”，而是处于“规则/解析主链已经较强，但机器学习层仍主要停留在统计校准与权重学习”的阶段。**

它已经具备：

- parser 主链
- reference 匹配
- canonical assetization
- human review -> gold -> training -> evaluation -> shadow -> gate 闭环

但它的“训练”目前还主要是：

- 学阈值
- 学 feature weight
- 学 pairwise weight

而不是：

- 使用更强的监督学习模型来直接学习复杂边界

所以当前系统更准确的定位不是：

- “传统纯规则系统”

也不是：

- “成熟的监督学习地址模型”

而是：

- **一个工程化很强、数据闭环较完整，但 ML 模型层还偏轻量的地址治理系统**

---

## 3. 项目最初为什么要用 ML

### 3.1 地址解析不是纯规则就能长期做好的问题

如果地址数据总是非常标准，例如：

- `123 Main St, Halifax, NS`
- `Unit 305, 5633 Fenwick St, Halifax, NS`

那么规则系统已经足够。

但真实业务里的地址会出现大量非标准形式，例如：

- `241 Broad Street 105 Bedford NS`
- `6886 NS-325 West Clifford NS`
- `505-1000 micmac boulevard 505 Dartmouth NS`
- `SUSHI ON BROAD INC226 BROAD ST UNIT107BEDFORD NS...`
- `58 14th Street garage apt TRENTON NS`

这些地址的问题是：

- 格式不统一
- 顺序会乱
- 会混入楼名、公司名、地区名、道路编号
- 单元号和路名里的数字长得很像
- 人工一眼能看懂，但规则很难全部覆盖

这就意味着：  
**系统不能只靠硬编码规则判断，它必须具备“从错误中学习”的能力。**

### 3.2 机器学习在这个项目里的真正角色

AddressForge 里引入机器学习，并不是为了“用 AI 替代全部解析逻辑”，而是为了做三件事：

1. **从人工审核中学习**
   - 哪类地址其实应该是 `multi_unit`
   - 哪类地址其实应该是 `single_unit`
   - 哪类地址该 `accept`
   - 哪类地址该 `review`

2. **对 parser / candidate / reference 的结果重新排序**
   - 多个候选里哪个更可信
   - 有没有 unit
   - building_type 应该是什么

3. **不断修正边界**
   - `numbered road` vs `unit number`
   - `true apartment` vs `double-number house`
   - `accept` vs `review`

也就是说，项目最初的 ML 初衷是合理的：

- **不是让模型直接端到端“猜地址”**
- 而是让系统在规则和参考数据的基础上，逐步从人审中学习边界

这个方向本身是对的。

---

## 4. 当前系统是如何一步步接入机器学习的

这一段很关键。  
因为从系统现状看，ML 并不是一开始就完整设计好的，而是**逐步长出来的**。

### 阶段 A：先有 parser / normalize / validate 主链

最早期系统先解决的是：

- 原始地址如何进入系统
- 如何标准化
- 如何做基础解析
- 如何给出 `accept/review/reject`

这一阶段的主技术手段是：

- 规则
- 正则
- 地址特征提取
- `libpostal`
- 参考地址匹配

这一步是必须的。  
因为如果连基础结构都提不出来，后面没有任何训练空间。

### 阶段 B：接通 human review -> gold -> eval

第二步，系统逐步具备了：

- review queue
- human gold
- freeze snapshot
- evaluation benchmark
- release gate

这一阶段的价值是：

- 系统第一次获得了“监督信号”
- 开始能够比较：
  - 老模型 vs 新模型
  - active vs candidate

这一步实际上比“先上复杂模型”更重要。  
因为没有 gold 和 eval，任何 ML 设计都只是拍脑袋。

### 阶段 C：引入“可学习权重”

后面系统开始引入：

- `decision_policy`
- `match_rule_weights`
- `parser_weights`
- `candidate_feature_weights`
- `candidate_pair_weights`

这是当前系统真正的 ML 雏形。

意思是：

- 不再完全手写固定规则
- 而是利用 gold 统计出：
  - 什么特征更可靠
  - 哪种 parser 候选更可信
  - 哪种模式更像公寓
  - 哪种模式更像 house

这一阶段已经不是纯规则了，  
但它本质上仍然是：

- **“统计学习 + 权重校准”**

而不是更强的监督模型。

### 阶段 D：引入 hard-sample 策略与平衡抽样

再往后，系统逐步意识到：

- 不是所有人审样本都一样有价值
- hardest cases 很有价值，但也会带偏训练分布

因此又引入了：

- correction pool
- calibration pool
- semantic ambiguity review
- decision calibration review
- label consistency diagnostics

这一阶段非常关键。  
因为它标志着系统开始从：

- “有人工审核”

进化为：

- “知道怎样抽样才能让机器学习更有效”

这一步说明系统的 ML 数据治理已经开始成熟。

---

## 5. 当前系统的机器学习，实际上用了什么

### 5.1 现在主要依赖的不是“大模型”或神经网络

当前系统里，机器学习层主要依赖：

- `numpy`
- `pandas`
- `scipy`
- `libpostal`

而代码层面的训练主要集中在：

- `learning/trainer.py`
- `learning/reranking_trainer.py`

### 5.2 当前训练的本质

当前系统的“训练”主要做的是：

1. 从 gold 中读取：
   - raw text
   - building_type
   - unit_number
   - decision
   - notes/sample_pool
   - parser candidate

2. 统计哪些模式更可靠
   - 哪种 parser source 更准
   - 哪种 rule/match pattern 更准
   - 哪些 candidate 特征对正确结果更有帮助
   - 哪些 pairwise 比较更常赢

3. 输出成 artifact
   - `decision_policy`
   - `match_rule_weights`
   - `candidate_feature_weights`
   - `candidate_pair_weights`

4. 在 runtime 使用这些 artifact
   - 对 parser 候选重新排序
   - 调整 `accept/review/reject`
   - 调整 building_type/unit 倾向

所以当前的 ML 不是：

- `fit(X, y)` 训练一个真正的分类器

而更像：

- **从 gold 统计“经验权重”，再回写规则系统**

这是一种合理的过渡方案，但天花板比较低。

---

## 6. 当前方法的优点是什么

尽管它还不强，但不是没有价值。

### 6.1 可解释

当前系统最大的优点是：

- 你可以解释为什么做出这个判断
- 你知道哪个 parser 模式命中了
- 你知道为什么进入 review
- 你知道哪个 candidate feature 加了分或减了分

这对地址治理场景非常重要。

### 6.2 对小规模 gold 比较稳定

当前人审 gold 虽然已经有一定规模，但还远没有达到：

- 几万
- 几十万

这样的监督量级。

在这种数据规模下，  
直接上复杂神经网络未必稳，  
而当前权重学习方案在早期更容易工作。

### 6.3 适合和 parser / reference / canonical 联动

地址问题不是纯文本分类问题。  
它本质上是：

- 结构恢复
- 候选排序
- reference 对齐
- canonical 收敛

当前这套方法更容易与这些工程模块协同。

---

## 7. 当前方法的核心局限在哪里

这是最重要的一部分。

### 7.1 它很难学习复杂交互

例如：

- street 里有数字，但这个数字不是 unit
- 第二个数字有时是 unit，有时是 road number
- 商业名前缀有时是噪音，有时是重要信号

当前系统虽然可以用 feature weight 近似表达，  
但它很难自动学习：

- 多个特征组合在一起时的复杂边界

这本来是树模型、GBDT、神经网络更擅长的部分。

### 7.2 它很容易被 gold 分布带偏

你们已经亲眼看到了这个问题：

- hardest cases 审多了
- 模型就容易学偏
- decision 或 apartment/unit 会被拉坏

这说明当前 ML 层对分布偏移不够鲁棒。

### 7.3 它更像“可学习规则”，而不是强监督模型

当前训练层不是没有 ML，  
但它仍然偏：

- heuristic learning
- weight calibration

而不是：

- 真正的判别模型

这意味着它更适合：

- 把 0 提升到 1

但不太适合：

- 把 1 提升到 10

### 7.4 `decision` 问题已经暴露出天花板

当前 apartment/unit 主线已经多次修回来了，  
但 `decision_f1` 一直很难稳定超过 active。

这恰恰说明：

- parser 主链不是唯一问题
- 当前的 threshold/weight 机制在 decision 边界上已经接近上限

---

## 8. 为什么系统最初目标是 ML 驱动，但现在 ML 仍然偏弱

这个问题需要正面回答。

### 8.1 不是方向完全错了

首先要明确：

**系统最初决定“用 ML 处理地址数据”这个方向没有错。**

错的不是方向，  
而是**演进顺序和实现层次偏保守**。

### 8.2 根因 1：最初必须先把工程主链打通

如果站在架构角度回看，项目早期先做这些事情是合理的：

- ingestion
- cleaning
- parser
- validate
- review
- gold
- evaluation
- canonical/reference

因为没有这些：

- 就没有监督数据
- 没有训练闭环
- 没法度量收益

所以早期优先工程主链，而不是优先上复杂 ML，是正确的。

### 8.3 根因 2：系统一开始缺的是“数据和闭环”，不是“模型算法”

许多机器学习项目早期失败，不是因为算法差，  
而是因为：

- 没有稳定 gold
- 没有真实错误桶
- 没有 release gate
- 没有 fresh-data 验证

AddressForge 用很长时间把这些底座补齐了。  
这其实是在做“机器学习系统工程”，不是单纯在做模型。

### 8.4 根因 3：中间采取了较保守的 ML 方案

当前 ML 之所以仍偏弱，更直接的原因是：

- 系统在引入学习能力时，采用的是**低风险权重学习路线**

这条路线的好处是：

- 容易接入
- 可解释
- 风险低
- 对现有规则系统侵入小

但坏处就是：

- 不够强
- 演进慢
- 到了后期容易碰天花板

### 8.5 根因 4：系统缺少“真正的监督学习层”

当前系统已经具备：

- 数据
- gold
- batch
- review
- evaluation
- shadow

但是还没有把这些真正转化成：

- 一个更强的 supervised model layer

所以不是最初框架完全没设计好，  
而是：

- **前期重点放在工程闭环，后期还没完成从“可学习权重系统”到“监督学习系统”的跃迁**

这是系统当前最核心的技术债。

---

## 9. 当前是否需要神经网络

### 9.1 结论：现在不应该立刻上神经网络主模型

当前不建议直接把主链改成：

- BERT 类文本分类器
- Transformer 地址序列标注
- 端到端神经 parser

原因：

1. 当前任务高度结构化
2. parser/reference/canonical 仍然必须保留
3. gold 规模还不够大到支持稳定训练强神经模型
4. 神经网络会降低可解释性
5. 当前最大的收益不在“更强文本编码”，而在“更强边界判别”

### 9.2 神经网络未来可能用在哪

未来更适合神经网络的地方是：

- commercial/prefix-noise hard cases
- 候选 reranking
- building/venue name 语义判断
- 公司名 vs 地址体区分

更合理的方式是：

- **先作为 hard-case reranker**
- 而不是直接替代主 parser

---

## 10. 下一版本最合理的 ML 演进设计

这是本文件最重要的结论部分。

### 10.1 不推翻现有 parser / reference / canonical 主链

下一版本不应做的事情：

- 不应该推翻现有 parser 主链
- 不应该放弃 libpostal
- 不应该把系统改成纯黑盒模型

这些工程主链已经是当前系统的优势。

### 10.2 新增一个真正的监督学习层

下一版本最合理的做法是：

**在现有系统之上，新增一个强的 supervised tabular model layer。**

优先用于 3 个任务：

1. `decision`
2. `building_type`
3. candidate reranking

### 10.3 为什么是表格模型而不是神经网络

因为当前系统已经有大量结构化特征：

- parser confidence
- parser pattern
- unit_source
- reference score
- parser_disagreement
- numbered-road flag
- explicit unit hint
- commercial hint
- sample_pool
- street/unit text alignment

这些特征非常适合：

- GBDT
- 树模型
- 表格监督模型

而不是必须用神经网络。

### 10.4 推荐技术方案

#### 首选：CatBoost

推荐理由：

- 对类别特征友好
- 对缺失值友好
- 对中小规模 gold 很合适
- 能学复杂交互
- 可解释性强于神经网络

适用任务：

- `decision` classifier
- `building_type` classifier
- candidate reranking score

#### 备选：XGBoost / LightGBM

也很强，适合：

- tabular feature learning
- pairwise ranking
- 多目标判别

#### 保守方案：scikit-learn HistGradientBoosting

适合做第一版 baseline，特点是：

- 引入成本低
- 工程风险小
- 可以先验证“真正监督学习模型是否明显优于当前权重法”

---

## 11. 下一版本的推荐技术路线图

### 第一步：保留现有系统，新增并行 baseline model

先不要替换当前权重法，  
而是并行做一个 baseline：

- 输入：当前 runtime 已有结构化特征
- 输出：
  - `decision`
  - `building_type`
  - candidate ranking score

先和现有 artifact 方案并行对比：

- 谁更稳
- 谁更强
- 谁更容易过 gate

### 第二步：先替换 `decision` 学习层

这是最适合先升级的部分，因为当前最明显的瓶颈就是：

- `decision_f1`
- `OVER_SENSITIVE_REVIEW`

而且它对 runtime 的侵入最小。

### 第三步：再替换 candidate reranking

当前 parser 主链可以保留，  
但最后选哪个 candidate，  
很适合改成更强的监督排序模型。

### 第四步：最后再看 building_type 是否独立建模

如果 `decision` 和 reranking 解决后，  
`building_type` 还有边界问题，  
再单独做 building_type classifier。

---

## 12. 这对系统意味着什么

如果走这条路线，系统会从：

- **规则 + reference + 统计权重校准**

演进成：

- **规则 + reference + supervised ranking/classification**

这会带来 3 个直接变化：

1. 更强的复杂边界学习能力
2. 更少依赖手工调 threshold
3. 更可能在保持 apartment/unit 主线的同时，把 `decision_f1` 拉起来

---

## 13. 最终判断

### 当前系统设计是不是一开始没设计好？

**不应该简单地下结论说“最初设计错了”。**

更准确的判断是：

- 最初的系统工程方向是对的
- 先建设数据闭环和地址治理主链也是对的
- 但 ML 层长期停留在“可学习权重”阶段，没有及时升级为“更强监督学习模型”

所以真正的问题不是：

- 一开始完全没想清楚

而是：

- **系统先把工程底座做强了，但 ML 模型层的升级节奏慢于系统主线成熟速度**

### 当前系统最该补的不是更多规则，也不是直接上神经网络

而是：

- **引入一个真正的监督学习层**
- 优先使用表格模型
- 先打 `decision` 和 reranking

---

## 14. 推荐结论

### 保持不变的部分

- parser 主链
- libpostal
- reference matching
- canonical assetization
- human gold / eval / shadow / gate 闭环

### 需要升级的部分

- `decision_policy`
- `candidate_feature_weights`
- `candidate_pair_weights`

### 推荐下一代 ML 设计

1. 先引入 `CatBoost` 或 `HistGradientBoosting` baseline
2. 先替代 `decision` 学习层
3. 再引入 candidate reranking classifier/ranker
4. 神经网络放在更后面的 hard-case reranking 阶段

---

## 15. 一句话结论

**AddressForge 目前不是没有机器学习，而是机器学习层还停留在“统计校准型 ML”的阶段。**

这不是因为项目最初方向完全错误，  
而是因为系统前期先把工程主链和数据闭环做强了，  
但后续没有及时把 ML 模型层升级成更强的监督学习系统。

**下一版本最合理的演进，不是直接上神经网络，而是先引入强的表格监督模型，优先升级 `decision` 和 candidate reranking。**
