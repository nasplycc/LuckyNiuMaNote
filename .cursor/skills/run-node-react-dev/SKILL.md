---
name: run-node-react-dev
description: 启动并调试本工程的 Node 后端与 React 前端。使用同一终端输出双服务日志，启动前自动检查并清理 3000/5173 端口占用，并用 Cursor 内置浏览器打开前端页面。适用于用户提到“启动前后端调试”“联调”“打开前端页面”或“清理端口后启动”。
---

# Run Node React Dev

## 作用范围

仅用于当前仓库 `LuckyNiuMaNote` 的本地开发调试。

- 后端：`node server.js`（端口 `3000`）
- 前端：`npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173`

## 执行流程

按顺序执行，禁止跳步：

1. 进入仓库根目录。
2. 检查根目录与 `frontend` 目录依赖，缺失则先安装。
3. 检查并清理端口 `3000`、`5173` 的占用进程。
4. 在同一个终端启动后端与前端，并为日志加前缀区分来源。
5. 确认前端可访问后，使用 Cursor 内置浏览器打开 `http://localhost:5173`。

## 依赖检查与安装

```bash
if [ ! -d "node_modules" ]; then
  echo "[deps] install root dependencies"
  npm install
else
  echo "[deps] root dependencies ready"
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "[deps] install frontend dependencies"
  npm --prefix frontend install
else
  echo "[deps] frontend dependencies ready"
fi
```

## 端口清理命令

```bash
for PORT in 3000 5173; do
  PIDS=$(lsof -ti tcp:$PORT || true)
  if [ -n "$PIDS" ]; then
    echo "[port-clean] kill tcp:$PORT -> $PIDS"
    kill -9 $PIDS
  else
    echo "[port-clean] tcp:$PORT free"
  fi
done
```

## 同终端启动双服务（统一日志）

```bash
node server.js 2>&1 | sed -u 's/^/[backend] /' &
BACKEND_PID=$!

npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173 2>&1 | sed -u 's/^/[frontend] /' &
FRONTEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

wait
```

## 打开 Cursor 内置浏览器

必须使用 MCP `cursor-ide-browser`，并先读取工具 schema 再调用。

1. 读取 `browser_navigate` 工具描述。
2. 调用：

```json
{
  "server": "cursor-ide-browser",
  "toolName": "browser_navigate",
  "arguments": {
    "url": "http://localhost:5173",
    "newTab": true
  }
}
```

## 验证标准

- 首次启动或依赖缺失时，终端输出 `[deps]` 安装日志并成功完成。
- 同一终端持续看到 `[backend]` 与 `[frontend]` 日志。
- 前端地址 `http://localhost:5173` 可在 Cursor 内置浏览器正常打开。
- 若端口被占用，启动前已输出对应清理日志。
