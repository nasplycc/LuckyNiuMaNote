# CHANGELOG

LuckyNiuMaNote 变更记录。

这个文件不追求完整替代 git log，而是记录**会影响实盘运行、风控链路、Dashboard 展示、告警解释口径**的关键变化，方便后续快速回溯。

---

## 记录原则

优先记录以下类型的变更：

- 实盘交易主链路改动
- SAFE_MODE / 风控恢复链路改动
- 状态层 / 导出层结构改动
- Dashboard 信息架构改动
- 服务与部署方式改动
- 会影响“如何理解当前系统状态”的关键修复

不必把纯样式微调、无影响重构、普通依赖更新全部写进来。

建议以后按下面格式追加：

```md
## YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Notes
- ...
```

---

## 2026-04-08

### Added
- 新增根目录 `CHANGELOG.md`，作为 Hyperliquid 系统的长期关键变更记录文件。

### Changed
- 根 README 与 `frontend/README.md` 已重写为基于当前真实代码结构、运行方式、导出层和前端页面结构的项目文档。
- 根 README 章节结构已与 A 股仓库统一，便于两个系统并行维护时快速对照。

### Notes
- 后续建议把“影响实盘解释口径和运行链路”的改动写入本文件，例如 SAFE_MODE、告警、导出结构、主脚本切换等。

---

## 2026-04-07

### Changed
- Hyperliquid Dashboard 完成一轮老板驾驶舱风格重构：
  - 总览优先
  - 持仓第二层
  - 次级信息折叠
  - 空状态做成完整可解释状态
- 全局新增“返回顶部”浮动按钮，并带平滑滚动与轻微呼吸光效。
- 一批状态文案改为更中性、运营视角的表达，避免把“等待机会 / 风控保护中 / 已恢复”误写成系统故障感。
- 根 README 更新为真实运行结构说明，不再沿用旧的混合型说明文档。

### Fixed
- 修复 Dashboard 白屏问题，根因是 `frontend/src/pages/DashboardPage.jsx` 中仍使用 `useState`，但导入被误删。
- 修复前一轮 Dashboard JSX 结构错误导致的 build 失败问题（包括 closing tag / unterminated expression 一类问题）。

### Notes
- 这一轮核心不是“做漂亮”，而是让页面更像可运营、可解释的实盘驾驶舱。

---

## 2026-04-05

### Changed
- SAFE_MODE 恢复链路进一步固化：
  - API 抖动（如 502 / RemoteDisconnected / SSL EOF）恢复后，系统可自动退出 SAFE_MODE。
  - Dashboard 增加“系统已恢复”提示块。
  - `safe_mode_exit` 告警以更明确的恢复态呈现。

### Fixed
- 修复“空仓 + perp equity=0 被误判为未恢复”的问题。
- 修复 SAFE_MODE 恢复提示在 Dashboard 上不够直观的问题。

### Notes
- 这轮更新的重点是：**不要因为 API 抖动后的残留状态，让系统看起来像一直没恢复**。

---

## 2026-04-02

### Changed
- 完成 `andforce/LuckyNiuMaNote` 的本地生产化加固，并推送到 fork：`nasplycc/LuckyNiuMaNote`。
- 当前正式运行方式切换为 systemd 托管，主服务为 `luckyniuma-trader.service`。
- 主交易脚本明确为：`trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`。
- 系统能力固化为：
  - SQLite 状态层
  - Telegram 告警
  - SAFE_MODE
  - 启动对账
  - 成交确认
  - 保护单自动补挂
  - 仓位关闭本地清理
  - monitor-only 兼容
  - systemd 托管

### Notes
- 这是 Hyperliquid 交易系统从“本地脚本集合”进入“生产运行形态”的关键起点。
