# LuckyNiuMaNote

Hyperliquid 实盘交易系统与只读 Dashboard 仓库。

这个仓库不是单纯的前端项目，也不是单纯的策略实验目录，而是一套围绕 **Hyperliquid 永续合约交易、实盘风控、运行状态持久化、只读可视化展示** 组织起来的代码集合。

当前仓库包含：

- 实盘交易机器人
- 多个策略脚本与回测脚本
- SQLite 状态层
- SAFE_MODE 风控保护机制
- Telegram 告警
- Dashboard 数据导出层
- React 前端看板
- Node/Express Web 服务
- systemd / nginx / 部署相关文件

项目目标不是“演示一个交易页面”，而是把 **交易执行、运行状态、风控保护、展示层、部署文件** 固化到同一个仓库里，形成可运行、可观察、可恢复的 Hyperliquid 交易系统。

---

## 1. 项目定位

当前仓库的定位是：

- **Hyperliquid 永续合约交易系统**
- **实盘运行中的交易机器人仓库**
- **运行状态与风控中台**
- **只读 Dashboard 展示层**

它强调的是：

1. **交易脚本不是裸跑**，而是带状态层、保护机制、恢复逻辑
2. **运行状态可观测**，不是只靠日志肉眼看
3. **Dashboard 是只读展示层**，不直接承担交易执行
4. **SAFE_MODE 是核心保护机制**，不是装饰字段
5. **开发仓 = GitHub 仓 = 运行仓**，减少线上线下漂移

---

## 2. 当前核心能力

### 2.1 实盘交易机器人

当前主实盘脚本：

- `trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`

该脚本负责：

- 拉取 Hyperliquid 市场数据与账户状态
- 基于 NFI（NostalgiaForInfinity-inspired）逻辑生成信号
- 执行开仓 / 平仓 / 保护单管理
- 监控异常状态并触发 SAFE_MODE
- 与本地状态层、告警系统联动

### 2.2 SAFE_MODE 保护机制

当前系统已把 SAFE_MODE 固化到运行链路中。触发场景包括但不限于：

- 连续 API 异常
- 下单后未确认真实持仓
- 持仓数量异常
- 止损 / 止盈保护单挂单失败
- 启动对账失败
- 持仓保护状态异常
- 账户回撤达到风险阈值

系统还包含若干自动恢复逻辑，例如：

- API 恢复后自动退出 SAFE_MODE
- 保护单修复成功后自动退出 SAFE_MODE
- 检测到无实际持仓时清除残留 SAFE_MODE

### 2.3 SQLite 状态层

当前系统已具备 SQLite 状态持久化能力，核心代码位于：

- `trading-scripts/scripts/state_store.py`

状态层用于：

- 记录信号
- 记录订单与持仓状态
- 记录系统事件
- 记录 SAFE_MODE 相关状态
- 为 Dashboard 导出层提供统一读取来源

### 2.4 Telegram 告警

当前系统通过：

- `trading-scripts/scripts/notifier.py`

向 Telegram 发送运行告警，例如：

- 开仓 / 平仓
- SAFE_MODE 进入
- SAFE_MODE 恢复
- 启动对账告警
- API 恢复提示
- 保护单修复完成提示

### 2.5 Dashboard 只读展示层

当前仓库内的 Dashboard 用于展示：

- 账户总览
- 当前持仓
- 历史交易
- 告警与运行状态
- SAFE_MODE / 系统恢复状态
- 策略与诊断信息
- 图表与指标页

前端技术栈：

- React
- React Router
- Vite

Web 服务：

- Node.js
- Express

### 2.6 Dashboard 数据导出层

当前 Dashboard 不直接读交易脚本内部对象，而是消费导出后的 JSON 数据。

相关脚本：

- `trading-scripts/export-dashboard-data.py`
- `trading-scripts/generate_realtime_data.py`

导出结果位于：

- `data-export/overview.json`
- `data-export/positions.json`
- `data-export/orders.json`
- `data-export/trades.json`
- `data-export/performance.json`
- `data-export/alerts.json`
- `data-export/bot_status.json`
- `data-export/signal_diagnostics.json`
- `data-export/meta.json`

---

## 3. 项目目录说明

```text
LuckyNiuMaNote/
├── README.md
├── package.json
├── package-lock.json
├── server.js                         # Node/Express Web 服务入口
├── build.js                          # 内容构建脚本
├── deploy.sh                         # 部署脚本
├── daily_report.sh                   # 日报相关脚本
├── content/                          # 页面内容与策略说明
│   ├── config.json
│   └── strategy.json
├── data-export/                      # Dashboard JSON 导出结果
├── public/                           # 静态资源
├── frontend/                         # React Dashboard 前端
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── src/
│   └── README.md
├── infra/                            # systemd / nginx / 部署配置参考
│   ├── luckyniuma-backend.service
│   ├── luckyniuma-dashboard-refresh.nas.service
│   └── nginx-luckyniuma.conf
├── logs/                             # 运行日志与交易日志
├── scripts/                          # 其他部署辅助脚本
├── src/                              # 旧站点/内容侧 JS 代码
├── trading-scripts/                  # 交易系统主目录
│   ├── requirements.txt
│   ├── export-dashboard-data.py
│   ├── generate_realtime_data.py
│   ├── realtime_data_cron.sh
│   ├── run_auto_trader.sh
│   ├── manage_bots.sh
│   ├── ecosystem.config.json
│   ├── state/
│   │   └── trader_state.db
│   ├── config/
│   │   ├── .hl_config.sample
│   │   └── .runtime_config.sample.json
│   ├── scripts/
│   │   ├── auto_trader_nostalgia_for_infinity.py
│   │   ├── notifier.py
│   │   ├── risk_guard.py
│   │   ├── reconcile.py
│   │   ├── state_store.py
│   │   ├── hl_trade.py
│   │   ├── transfer.py
│   │   ├── trailing_stop.py
│   │   └── trader_01~06_*.py
│   ├── backtest_*.py
│   └── test_*.py
├── DEPLOY.md
├── PROJECT_OVERVIEW.md
└── UPSTREAM_SYNC.md
```

---

## 4. 核心运行逻辑

### 4.1 交易主程序 + 状态层 + 导出层 + 前端

系统可以理解为四层：

1. **交易执行层**
   - `auto_trader_nostalgia_for_infinity.py`
   - 其他策略脚本

2. **状态与风控层**
   - `state_store.py`
   - `risk_guard.py`
   - `reconcile.py`
   - SQLite 数据库 `trader_state.db`

3. **导出层**
   - `export-dashboard-data.py`
   - `generate_realtime_data.py`
   - 导出到 `data-export/*.json`

4. **展示层**
   - `frontend/`
   - `server.js`
   - Dashboard 页面与 API

### 4.2 Dashboard 是展示层，不是交易执行层

虽然这个仓库里有前端与 Web 服务，但交易逻辑并不在 React 页面里执行。

Dashboard 负责：

- 展示账户与持仓
- 展示历史交易与性能
- 展示 SAFE_MODE / 风控状态
- 展示图表与策略信息

真正的执行与状态判断发生在 Python 交易脚本与状态层中。

### 4.3 数据导出是中间桥梁

前端消费的是 `data-export/*.json`，不是直接读 SQLite，也不是直接连 Hyperliquid API。

这使得：

- 前端更稳定
- 展示层和执行层边界清晰
- 页面结构调整不会直接干扰实盘交易逻辑

---

## 5. 当前系统硬规则与约束

### 5.1 SAFE_MODE 是核心保护机制

SAFE_MODE 不是页面上的一个提示文案，而是运行层真实存在的保护状态。

当系统检测到：

- 交易执行链路异常
- API 异常持续
- 持仓与本地状态不一致
- 保护单缺失或修复失败
- 账户风险超阈值

系统会进入 SAFE_MODE，阻断继续交易或转入保护流程。

### 5.2 启动对账已固化

当前系统启动时会做对账与状态核验，相关逻辑见：

- `trading-scripts/scripts/reconcile.py`

这一步用于避免：

- 交易所实际持仓和本地状态漂移
- 保护单状态缺失
- 重启后误判无仓 / 漏单

### 5.3 保护单自动补挂已固化

当前系统不仅会在开仓后尝试挂保护单，还会：

- 检查止损 / 止盈是否缺失
- 在条件允许时尝试自动补挂
- 修复成功后自动清理相关 SAFE_MODE

### 5.4 monitor-only 模式已支持

系统支持 monitor-only 模式，即：

- 不做真实下单
- 只运行监控、信号、状态记录和告警链路

这适合：

- 新环境验证
- 新参数观察
- 部署前健康检查

---

## 6. Dashboard 数据流

当前数据流大致如下：

```text
Hyperliquid API / 账户状态 / 行情
        │
        ▼
trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py
        │
        ├── notifier.py
        ├── risk_guard.py
        ├── reconcile.py
        └── state_store.py → SQLite
        │
        ▼
trading-scripts/export-dashboard-data.py
trading-scripts/generate_realtime_data.py
        │
        ▼
data-export/*.json
        │
        ▼
frontend/src/* + server.js
        │
        ▼
只读 Dashboard 页面 / API
```

---

## 7. 本地开发与运行

### 7.1 安装 Node 依赖

根目录：

```bash
npm install
```

前端目录：

```bash
cd frontend
npm install
```

### 7.2 构建 Dashboard

在仓库根目录：

```bash
npm run build
```

这条命令会执行：

- 内容构建
- 前端构建

### 7.3 前端开发模式

```bash
npm run dev:frontend
```

### 7.4 启动 Web 服务

```bash
node server.js
```

默认端口：

- `3000`

### 7.5 Python 交易环境

```bash
cd trading-scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 8. 交易脚本运行

### 8.1 主交易脚本

当前主脚本：

```bash
cd trading-scripts
source .venv/bin/activate
python scripts/auto_trader_nostalgia_for_infinity.py
```

也可以通过已有包装脚本启动：

- `run_auto_trader.sh`
- `run_nfi_local.sh`
- `start_trader.sh`

### 8.2 其他策略脚本

仓库里还保留了其他策略实现，例如：

- `trader_01_boll_macd.py`
- `trader_02_rsi_macd.py`
- `trader_03_vwap.py`
- `trader_04_supertrend.py`
- `trader_05_adx.py`
- `trader_06_bb_mean_reversion.py`

这些可用于：

- 对比策略
- 独立实验
- 回测与观察

但当前实盘主线应以你实际运行的主脚本为准。

---

## 9. 配置与敏感文件

仓库中与配置相关的重要路径：

- `trading-scripts/config/.hl_config`
- `trading-scripts/config/.hl_config.sample`
- `trading-scripts/config/.runtime_config.json`
- `trading-scripts/config/.runtime_config.sample.json`

一般来说：

- `.sample` 文件用于模板
- 真实密钥 / 钱包 / 告警配置应放在本地实际配置文件中

使用前请自行确认：

- API 钱包权限
- 风险参数
- Telegram 配置
- 是否处于 monitor-only 模式

---

## 8. 生产运行相关文件

当前仓库中已包含若干基础设施文件：

- `infra/luckyniuma-backend.service`
- `infra/luckyniuma-backend.nas.service`
- `infra/luckyniuma-dashboard-refresh.nas.service`
- `infra/nginx-luckyniuma.conf`
- `deploy.sh`
- `scripts/setup-https.sh`

这些文件反映了项目的真实生产部署方式：

- backend / Web 服务常驻
- dashboard 数据定期或触发刷新
- 可配合 nginx 暴露页面
- 支持本地 NAS / Linux 环境部署

> 注意：不同机器上的真实 service 名、部署路径、用户、端口和反向代理配置可能不同，使用前请按当前机器实际情况核对。

---

## 9. 当前前端页面结构

当前前端为 React SPA，主要页面包括：

- `/`
- `/dashboard`
- `/trades`
- `/strategy`
- `/learn`
- `/chart`
- `/entry/:slug`

当前 Web 服务也暴露了若干 API 路径，例如：

- `/api/trader-status`
- `/api/traders-status`
- 以及其他图表 / 指标 / 账户状态相关接口

整体展示定位是：

- 总览优先
- 风险状态优先
- 当前持仓优先
- 告警与恢复状态清晰可见
- 次级说明后置

---

## 10. 关键脚本说明

### `trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`

当前主实盘机器人：

- 获取行情
- 计算信号
- 执行开平仓
- 管理保护单
- 处理 SAFE_MODE
- 与 SQLite / Telegram / 对账逻辑联动

### `trading-scripts/scripts/state_store.py`

SQLite 状态层：

- 负责持久化交易与系统状态
- 为风控和 dashboard 导出提供统一状态来源

### `trading-scripts/scripts/risk_guard.py`

SAFE_MODE 与风险计数逻辑：

- 负责进入 / 退出 SAFE_MODE
- 负责记录风险状态与保护状态

### `trading-scripts/scripts/reconcile.py`

启动对账与保护状态校验：

- 检查交易所状态与本地状态是否一致
- 发现问题时输出告警或触发保护机制

### `trading-scripts/scripts/notifier.py`

Telegram 告警发送器：

- 将关键运行事件推送到 Telegram

### `trading-scripts/export-dashboard-data.py`

Dashboard 导出层：

- 从 SQLite / 日志 / 运行状态生成 JSON
- 输出给前端页面消费

### `server.js`

Node/Express 服务：

- 提供 React SPA 页面
- 提供 `/data-export` 静态数据
- 提供运行状态 API
- 对 Hyperliquid 接口做部分读取与指标计算支持

---

## 11. 适合谁用

这个仓库更适合：

- 已经在 Hyperliquid 上做实盘或准实盘交易
- 希望把交易逻辑、风控、状态展示固化到一个仓库
- 需要 SAFE_MODE / 对账 / 告警这类生产化能力
- 需要一个只读 dashboard 快速查看运行状态

它不适合：

- 作为通用量化平台模板直接套用
- 作为完整的多交易所聚合框架
- 作为单纯的前端页面项目

---

## 12. 维护建议

如果后续继续演进，建议遵守以下原则：

1. **实盘逻辑优先稳定，不要为了页面改动去冒险动执行链路**
2. **SAFE_MODE 与对账逻辑属于高优先级，不要轻易弱化**
3. **前端只做展示，不要把执行判断偷偷搬进页面层**
4. **导出层保持中间层角色，避免前端直接耦合 SQLite 细节**
5. **生产改动前先 monitor-only 验证，再小额 live 验证**

---

## 13. 相关文档建议阅读顺序

如果你是第一次接手这个仓库，推荐按这个顺序读：

1. `README.md`
2. `PROJECT_OVERVIEW.md`
3. `DEPLOY.md`
4. `trading-scripts/README.md`
5. `trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`
6. `trading-scripts/scripts/risk_guard.py`
7. `trading-scripts/scripts/reconcile.py`
8. `trading-scripts/export-dashboard-data.py`
9. `server.js`
10. `frontend/src/`

---

## 14. 免责声明

本仓库用于交易执行、状态展示与决策支持。

- 不构成投资建议
- 不保证收益
- 不替代人工风险判断
- 在任何实盘环境中使用前，都应自行确认：
  - 钱包与 API 权限
  - 风控参数
  - 杠杆与仓位设置
  - SAFE_MODE / 告警 / 对账链路是否正常

---

## 15. 当前仓库边界

本仓库只负责 **Hyperliquid / LuckyNiuMaNote 系统**。

明确不包含：

- A 股交易系统代码
- workspace 中的私有身份文件
- 其他无关实验项目的长期维护逻辑

如果你在找的是 A 股系统，请到 `LuckyniumaA` 仓库，不要在这里混改。
