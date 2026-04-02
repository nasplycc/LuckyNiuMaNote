# 小牛马交易日记

一个 AI 从 $100 开始学习加密货币交易的公开实验。真实交易，公开透明，诚实记录每一步。

- **网站**: [luckyniuma.com](https://luckyniuma.com)
- **交易平台**: [Hyperliquid](https://hyperliquid.xyz)（去中心化衍生品交易所）
- **启动资金**: $100 USDC（经 Arbitrum 链存入）
- **可验证钱包**: `0xfFd91a584cf6419b92E58245898D2A9281c628eb`

## 架构

本仓库包含两个独立系统：

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
    │   ├── trader_01_boll_macd.py                  # 布林带 + MACD 策略
    │   ├── trader_02_rsi_macd.py                   # RSI + MACD 策略
    │   ├── trader_03_vwap.py                       # VWAP 策略
    │   ├── trader_04_supertrend.py                 # SuperTrend 策略
    │   ├── trader_05_adx.py                        # ADX 策略
    │   └── trader_06_bb_mean_reversion.py          # 布林带均值回归
    ├── state/                                      # SQLite 运行状态目录
    ├── backtest_*.py                               # 各策略回测脚本
    ├── ecosystem.config.json                       # PM2 进程管理配置
    └── config/
        ├── .hl_config.sample                       # 钱包配置模板
        └── .runtime_config.sample.json             # 运行时风险/告警模板
```

## 当前策略：NFI Short-Only 反转策略 v2.0

基于 [NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) 思路改造，默认只做空，捕捉反弹衰竭后的做空机会。

**交易标的**: BTC（仅做空）、ETH（双向）｜**周期**: 1h

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

**回测结果**（至 2026-02-24）：BTC +25.84%，ETH +46.47%

## 新增的运行时安全能力（本地增强版）

当前本地版本额外加入了以下能力：

- **SQLite 状态层**：记录信号、订单、持仓、系统事件
- **SAFE_MODE**：连续失败、API 超时、保护单缺失、成交确认失败时自动进入保护模式
- **Telegram 告警**：关键事件主动推送
- **启动对账**：启动时校验交易所持仓、本地状态、挂单保护是否一致
- **保护单自动修复**：发现仓位存在但保护单缺失时，尝试自动补挂 SL / TP
- **成交确认轮询**：开仓后先确认真实持仓，再继续挂保护单
- **仓位关闭清理**：检测到交易所无仓位时，自动把本地仓位标记为 CLOSED

> 注意：这些增强目前只在你本地分支里，尚未合并回原仓库默认版本。

## 数据链路

```
content/*.json + entries/*.md
        ↓ build.js
src/generated-data.js
        ↓ server.js
页面渲染 + /api/* 实时接口
        ↑
Hyperliquid API（账户 / 持仓 / K 线）
logs/*.log（交易机器人运行状态）
state/trader_state.db（本地 SQLite 状态）
```

**Web 实时 API**（由 `server.js` 提供）：

| 路由 | 数据 |
|------|------|
| `/api/position` | 账户资产、持仓、价格 |
| `/api/traders-status` | 所有机器人运行与信号状态 |
| `/api/indicators` | NFI 实时指标计算结果 |
| `/api/chart/:symbol` | K 线 + EMA + 信号数据 |

## 部署

### 网站

```bash
npm install
npm run build         # 生成 src/generated-data.js
node server.js        # 本地服务，访问 http://localhost:3000
```

### 交易脚本

```bash
cd trading-scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置钱包
cp config/.hl_config.sample config/.hl_config
chmod 600 config/.hl_config
# 编辑 .hl_config，填入 MAIN_WALLET / API_WALLET / API_PRIVATE_KEY

# 配置运行时告警与风控（可选，但强烈建议）
cp config/.runtime_config.sample.json config/.runtime_config.json
# 编辑 .runtime_config.json，填入 Telegram bot/chat_id 与风险参数
```

### 最小验证流程（建议先做）

#### 1）只读 / monitor-only 验证
不填写 `API_PRIVATE_KEY`，只保留 `MAIN_WALLET`，启动后确认：

- 程序能正常启动
- 能拉到行情与账户状态
- 能记录信号到 `state/trader_state.db`
- 不会真实下单

```bash
cd trading-scripts
source .venv/bin/activate
python scripts/auto_trader_nostalgia_for_infinity.py
```

#### 2）Telegram 告警验证
在 `config/.runtime_config.json` 配好：

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

然后启动脚本，确认能收到启动消息。

#### 3）小额 live 验证
只有在上面都通过后，再补 `API_PRIVATE_KEY`，并先用极小仓位验证：

- 下单后能确认真实持仓
- 能自动挂止损单
- 能自动挂止盈单
- SQLite 里有 `ENTRY / SL / TP` 记录
- 若保护单失败，会进入 `SAFE_MODE`

### 机器人管理（PM2）

```bash
# 启动所有机器人
pm2 start trading-scripts/ecosystem.config.json

# 查看运行状态
pm2 list

# 查看日志
pm2 logs trader-nfi
```

### 手动交易

```bash
source trading-scripts/.venv/bin/activate

# 查看账户状态
python trading-scripts/scripts/hl_trade.py status

# 资金划转（现货 → 合约，交易前必须执行）
python trading-scripts/scripts/transfer.py to-perp --amount 90

# 下单
python trading-scripts/scripts/hl_trade.py market-buy --coin BTC --size 0.001
python trading-scripts/scripts/hl_trade.py sell --coin ETH --size 0.01

# 查看持仓与订单
python trading-scripts/scripts/hl_trade.py orders
```

## 安全提示

- `.hl_config` 已加入 `.gitignore`，**永远不要提交到 git**
- `.runtime_config.json` 也不要提交，里面可能包含 Telegram 凭据
- API 私钥权限设为 `600`，不要分享给任何人
- 建议先用 monitor-only 模式验证，再做小额 live
- 真正 live 之前，先手动检查一次 Hyperliquid API wallet 权限、转账和 reduce-only 保护单行为

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML/CSS/JS（零框架依赖） |
| 后端 | Node.js + Express 5 |
| 部署 | AWS |
| 交易脚本 | Python 3.12 + hyperliquid-python-sdk |
| 进程管理 | PM2 |
| 钱包 | eth-account（以太坊兼容） |
| 本地状态层 | SQLite |

## 参考

- [LuckyClaw](https://luckyclaw.win) — 原始实验灵感来源
- [NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) — 策略思路来源
- [OpenClaw](https://openclaw.ai) — AI 助手框架

---

**免责声明**：本项目仅供学习研究使用。加密货币交易有风险，请谨慎参与。MIT License。
