# React 前端迁移设计（保留 Express API）

## 目标

将当前项目的页面渲染从 `server.js` 中的字符串拼接迁移为 React 客户端渲染，保留现有 Express API 路由与返回结构，保持页面 URL 与 UI 风格不变。

## 现状

- 后端：`Node.js + Express`
- 页面：`server.js` 中内联 HTML/CSS/JS 生成
- API：`/api/position`、`/api/traders-status`、`/api/indicators`、`/api/chart/:symbol` 等
- 数据：`build.js` 生成 `src/generated-data.js`

## 方案

采用 `Vite + React + React Router`：

- 前端工程放在 `frontend/`
- 路由保持不变：`/`、`/entry/:slug`、`/strategy`、`/learn`、`/learn/:slug`、`/chart`
- 样式从当前内联 CSS 抽离为 React 全局样式，优先复用 class 与变量
- Express 负责 API 与 React 静态文件托管
- 非 API 路由回退到 React `index.html`

## 边界与约束

- 不改变 API 路径与响应字段
- 不新增额外业务功能
- 不引入 SSR，仅 CSR
- 不改交易脚本与其调用链

## 风险与规避

- 风险：迁移体量大导致视觉偏差  
  规避：优先迁移关键样式 token 与主布局结构
- 风险：前端路由与后端冲突  
  规避：后端先匹配 `/api/*`，其余 fallback 到前端入口
- 风险：旧数据模块为 ESM 导出不便浏览器直接消费  
  规避：构建阶段输出 `public/generated-data.json` 供 React 读取

## 验收标准

- 所有原有页面 URL 可访问
- 所有现有 API 可用且响应结构不变
- `npm run build` 成功
- 主页、文章页、策略页、学习页、图表页样式与交互行为与现状一致（允许非核心像素级差异）
