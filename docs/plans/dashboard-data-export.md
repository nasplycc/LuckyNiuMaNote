# LuckyNiuMa Dashboard Data Export

## 目的

为 LuckyNiuMa 的网页前端 / 微信小程序 / 其他只读客户端提供统一的数据出口。

当前方案不要求独立服务器、不要求先做公网 API，直接在 NAS 本机定时生成 JSON 文件。

## 导出脚本

路径：

```bash
trading-scripts/export-dashboard-data.py
```

执行：

```bash
cd trading-scripts
.venv/bin/python export-dashboard-data.py
```

## 输出目录

```bash
data-export/
├── meta.json
├── overview.json
├── positions.json
├── trades.json
├── orders.json
├── performance.json
├── bot_status.json
└── alerts.json
```

## 字段用途

### overview.json
首页总览：
- 总权益
- 可用余额
- 保证金占用
- 浮盈亏
- 持仓数
- 挂单数
- 当前模式（LIVE / SAFE_MODE）

### positions.json
当前持仓：
- symbol
- side
- size
- entry_price
- mark_price
- unrealized_pnl
- unrealized_pnl_pct
- leverage
- stop_loss / take_profit（若本地状态层有记录）

### trades.json
最近成交（当前初版主要由 orders 表里的 FILLED / EXECUTED / CLOSED 推导）

### orders.json
最近订单 / 挂单状态

### performance.json
当前为基础版：
- 当前权益快照
- total_return_pct
- 后续待补历史权益曲线、胜率、回撤

### bot_status.json
机器人状态：
- systemd 服务状态
- SAFE_MODE
- 最近心跳
- 最近交易时间
- SQLite 是否可用
- git 版本号

### alerts.json
最近系统事件 / 风险告警

## 当前数据源

脚本会尽量复用现有 LuckyNiuMa 数据链路：

- Hyperliquid API
- `trading-scripts/state/trader_state.db`
- `logs/trader_nfi.log`
- `frontend/public/generated-data.json`
- systemd 服务 `luckyniuma-trader.service`
- git commit hash

## 自动刷新

当前已并入：

```bash
trading-scripts/realtime_data_cron.sh
```

刷新频率：
- 每 30 秒执行一次

每轮会执行：

```bash
.venv/bin/python generate_realtime_data.py
.venv/bin/python export-dashboard-data.py
```

因此现有 PM2 的 `realtime-data` 进程启动后，会同时刷新：
- 原网站实时数据
- 新 dashboard JSON 数据

## 前端接入状态

当前已完成：

- 新增 React 页面：`frontend/src/pages/DashboardPage.jsx`
- 新增前端数据 hook：`useDashboardData()`
- 新增页面路由：`/dashboard`
- 顶部导航已加入 `Dashboard`
- `server.js` 已暴露静态目录：`/data-export`
- `server.js` 已将 `/dashboard` 纳入 SPA 路由回退
- `frontend` 已成功执行 `npm install` 与 `npm run build`

因此现在网页端已经具备直接消费 `data-export/*.json` 的能力。

## 推荐用途

这套 JSON 可以作为以下前端的数据源：

1. LuckyNiuMa 网站 dashboard 页面
2. 手机端 H5 页面
3. 微信小程序展示层
4. 云端同步中间层

## 当前限制

### 已完成
- 数据出口已建立
- JSON 结构已稳定
- 已可读取真实账户 / 持仓 / 服务状态
- Dashboard 前端页面已接入并可构建

### 待增强
- performance.json 缺少历史权益曲线
- trades.json 仍可继续提高“成交”识别准确度
- bot_status.json 中 monitor_only 判断还可进一步改精确
- 页面目前只接了总览 / 持仓 / 机器人状态 / 告警
- 可考虑后续增加 dashboard-summary.json 做聚合输出

## 后续建议

优先顺序：

1. 重启生产中的网站后端 / 前端托管进程，使新 `/dashboard` 路由生效
2. 确认线上可访问：`/dashboard` 与 `/data-export/overview.json`
3. 继续补 `trades` / `performance` 卡片
4. 再决定做移动网页还是小程序
5. 若将来需要公网访问，再考虑 API / 云同步层
