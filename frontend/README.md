# LuckyNiuMaNote Frontend

LuckyNiuMaNote 的 React Dashboard 前端子项目。

这个目录负责展示 Hyperliquid 交易系统的只读可视化界面，不负责直接执行交易。

---

## 1. 子项目定位

`frontend/` 的职责是：

- 展示账户总览
- 展示当前持仓与历史交易
- 展示 SAFE_MODE / 告警 / 恢复状态
- 展示图表、策略说明与运行诊断
- 提供更适合老板/运营视角查看的驾驶舱界面

它**不负责**：

- 直接下单
- 直接写入交易状态
- 替代 Python 交易脚本做风控判断

真正的交易执行发生在：

- `trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`
- 以及其他 Python 运行脚本中

---

## 2. 技术栈

- React
- React Router
- Vite
- Chart.js

这个目录只负责前端构建；实际线上页面由仓库根目录的 `server.js` 提供服务。

---

## 3. 当前页面结构

当前前端主要包含以下页面：

- `/`
- `/dashboard`
- `/trades`
- `/strategy`
- `/learn`
- `/chart`
- `/entry/:slug`

页面重点包括：

- Dashboard 首页总览
- 当前持仓与账户状态
- 历史交易与绩效表现
- 图表与指标页
- 策略说明与学习内容
- SAFE_MODE / 系统恢复提示

---

## 4. 数据来源

这个前端不直接访问 SQLite，也不承担实盘判断逻辑。

它消费的主要是：

- `/data-export/*.json`
- `server.js` 暴露的部分 API

常见数据文件包括：

- `/data-export/overview.json`
- `/data-export/positions.json`
- `/data-export/orders.json`
- `/data-export/trades.json`
- `/data-export/performance.json`
- `/data-export/alerts.json`
- `/data-export/bot_status.json`
- `/data-export/signal_diagnostics.json`
- `/data-export/meta.json`

这些数据通常由以下脚本生成：

- `trading-scripts/export-dashboard-data.py`
- `trading-scripts/generate_realtime_data.py`

---

## 5. 关键文件

```text
frontend/
├── README.md
├── package.json
├── package-lock.json
├── index.html
├── vite.config.js
└── src/
    ├── main.jsx
    ├── styles.css
    ├── components/
    ├── pages/
    └── lib/
```

### `src/main.jsx`

前端主入口，挂载 React 应用。

### `src/pages/`

页面级组件目录，通常包含：

- Dashboard
- Trades
- Strategy
- Learn
- Chart

### `src/components/`

公共 UI 组件目录，例如：

- Layout
- 卡片组件
- 汇总组件
- 导航组件

### `src/lib/`

前端数据读取与工具函数目录。

### `styles.css`

全局样式文件，负责驾驶舱整体视觉风格。

---

## 6. 本地开发

安装依赖：

```bash
cd frontend
npm install
```

启动开发模式：

```bash
npm run dev
```

默认由 Vite 提供本地开发服务。

---

## 7. 构建

```bash
cd frontend
npm run build
```

构建输出目录：

- `frontend/dist`

根目录 `server.js` 会读取这里的构建结果并提供静态服务。

---

## 8. 与根目录服务的关系

前端本身只是构建产物来源，真正提供线上访问的是仓库根目录：

- `server.js`

它负责：

- 提供 `frontend/dist` 静态资源
- 提供 `/data-export` 数据目录
- 提供部分后端 API
- 将 SPA 路由映射到 `index.html`

因此如果页面访问异常，通常要一起排查：

1. `frontend` 是否成功 build
2. `data-export/*.json` 是否成功刷新
3. `server.js` 对应服务是否运行正常

---

## 9. 前端设计原则

当前前端遵循这些原则：

1. **先给结果，再给解释**
2. **风控状态必须显眼**
3. **空状态必须看起来是正常状态，不像报错**
4. **Dashboard 是老板视角，不是工程日志面板**
5. **展示层不替代执行层做判断**

---

## 10. 修改建议

如果你后续继续改这个前端，建议：

- 先确认业务语义，再调整样式
- 不要把 SAFE_MODE 之类核心状态弱化成普通提示
- 不要让页面直接依赖 Python 内部实现细节
- 改完页面后必须重新 `npm run build`
- 页面调整尽量保持与 `data-export` 字段结构解耦

---

## 11. 相关文件建议联动阅读

如果你不是只改样式，而是要理解整个系统，建议联动阅读：

- 根目录 `README.md`
- `server.js`
- `trading-scripts/export-dashboard-data.py`
- `trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`
- `trading-scripts/scripts/risk_guard.py`

---

## 12. 注意事项

- 这个前端是 **只读展示层**
- 前端内容是否正确，取决于导出层和后端状态是否正常
- 如果页面空白、字段异常或状态不一致，优先排查：
  - build 是否最新
  - 数据导出是否最新
  - `server.js` 是否已加载新构建

不要把这里当成独立产品看待；它是整个 LuckyNiuMaNote 运行系统的展示前端，而不是孤立的 Vite 页面项目。
