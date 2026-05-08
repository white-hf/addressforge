# AddressForge 运营系统任务状态缺陷说明

## 问题类型
- 功能缺失
- 状态展示缺陷
- 任务编排一致性问题

## 问题摘要
当前运营系统中，用户在 `Dashboard` 页面点击 `开始训练` 后，界面只提示 `job dispatched`，但用户无法在页面上可靠确认训练是否已经执行完成，也无法据此判断是否可以继续执行下一步 `运行评测`。

这不是单纯的体验优化问题，而是一个明确的功能性缺陷：**训练动作没有完整接入统一任务状态体系，而任务状态展示接口也没有返回页面所需的数据。**

## 复现路径
1. 打开 `Dashboard`
2. 点击 `开始训练`
3. 页面显示 `job dispatched`
4. 继续查看页面底部 `任务队列状态 (Recent Jobs)`
5. 观察不到本次训练任务的状态变化，无法判断：
   - 是否仍在运行
   - 是否已成功完成
   - 是否执行失败
   - 是否可以进入 `运行评测`

## 当前实际代码问题

### 1. `Recent Jobs` 前端依赖 `recent_jobs`，但后端未返回
前端页面 `Dashboard` 的任务表依赖 `/api/v1/control/status` 返回的 `recent_jobs` 字段。

但当前后端实现中：
- [src/addressforge/console/server.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/console/server.py:63)

`/api/v1/control/status` 只返回：
- `workspace`
- `gold_labels`
- `active_learning`
- `job_counts`
- `job_kind_counts`
- `continuous_mode`

没有返回：
- `recent_jobs`

因此前端表格会显示为空或无法反映真实任务记录。

### 2. `training_once` 没有进入统一 job 队列
当前 `Dashboard` 的 `开始训练` 实际调用：
- `POST /api/v1/jobs/trigger`

在后端：
- [src/addressforge/api/routes/jobs.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/api/routes/jobs.py:51)

`training_once` 被直接同步执行：
- `run_training_pipeline(...)`

而不是：
- `enqueue_job(...)`

这意味着：
- 训练不会进入 `control_job` / `job_service` 统一任务记录体系
- 训练不会自然出现在 `Recent Jobs`
- 训练状态无法和 `ingestion_once / cleaning_once / evaluation_once` 一样统一追踪

### 3. 页面提示与真实执行模型不一致
当前前端点击训练后提示：
- `job dispatched`

但后端并不是“排队任务”
而是“同步直接执行”

因此前后语义不一致：
- 前端让用户以为这是可追踪的异步任务
- 实际上后端是即时执行路径

### 4. 训练、评测、shadow 的任务模式不一致
当前系统中：
- `ingestion_once` / `cleaning_once` / `evaluation_once` 走统一队列
- `training_once` 走同步执行
- `shadow` 又是评测后的 follow-up

这导致运营人员无法形成稳定的任务心智：
- 哪些动作有任务状态
- 哪些动作没有任务状态
- 哪些动作会自动 follow-up

## 对业务流程的直接影响
这个问题会直接影响运营执行链路：

1. 用户无法确认训练是否完成
2. 用户无法确认是否应该继续点击 `运行评测`
3. 用户无法区分训练失败和训练尚未完成
4. 页面“最近任务记录”无法作为可靠执行依据
5. 运营执行链路从 `freeze gold -> retrain -> evaluate` 中断在状态判断环节

## 对修复方向的明确要求
此处只列修复要求，不展开产品方案。

### 必须满足的修复目标
1. `training_once` 必须进入统一任务状态体系，或提供同等级的可追踪运行状态
2. `Dashboard` 的 `Recent Jobs` 必须返回并展示真实最近任务记录
3. 用户必须能够明确看到训练任务的：
   - `queued`
   - `running`
   - `succeeded`
   - `failed`
4. 用户必须能够据任务状态判断是否可继续执行 `运行评测`
5. 前端提示文案必须与后端真实执行模型一致，不能继续出现“看起来是 job，实际上不是 job”的语义错位

## 结论
这是一个会阻断运营执行链路的功能性缺陷，不应归类为纯体验问题。

本质上，当前系统存在：
- 任务状态接口返回不完整
- 训练任务未接入统一任务体系
- 前后端任务语义不一致

需要按功能修复方式处理，而不是仅作为体验优化处理。
