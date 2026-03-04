# React Frontend Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将页面渲染迁移到 React CSR，保留现有 Express API 与 URL 结构并保持 UI 风格。

**Architecture:** 新建 `frontend`（Vite + React），Express 继续承载 `/api/*`。构建后由 Express 托管 `frontend/dist`，并对非 API 路由执行 `index.html` 回退。内容数据改为构建时输出 JSON，由 React 读取。

**Tech Stack:** Node.js、Express、Vite、React、React Router、Chart.js

---

### Task 1: 初始化 React 前端工程

**Files:**
- Create: `frontend/*`
- Modify: `package.json`

**Step 1: 生成前端项目**
Run: `npm create vite@latest frontend -- --template react`

**Step 2: 安装前端依赖**
Run: `npm --prefix frontend install`

**Step 3: 安装路由与图表依赖**
Run: `npm --prefix frontend install react-router-dom chart.js chartjs-adapter-date-fns`

**Step 4: 验证前端可构建**
Run: `npm --prefix frontend run build`  
Expected: 成功生成 `frontend/dist`

### Task 2: 迁移内容数据为 JSON 消费

**Files:**
- Modify: `build.js`
- Create: `frontend/public/generated-data.json`

**Step 1: 修改构建脚本输出 JSON**
将 `content` 数据额外写入 `frontend/public/generated-data.json`

**Step 2: 执行构建脚本**
Run: `npm run build`

**Step 3: 验证 JSON 产物**
检查 `frontend/public/generated-data.json` 存在且包含核心字段

### Task 3: 实现 React 页面与路由

**Files:**
- Create: `frontend/src/*`

**Step 1: 建立路由与页面骨架**
实现 `/`、`/entry/:slug`、`/strategy`、`/learn`、`/learn/:slug`、`/chart`

**Step 2: 迁移公共样式与工具**
抽离样式、日期与 markdown 工具

**Step 3: 接入现有 API**
在首页/图表页完成与现 `/api/*` 对接

**Step 4: 本地构建验证**
Run: `npm --prefix frontend run build`

### Task 4: 改造 Express 为 API + 静态托管

**Files:**
- Modify: `server.js`

**Step 1: 保留所有 `/api/*` 逻辑**
删除页面 HTML 模板函数与页面路由拼接逻辑

**Step 2: 增加静态托管与回退**
托管 `frontend/dist`，非 `/api/*` 返回 `index.html`

**Step 3: 验证服务可启动**
Run: `node server.js`

### Task 5: 端到端验证

**Files:**
- Modify: `package.json`（如需增加脚本）

**Step 1: 执行全量构建**
Run: `npm run build && npm --prefix frontend run build`

**Step 2: 运行服务并检查路由**
访问六个页面 URL，确认可加载

**Step 3: 检查 API**
访问关键 API，确认结构稳定
