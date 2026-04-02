# UPSTREAM_SYNC.md

# LuckyNiuMaNote 上游同步说明

这份文档用于说明：**如何同步 `andforce/LuckyNiuMaNote` 的上游更新，同时不丢失当前 fork 中已经落地的生产化增强。**

---

## 当前仓库关系

- 当前本地仓库：`/home/Jaben/.openclaw/workspace-finnace-bot/repos/LuckyNiuMaNote`
- 当前 fork：`https://github.com/nasplycc/LuckyNiuMaNote.git`
- 上游仓库：`https://github.com/andforce/LuckyNiuMaNote.git`

推荐始终保持两个 remote：

- `origin` = 自己的 fork
- `upstream` = 原项目

可用以下命令确认：

```bash
git remote -v
```

理想输出应包含类似：

```bash
origin   https://github.com/nasplycc/LuckyNiuMaNote.git (fetch)
origin   https://github.com/nasplycc/LuckyNiuMaNote.git (push)
upstream https://github.com/andforce/LuckyNiuMaNote.git (fetch)
upstream https://github.com/andforce/LuckyNiuMaNote.git (push)
```

---

## 当前 fork 中不能丢失的增强

同步上游前，先记住：下面这些是当前仓库中**优先级很高、不能被上游覆盖掉**的生产化增强。

### 关键能力

- SQLite 状态层
- Telegram 告警
- SAFE_MODE 风控保护
- 启动对账（reconciliation）
- 成交确认（entry fill confirmation）
- 缺失保护单自动补挂
- 关闭仓位后的本地状态清理
- monitor-only 模式兼容
- 本地 runtime 配置体系
- `systemd` 服务化运行

### 关键文件 / 关键模块

重点关注：

- `trading-scripts/scripts/state_store.py`
- `trading-scripts/scripts/notifier.py`
- `trading-scripts/scripts/risk_guard.py`
- `trading-scripts/scripts/reconcile.py`
- `trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py`
- `trading-scripts/config/.runtime_config.sample.json`
- `trading-scripts/run_nfi_local.sh`
- `README.md`

### 当前重要提交

- `6c45724` — `Harden NFI trader for safer live operation`

后续任何同步动作，都应重点检查这些能力是否还在。

---

## 推荐同步原则

### 1. 不要直接覆盖

不要用“直接复制上游代码覆盖本地仓库”的方式同步。  
正确做法是使用：

- `git fetch`
- `git merge`
- 或者选择性摘取上游改动

### 2. 不要直接在 `main` 上试

同步上游时，先创建临时同步分支，再测试，再回合到 `main`。

### 3. 优先模块化保留自有增强

如果上游改动较大，优先保留以下模块化增强：

- `state_store.py`
- `notifier.py`
- `risk_guard.py`
- `reconcile.py`

这样即使主策略文件变化较大，生产化增强也更容易继续接上。

---

## 标准同步流程

### 第一步：进入仓库

```bash
cd /home/Jaben/.openclaw/workspace-finnace-bot/repos/LuckyNiuMaNote
```

### 第二步：抓取最新远程信息

```bash
git fetch origin
git fetch upstream
```

### 第三步：确保本地主分支是最新 fork 状态

```bash
git checkout main
git pull origin main
```

### 第四步：创建同步分支

```bash
git checkout -b sync-upstream-YYYYMMDD
```

例如：

```bash
git checkout -b sync-upstream-20260403
```

### 第五步：合并上游

```bash
git merge upstream/main
```

如果无冲突，进入测试环节。  
如果有冲突，优先人工处理，不要盲目接受全部上游版本。

---

## 冲突处理原则

### 优先保留的内容

以下内容通常应优先保留或人工融合：

- `StateStore`
- `TelegramNotifier`
- `RiskGuard`
- `reconcile_exchange_state(...)`
- `wait_for_entry_fill(...)`
- `ensure_protection_orders(...)`
- `attempt_repair_protection()`
- `refresh_position_states()`
- monitor-only / live 模式兼容逻辑
- runtime config 加载逻辑

### 可以积极吸收的上游内容

如果上游更新的是这些，通常值得优先看：

- 策略参数优化
- 指标阈值优化
- 新的过滤条件
- 选币/信号改进
- 非破坏性 bug 修复

### 需要谨慎吸收的上游内容

如果上游更新的是这些，要更谨慎：

- 主交易脚本整体重构
- 下单执行层大改
- 目录结构重构
- 配置方式大改
- 状态管理方式重写

因为这些最容易把当前的生产加固层撞掉。

---

## 合并后必须做的验证

同步上游后，不要直接推送，也不要直接长期开实盘。  
必须先做本地验证。

### 1. 语法检查

```bash
python3 -m py_compile \
  trading-scripts/scripts/state_store.py \
  trading-scripts/scripts/notifier.py \
  trading-scripts/scripts/risk_guard.py \
  trading-scripts/scripts/reconcile.py \
  trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py
```

### 2. monitor-only 启动验证

可临时移走或注释 `API_PRIVATE_KEY`，确认：

- 程序能启动
- 不会下单
- 不会因 monitor-only 的 reconciliation 误触发 SAFE_MODE

### 3. live 配置加载验证

恢复 live 配置后，确认：

- `API_PRIVATE_KEY` 能正常读取
- 启动对账通过
- 进入主循环
- Telegram 告警可正常使用

### 4. 服务验证

```bash
sudo systemctl restart luckyniuma-trader
sudo systemctl status luckyniuma-trader --no-pager -l
journalctl -u luckyniuma-trader -n 50 --no-pager
```

### 5. 日志验证

```bash
tail -n 100 logs/trader_nfi.log
```

重点确认是否出现：

- 启动成功
- reconciliation 正常
- 无异常 traceback
- 无 SAFE_MODE 误触发

---

## 验证通过后的回合流程

如果同步分支验证通过：

### 合回 main

```bash
git checkout main
git merge sync-upstream-YYYYMMDD
```

### 推送到 fork

```bash
git push origin main
```

---

## 如果上游变化太大，建议改为“选择性吸收”

如果 `git merge upstream/main` 冲突很多，或者你发现上游改动会明显冲击当前稳定运行逻辑，不要强行整体合并。

这时建议：

### 先看差异

```bash
git diff main..upstream/main
```

### 看某个文件差异

```bash
git diff main..upstream/main -- trading-scripts/scripts/auto_trader_nostalgia_for_infinity.py
```

### 只摘取有价值的文件或逻辑

例如：

```bash
git checkout upstream/main -- path/to/file
```

然后再人工融合到当前 fork 中。

也可以直接人工把上游策略参数或条件摘过来，而不吸收它对执行层的大改动。

---

## 推荐维护策略

### 情况 A：上游只是小幅优化策略参数

建议同步，成本低，收益高。

### 情况 B：上游新增过滤条件或修 bug

建议先在同步分支合并并验证，再决定是否进 `main`。

### 情况 C：上游重构了主交易脚本

建议不要盲 merge。优先做：

- 读 diff
- 分析收益点
- 选择性吸收
- 保住现有生产能力

---

## 以后如果让 AI 帮你同步，建议这样说

固定描述建议：

> 继续看 LuckyNiuMaNote 的 Hyperliquid 交易机器人，我要同步 upstream 更新，但不能丢掉我们现在的生产加固。

这样 AI 应优先理解为：

- 要同步 `andforce/LuckyNiuMaNote`
- 但要保留当前 fork 中的 live 风控与运维增强
- 应优先采用“同步分支 + diff + 测试 + 合并”的方式，而不是覆盖式替换

---

## 一句话原则

> 上游负责提供可吸收的策略改进；当前 fork 负责保证实盘安全、状态管理、风控与运维能力。同步时优先保住后者，再有选择地吸收前者。
