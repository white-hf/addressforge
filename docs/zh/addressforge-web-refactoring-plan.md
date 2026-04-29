# AddressForge Web 重构迭代计划 (Web Modernization Roadmap)

> **目标**：将当前单文件 FastAPI 应用重构为符合现代运营网站规范的架构。

## 阶段 1: 基础设施迁移
- [ ] 任务 1.1: 创建 templates/ 和 static/ 目录结构。
- [ ] 任务 1.2: 配置 FastAPI Jinja2 模板引擎。
- [ ] 任务 1.3: 将 server.py 中的 HTML/JS 逻辑提取到 templates/base.html 和 templates/dashboard.html。

## 阶段 2: 静态资源标准化
- [ ] 任务 2.1: 将内嵌 CSS 抽离为 static/css/style.css，引入 Tailwind CSS CDN。
- [ ] 任务 2.2: 将内嵌 JavaScript 抽离为 static/js/app.js。
- [ ] 任务 2.3: 设置 FastAPI 静态文件挂载。

## 阶段 3: 前端交互与国际化
- [ ] 任务 3.1: 在 JS 中实现基于词典的 I18N 切换逻辑。
- [ ] 任务 3.2: 重构导航，引入业务中心化布局。

## 阶段 4: 清理与验收
- [ ] 任务 4.1: 删除 server.py 中所有 HTML 字符串硬编码。
- [ ] 任务 4.2: 全流程回归测试。
