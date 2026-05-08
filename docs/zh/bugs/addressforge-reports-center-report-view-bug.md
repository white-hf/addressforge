# AddressForge 报表中心查看接口缺失与报表落盘路径不一致 Bug

## 问题类型
- 功能性缺陷
- 报表查看链路断裂
- 前后端契约不一致

## 问题概述
运营人员在控制台中执行 `run shadow` 或完成训练 / 评测后，进入 `Reports Center / 报表中心` 点击：

- `质量汇总报表`
- `模型评测报表`
- `金标治理报表`

页面会持续提示无报告，后台日志同时出现：

- `GET /api/v1/business/reports/view/quality` -> `404`
- `GET /api/v1/business/reports/view/evaluation` -> `404`
- `GET /api/v1/business/reports/view/gold_governance` -> `404`

这不是“报告还没生成”的单一问题，而是报表中心的查看入口、报表扫描目录、以及实际报表产物位置之间存在明确断裂。

## 现象
### 1. 报表中心点击查看直接触发不存在的路由
前端模板 [reports.html](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/templates/reports.html:141) 中：

- `viewReport('quality')`
- `viewReport('evaluation')`
- `viewReport('gold_governance')`

会请求：

- `/api/v1/business/reports/view/quality`
- `/api/v1/business/reports/view/evaluation`
- `/api/v1/business/reports/view/gold_governance`

但后端 [business.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/api/routes/business.py:47) 只实现了：

- `GET /api/v1/business/reports`
- `GET /api/v1/business/reports/download`
- `GET /api/v1/business/benchmark-report`

并没有实现任何 `/reports/view/{type}` 路由。

### 2. 报表列表扫描目录与实际评测产物目录不一致
[business_service.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/services/business_service.py:117) 的 `get_reports_list()` 只扫描：

- `runtime/reports`

但评测相关产物实际至少分散在两个位置：

- `runtime/reports`
  - `*_release_report.md`
- `runtime/models`
  - `*_eval.md`
  - `*_eval.json`
  - `*_shadow.json`

当前代码中：

- evaluation Markdown release report 写入 `runtime/reports`
  - 见 [evaluator.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/evaluator.py:657)
- benchmark/eval markdown 仍存在于 `runtime/models`
  - 见实际运行目录
- shadow 结果只写 `runtime/models/*_shadow.json`
  - 见 [shadow.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/learning/shadow.py:191)

因此报表中心当前既没有统一的查看路由，也没有统一的报表发现策略。

### 3. 报表摘要字段并未真实反映各类报表
`get_reports_list()` 当前返回的 summaries 为：

- `quality = files[0]["created_at"] if files else "-"`
- `evaluation = "-"`
- `gold = "-"`

也就是说：

- `quality` 实际只是“runtime/reports 里最新任意文件时间”
- `evaluation` 永远是 `-`
- `gold` 永远是 `-`

这会导致报表中心顶部卡片即使存在评测/治理产物，也仍然表现为“无报告”或时间未更新。

## 根因分析
### 根因 1：前端调用了未实现的查看接口
报表页已经按类型组织了：

- quality
- evaluation
- gold_governance

但后端没有对应的 type-specific view API。

### 根因 2：报表产物没有统一归档协议
不同报表写在不同目录：

- `runtime/reports`
- `runtime/models`

且 shadow/gold governance 并没有稳定的 markdown/html 查看产物。

### 根因 3：报表中心列表逻辑与业务语义脱节
当前 `Reports Center` 不是在回答：

- “最新 quality report 在哪里”
- “最新 evaluation report 在哪里”
- “最新 gold governance report 在哪里”

而是在回答：

- “runtime/reports 目录里最近有哪些文件”

这导致业务语义和文件系统扫描结果不一致。

## 对运营的直接影响
- 用户执行 `run shadow` 后，无法在报表中心确认结果是否生成
- 用户点击 `查看评测` / `治理分析` 只会收到 404 或“Report not ready”
- 报表中心不能承担“训练/评测/shadow/gate 结果查看”的功能
- 用户必须依赖日志、数据库或文件系统人工排查
- 系统看起来像“支持报表查看”，但实际查看链路并未闭合

## 这不是体验优化，而是功能缺陷
这个问题不是“按钮位置不好”或“文案不清楚”，而是：

- 前端调用不存在的 API
- 后端没有提供对应能力
- 报表发现逻辑与产物生成逻辑不一致

因此应按功能性 Bug 修复，而不是按纯 UX 优化处理。

## 架构师修复时必须满足的要求
### 1. `/api/v1/business/reports/view/{type}` 必须真实存在
至少要支持：

- `quality`
- `evaluation`
- `gold_governance`

并且每种类型都必须有明确的取最新报表逻辑。

### 2. 报表产物必须有统一归档约定
需要明确：

- 哪些报表统一写入 `runtime/reports`
- 哪些模型级 artifact 保留在 `runtime/models`
- 报表中心到底读取哪一类产物

不能继续依赖不同目录的零散文件碰运气被扫到。

### 3. 报表 summaries 必须按类型真实计算
至少要能分别返回：

- 最新 quality report 时间
- 最新 evaluation report 时间
- 最新 gold governance report 时间

不能继续用单个目录中的任意最新文件时间冒充 `quality`。

### 4. shadow 结果必须能被报表中心查看
如果 shadow 是发布流程中的关键步骤，那么：

- 不能只写 JSON artifact 到 `runtime/models`
- 必须能通过报表中心查看摘要或详细报告

### 5. 404 必须被消除，而不是继续由前端兜底 toast
前端当前 `showToast("Report not ready or missing.")` 只是掩盖问题，不能替代后端路由与报表生成能力。

## 最小验收标准
以下链路必须全部成立：

1. 用户运行 `evaluation_once` 或 `shadow_once`
2. 系统生成对应类型的可查看报表
3. `Reports Center` 顶部卡片显示真实更新时间
4. 点击 `查看评测 / 立即查看 / 治理分析` 不再返回 404
5. 页面能展示最新同类型报表，而不是仅提供下载

## 当前结论
当前 `Reports Center` 的问题本质上是：

**前端存在查看入口，但后端未实现对应路由；同时报表产物目录与扫描逻辑不统一，导致运行了 evaluation/shadow 后，用户依然无法在报表中心查看结果。**
