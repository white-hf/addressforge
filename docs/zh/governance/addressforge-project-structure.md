# AddressForge 项目结构规范

## 文档信息
- 文档类型：Project Structure Standard
- 适用日期：2026-05-12
- 负责人：AddressForge 架构 / 工程
- 状态：Active
- 治理依据：
  - `addressforge-agile-delivery`
  - `codex-agile-product-delivery`

## 1. 文档目的

本文件用于正式定义 AddressForge 当前项目目录结构的职责边界，避免：

- 文档持续无序增长
- 运行产物与源码/模板混放
- 迭代计划、总结、设计文档职责重叠
- 测试、脚本、模型产物缺少清晰归属

本文件不要求立即重构全部历史目录，但从现在开始：

- 新文件应尽量按本规范放置
- 旧文件如发生实质更新，应逐步向本规范收口

## 2. 当前项目结构判断

当前项目已经具备较完整的基础结构：

- `src/addressforge/`
- `docs/zh/`
- `docs/en/`
- `tests/`
- `scripts/`
- `runtime/`
- `sql/`
- `templates/`
- `static/`
- `web/`

这说明项目并不是“缺结构”，而是：

- **结构已经很多，但治理边界需要正式化**

当前还存在几个需要明确规范的点：

1. 文档都堆在 `docs/zh` / `docs/en` 顶层，缺少二级分类
2. `runtime/` 和 `models/`、`catboost_info/`、`addressforge/addressforge/runtime/` 存在职责混淆
3. `tests/` 当前未按测试层次拆分
4. 运行时临时产物和长期工程资产没有完全分离

## 3. 顶层目录职责

### 3.1 `src/addressforge/`
核心系统源码目录。

子目录职责：
- `api/`
  - 对外 API 路由与 server 主链
- `console/`
  - 控制台后端
- `control/`
  - worker / job orchestration / pipeline control
- `core/`
  - 核心通用能力、配置、解析基础、特征、检索等
- `ingestion/`
  - 导入与数据接入
- `learning/`
  - 训练、评测、shadow、gold、baseline 等 ML 相关逻辑
- `models/`
  - 模型注册、模型元数据与模型管理逻辑
- `pipelines/`
  - 训练、清洗、导出等流水线
- `services/`
  - service 层业务逻辑
- `workspace/`
  - workspace 管理相关代码

### 3.2 `docs/`
正式文档主目录。

语言层拆分：
- `docs/zh/`
- `docs/en/`

建议职责：
- 中文与英文保持“主要正式文档”的对应关系
- 如果仅有中文是当前主版本，应在英文文档中保持最小同步说明

### 3.3 `tests/`
测试代码目录。

当前状态：
- 主要平铺在根下

推荐收口方向：
- `tests/unit/`
- `tests/integration/`
- `tests/regression/`

迁移原则：
- 不要求一次性搬迁全部历史测试
- 新测试应优先按层次放置
- 老测试在被大改或重构时再逐步迁移

### 3.4 `scripts/`
项目级脚本目录。

适合放置：
- ingestion / cleaning / refresh / export / verification 脚本
- 一次性修复脚本
- 生产辅助脚本

不适合放置：
- 长期核心业务逻辑
- 只供单元测试内部调用的辅助代码

### 3.5 `runtime/`
运行产物目录。

适合放置：
- `runtime/models/`
  - 训练产物、baseline compare、shadow、metadata
- `runtime/reports/`
  - 数据质量、资产质量、执行报告
- `runtime/vector_index/`
  - 检索索引
- `runtime/exports/`
  - 导出产物
- `runtime/addressforge.log`
  - 运行日志

原则：
- `runtime/` 里的内容默认视为**运行生成产物**
- 不应把源码级长期资产继续塞进这里

### 3.6 `models/`
长期模型模板或默认模型资产目录。

当前已有：
- `models/default_canada`

规范建议：
- `models/` 用于：
  - 默认模型包
  - 静态分发模型
  - 非运行中间产物
- 真正训练出来的当前运行产物应放 `runtime/models/`

### 3.7 `sql/`
数据库 schema 与结构迁移相关文件。

### 3.8 `templates/`
服务端 HTML 模板目录。

### 3.9 `static/`
静态资源目录。

### 3.10 `web/`
前端工程目录。

适合放置：
- 前端源码
- 构建产物

## 4. 文档目录规范

当前 `docs/zh` 和 `docs/en` 顶层文件较多。  
从现在开始，建议在逻辑上按下面 6 类理解，即使短期不立即搬目录：

1. **README / quickstart / workflow**
2. **product / requirements / roadmap**
3. **system design / architecture**
4. **iteration execution plans**
5. **iteration execution summaries**
6. **operations / runbooks / UI / benchmarks**

建议命名规则：
- `addressforge-iteration-execution-plan-<date>-phaseX.md`
- `addressforge-iteration-execution-summary-<date>-phaseX.md`
- `addressforge-<topic>-design.md`
- `addressforge-<topic>-guide.md`

## 5. 测试目录规范

### 5.1 当前原则
现有测试可继续运行，不强制立刻搬迁。

### 5.2 新增测试建议
- 纯函数/局部逻辑：
  - `tests/unit/`
- 多模块协作、服务层、DB mock：
  - `tests/integration/`
- 真实产物、长流程、回归问题复现：
  - `tests/regression/`

### 5.3 测试命名建议
- `test_<module>_<behavior>.py`
- 优先按行为命名，而不是按历史 issue 命名

## 6. 运行产物与源码资产分离规则

必须区分：

### 6.1 长期工程资产
例如：
- 默认模型模板
- 系统设计文档
- 训练代码
- schema

应放：
- `src/`
- `docs/`
- `models/`
- `sql/`

### 6.2 运行时生成产物
例如：
- compare artifact
- shadow artifact
- report
- vector index
- log

应放：
- `runtime/`

### 6.3 临时开发噪音
例如：
- `catboost_info/`
- 零散调试输出

建议：
- 默认视作临时产物
- 不应作为正式工程结构依赖

## 7. 当前特别说明

### 7.1 `addressforge/addressforge/runtime/`
该路径目前看起来像历史或重复结构。

规范建议：
- 不作为未来主结构继续扩展
- 后续如确认无生产依赖，应考虑逐步清理或合并说明

### 7.2 `catboost_info/`
这是 CatBoost 默认训练输出的临时目录。

规范建议：
- 视为训练噪音目录
- 不作为正式项目结构一部分

## 8. 新文件落点规则

从现在开始，新增内容按以下规则放置：

- 新 phase 计划：
  - `docs/zh/` 与 `docs/en/`
- 新 phase 总结：
  - `docs/zh/` 与 `docs/en/`
- 新系统设计：
  - `docs/zh/` 与必要的 `docs/en/`
- 新训练/评测产物：
  - `runtime/models/`
- 新质量报告：
  - `runtime/reports/`
- 新脚本：
  - `scripts/`
- 新测试：
  - 优先按层次放到 `tests/unit|integration|regression`

## 9. 执行原则

1. 不要求为目录规范一次性重构全仓库
2. 先规范**新增内容**
3. 旧内容在被大改时逐步归位
4. 所有结构调整都必须保证：
   - 链接不失效
   - 脚本路径不失效
   - 运行时路径不失效

## 10. 一句话结论

AddressForge 当前已经具备较完整的工程结构。  
本规范的目标不是推翻现状，而是：

- **把现有结构正式化**
- **给后续新增内容提供稳定落点**
- **避免项目继续无边界增长**

