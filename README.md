# LuckyNiuMaNote - Hyperliquid 交易机器人

基于 NostalgiaForInfinity 思路改造的 Hyperliquid 自动交易系统，运行于生产环境。

**当前版本**: `d57f142` (2026-04-07)  
**仓库**: [`nasplycc/LuckyNiuMaNote`](https://github.com/nasplycc/LuckyNiuMaNote)  
**实盘状态**: 运行中 · systemd 托管 · Telegram 告警

---

## 生产环境概览

| 项目 | 状态 |
|------|------|
| **交易平台** | [Hyperliquid](https://hyperliquid.xyz)（去中心化衍生品交易所） |
| **交易标的** | BTC、ETH 永续合约 |
| **启动时间** | 2026-04-02 |
| **初始资金** | ~109.80 USDC |
| **运行方式** | systemd 服务 (`luckyniuma-trader.service`) |
| **状态存储** | SQLite (`trading-scripts/state/trader_state.db`) |
| **告警通知** | Telegram Bot |
| **当前策略** | NFI Short-Only 反转策略（默认做空） |

---

## 核心能力

### 生产化安全增强

当前版本已加入以下生产级能力：

- ✅ **SQLite 状态层**：完整记录信号、订单、持仓、系统事件
- ✅ **SAFE_MODE 保护机制**：连续失败、API 超时、保护单缺失时自动进入安全模式
- ✅ **API 抖动自动恢复**：502 / RemoteDisconnected / SSL EOF 等 transient 错误自动重试，恢复后自动退出 SAFE_MODE
- ✅ **Telegram 实时告警**：开仓、平仓、止损、止盈、SAFE_MODE 进入/退出、系统恢复
- ✅ **启动对账**：启动时校验交易所持仓、本地状态、挂单保护是否一致
- ✅ **保护单自动修复**：发现仓位存在但 SL/TP 缺失时，自动补挂止损止盈单
- ✅ **成交确认轮询**：开仓后先确认真实持仓，再继续挂保护单
- ✅ **仓位关闭本地清理**：检测到交易所无仓位时，自动把本地仓位标记为 CLOSED
- ✅ **monitor-only 模式**：不填 API 私钥即可只读运行，用于验证和监控

### Dashboard 功能

| 页面 | 功能 |
|------|------|
| **Dashboard** | 账户总览、当前持仓、SAFE_MODE 状态、系统恢复提示 |
| **Trades** | 历史交易记录、盈亏统计、回放质量评分、趋势警告 |
| **Chart** | K 线 + EMA + 信号标记、NFI 实时指标 |
| **API** | `/api/position`、`/api/traders-status`、`/api/indicators`、`/api/chart/:symbol` |

---

## 架构

```
LuckyNiuMaNote/
├── content/                    # 站点内容（交易日志、策略、学习资料）
│   ├── config.json             # 站点配置与账户统计
│   ├── strategy.json           # 当前策略描述
│   ├── entries/                # 每日交易日志（Markdown）
│   └── learn/                  # 学习笔记
├── src/                        # 前端原生 JS/HTML/CSS
├── public/                     # 静态资源
├── build.js                    # 内容构建器（content/ → generated-data.js）
├── server.js                   # Express 服务器（页面路由 + 实时 API）
└── trading-scripts/
    ├── scripts/
    │   ├── auto_trader_nostalgia_for_infinity.py   # 主力自动交易机器人（当前实盘）
    │   ├── hl_trade.py                             # 手动交易 CLI
    │   ├── transfer.py                             # 现货/合约资金划转
    │   ├── market_check.py                         # 价格监控与告警
    │   ├── trailing_stop.py                        # 移动止损管理
    │   ├── state_store.py                          # SQLite 状态层
    │   ├── notifier.py                             # Telegram 告警
    │   ├── risk_guard.py                           # SAFE_MODE 与失败计数
    │   ├── reconcile.py                            # 启动对账与保护单检查
    │   └── ...                                     # 其他策略脚本
    ├── state/                                      # SQLite 运行状态目录
    │   └── trader_state.db                         # 当前运行状态数据库
    ├── backtest_*.py                               # 各策略回测脚本
    ├── ecosystem.config.json                       # PM2 进程管理配置
    └── config/
        ├── .hl_config.sample                       # 钱包配置模板
        └── .runtime_config.sample.json             # 运行时风险/告警模板
```

---

## 部署与运行

### 前置要求

- Python 3.12+
- Node.js 18+
- Hyperliquid API Wallet（需单独配置权限）

### 1. 克隆与安装

```bash
git clone https://github.com/nasplycc/LuckyNiuMaNote.git
cd LuckyNiuMaNote
git checkout master  # 生产分支

# 安装 Python 依赖
cd trading-scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 安装 Node 依赖（用于 Dashboard）
cd ..
npm install
```

### 2. 配置钱包

```bash
cd trading-scripts
cp config/.hl_config.sample config/.hl_config
chmod 600 config/.hl_config
```

编辑 `config/.hl_config`：

```ini
# 主钱包地址（用于只读监控）
MAIN_WALLET=0x...

# API 钱包地址（用于下单）
API_WALLET=0x...

# API 钱包私钥（live 交易必填，monitor-only 可不填）
API_PRIVATE_KEY=your_private_key_here
```

### 3. 配置运行时风控与告警

```bash
cp config/.runtime_config.sample.json config/.runtime_config.json
```

编辑 `config/.runtime_config.json`：

```json
{
  "telegram": {
    "bot_token": "123:abc",
    "chat_id": "123456"
  },
  "risk": {
    "max_consecutive_failures": 3,
    "max_api_timeouts": 5,
    "safe_mode_on_protection_failure": true,
    "entry_fill_timeout_sec": 20,
    "entry_fill_poll_interval_sec": 2
  }
}
```

### 4. 验证流程（强烈建议按顺序执行）

#### 阶段 1：monitor-only 验证（只读）

不填写 `API_PRIVATE_KEY`，仅验证数据拉取和状态记录：

```bash
cd trading-scripts
source .venv/bin/activate
python scripts/auto_trader_nostalgia_for_infinity.py
```

确认：
- ✅ 程序正常启动
- ✅ 能拉取行情与账户状态
- ✅ 能记录信号到 `state/trader_state.db`
- ✅ 不会真实下单

#### 阶段 2：Telegram 告警验证

配置好 `.runtime_config.json` 中的 Telegram 凭据，启动后确认能收到消息。

#### 阶段 3：小额 live 验证

仅在上述两步通过后，再填写 `API_PRIVATE_KEY`，并用极小仓位验证完整闭环。

### 5. systemd 托管（生产环境）

创建服务文件 `/etc/systemd/system/luckyniuma-trader.service`：

```ini
[Unit]
Description=LuckyNiuMaNote Hyperliquid Trader
After=network.target

[Service]
Type=simple
User=Jaben
Group=Users
WorkingDirectory=/home/Jaben/.openclaw/workspace-finnace-bot/repos/LuckyNiuMaNote/trading-scripts
Environment=PATH=/home/Jaben/.openclaw/workspace-finnace-bot/repos/LuckyNiuMaNote/trading-scripts/.venv/bin
ExecStart=/home/Jaben/.openclaw/workspace-finnace-bot/repos/LuckyNiuMaNote/trading-scripts/.venv/bin/python scripts/auto_trader_nostalgia_for_infinity.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable luckyniuma-trader.service
sudo systemctl start luckyniuma-trader.service
sudo systemctl status luckyniuma-trader.service
```

### 6. Dashboard 部署

```bash
cd /home/Jaben/.openclaw/workspace-finnace-bot/repos/LuckyNiuMaNote
npm run build
node server.js
```

访问 `http://localhost:3000` 查看 Dashboard。

---

## 当前策略：NFI Short-Only 反转策略

基于 [NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) 思路改造，默认只做空，捕捉反弹衰竭后的做空机会。

**交易标的**: BTC（仅做空）、ETH（双向）  
**周期**: 1h

### 指标体系

| 指标 | 参数 | 用途 |
|------|------|------|
| EMA 快/趋势/长期 | 20 / 50 / 200 | 趋势方向与入场锚点 |
| RSI 快速/主周期 | 4 / 14 | 超买超卖判断 |
| Bollinger Bands | 20 期，2σ | 识别反弹触顶区域 |
| ATR | 14 | 波动率驱动止损止盈 |
| Volume SMA | 30 | 过滤低流动性假信号 |

### 入场条件（做空）

- EMA50 < EMA200 且价格低于 EMA200 上方容差
- 价格触及布林上轨或反弹至 EMA20 上方
- RSI(4) > 79、RSI(14) > 62（BTC 默认值，ETH 稍有不同）
- 成交量通过过滤，价格结构出现回落确认

### 风控参数

| 参数 | 值 |
|------|----|
| 最大杠杆 | 3x（默认 2x） |
| 单笔最大持仓 | $294 |
| ATR 止损倍数 | BTC 2.4x / ETH 2.8x |
| ATR 止盈倍数 | BTC 4.0x / ETH 2.8x |
| 开仓冷却期 | 4 小时 |
| 最大同时持仓 | 2 个 |
| 手续费后最低利润 | 0.5% |

---

## 手动交易 CLI

```bash
cd trading-scripts
source .venv/bin/activate

# 查看账户状态
python scripts/hl_trade.py status

# 资金划转（现货 → 合约）
python scripts/transfer.py to-perp --amount 90

# 下单
python scripts/hl_trade.py market-buy --coin BTC --size 0.001
python scripts/hl_trade.py sell --coin ETH --size 0.01

# 查看持仓与订单
python scripts/hl_trade.py orders
```

---

## 安全提示

⚠️ **重要**：

- `.hl_config` 和 `.runtime_config.json` 已加入 `.gitignore`，**永远不要提交到 git**
- API 私钥权限设为 `600`，不要分享给任何人
- 建议先用 monitor-only 模式验证，再做小额 live
- 真正 live 之前，先手动检查一次 Hyperliquid API wallet 权限、转账和 reduce-only 保护单行为

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML/CSS/JS（零框架依赖） |
| 后端 | Node.js + Express 5 |
| 交易脚本 | Python 3.12 + hyperliquid-python-sdk |
| 进程管理 | PM2 / systemd |
| 状态存储 | SQLite |
| 钱包 | eth-account（以太坊兼容） |

---

## 参考

- [NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) — 策略思路来源
- [OpenClaw](https://openclaw.ai) — AI 助手框架
- [LuckyClaw](https://luckyclaw.win) — 原始实验灵感来源

---

**免责声明**：本项目仅供学习研究使用。加密货币交易有风险，请谨慎参与。

**License**: MIT
