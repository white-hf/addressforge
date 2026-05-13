# AddressForge Console 自动化闭环与重构迭代计划

> **目标**：实现 AddressForge 平台的数据处理全流程“API-First”化，并重构为标准的 Web 架构。

## 迭代阶段

### Phase 1: 核心 Pipeline 端点化 (Job 驱动)
- [x] 任务 1.1: 在 server.py 中添加 POST /api/v1/jobs/train 端点。
- [x] 任务 1.2: 在 server.py 中添加 POST /api/v1/jobs/evaluate 端点。
- [x] 任务 1.3: 集成 trainer 与 evaluator 到 ControlCenter 作业调度系统。

### Phase 2: 作业监控与进度可视化
- [x] 任务 2.1: 开发 GET /api/v1/jobs/{job_id}/status 接口。

### Phase 3: Benchmark 报表 Web 化
- [x] 任务 3.1: 开发 GET /api/v1/benchmark/report 接口。

### Phase 4: 闭环标注与策略配置
- [x] 任务 4.1: 实现 POST /api/v1/active-learning/seed 主动学习入队 API。

### Phase 5: 前端工程化与后端解耦 (Web 现代化)
- [ ] 任务 5.1: 建立 Service 层，将 server.py 的业务逻辑迁移至 src/addressforge/services。
- [ ] 任务 5.2: 将 server.py 拆分为模块化 Router (src/addressforge/api/routes/)。
- [ ] 任务 5.3: 初始化 web/ 目录 (Vite + React)，建立前端开发环境。
- [ ] 任务 5.4: 实现静态文件托管配置，彻底移除内嵌 HTML 模板。
