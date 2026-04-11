# MEMORY.md - LuckyNiuMaNote 长期记忆

## Y(4.0) 委员会投票系统（完整参数记录）

### 📊 Y(4.0) 策略来源
- **TradingView Script**: https://cn.tradingview.com/script/Mr7em8sC/
- **作者**: nudaez
- **版本**: v4.0
- **核心**: 8组件投票委员会 + 3层决策架构

---

## 完整Pine Script参数（原版）

### Layer 1: 投票委员会参数

#### 1. RSI
```
rsiLen = 14           # RSI周期
rsiOS = 30            # 超卖阈值
rsiOB = 70            # 超买阈值
rsiWarn = 8           # 缓冲区
rsiDeep = 8           # 深度区
```

#### 2. Stochastic
```
stK = 14              # %K周期
stD = 3               # %D周期
stSmooth = 3          # 平滑
stOS = 20             # 超卖阈值
stOB = 80             # 超买阈值
stDeep = 8            # 深度区
```

#### 3. Bollinger Bands
```
bbLen = 20            # BB周期
bbMult = 2.0          # 标准差倍数
bbDeepPct = 0.15      # 深度比例 (15%)
```

#### 4. CCI
```
cciLen = 20           # CCI周期
cciDeep = 200         # 深度阈值 (±200)
cciMid = 100          # 中等阈值 (±100)
cciLight = 50         # 轻度阈值 (±50)
```

#### 5. Williams %R
```
wrLen = 14            # 周期
wrDeep = 95           # 深度阈值 (-95/-5)
wrMid = 80            # 中等阈值 (-80/-20)
wrLight = 65          # 轻度阈值 (-65/-35)
```

#### 6. MFI
```
mfiLen = 14           # MFI周期
mfiDeep = 15          # 深度阈值 (15/85)
mfiMid = 20           # 中等阈值 (20/80)
mfiLight = 30         # 轻度阈值 (30/70)
```

#### 7. ADX/DI
```
adxLen = 14           # ADX周期
adxStrong = 25        # 强趋势阈值
adxRising = 3         # ADX上升确认（最近3bar）
```

#### 8. Divergence（背离）
```
divLookback = 5       # Pivot Lookback
divExpiry = 8         # 有效期（bar）
divFreshBar = 3       # 新鲜背离bar数（3分需要）
```

---

### Layer 2: 成交量支撑倍数
```
volLen = 20           # 成交量平均周期
volSpikeMult = 1.5    # Spike倍数
volStrongMult = 2.5   # 强Spike倍数
volBoostWeak = 1.15   # 弱Spike倍数（增强）
volBoostStrong = 1.25 # 强Spike倍数（增强）
```

---

### Layer 3: 趋势过滤器
```
useTrendFilter = false  # 趋势过滤开关
emaFastLen = 8          # 快EMA
emaSlowLen = 21         # 慢EMA
emaTrendLen = 50        # 趋势EMA
```

---

### 出场系统参数

#### Trailing Stop（Score + ATR集成）
```
useTrailing = true       # Trail开关
trailActivation = 1.5    # 激活盈利(%)
trailPercent = 0.7       # 回撤(%)
trailTightenRate = 0.5    # Score收紧率
trailLoosenRate = 0.2     # Score放宽率
trailATRlen = 14         # ATR周期
trailATRweight = 0.3     # ATR权重 (0=无, 1=全)
```

#### Breakeven保护（3阶段）
```
useBreakeven = true      # BE开关
bePhase2pct = 0.5        # Phase 2: 激活(%)
bePhase3pct = 1.0        # Phase 3: 激活(%)
bePhase3lock = 0.3       # Phase 3: 锁定盈利(%)
```

---

### 辅助模块参数

#### Re-Entry v3
```
useReEntry = true        # RE开关
reCooldownBars = 5       # 冷却时间(bar)
rePullbackPct = 0.5      # 最小回踩深度(%)
reMaxEntries = 3         # 最大重入场次数
reMinVoters = 3          # 最少激活组件
reMaxBarsWindow = 80     # 时间窗口(bar)
```

#### Pullback v2
```
usePullbackEntry = false # PB开关
pbMinVoters = 2          # 最少激活组件
pbBounceBar = 2          # 回弹确认bar
pbMaxDist = 0.3          # 最大EMA距离(%)
pbSLratio = 0.65         # SL压缩比 (65%)
```

---

## Python融合版本参数

### 融合策略参数调整
| 参数 | Y原版 | Python融合版 | 说明 |
|------|-------|--------------|------|
| min_active_components | 5/8 | 5/8 | 保持一致 |
| min_total_score | 10/24 | 10/24 | 保持一致 |
| rsi_fast_buy | 30 (Y) | 38 (NFI) | NFI更宽松 |
| volume_threshold | 无独立阈值 | 20% | NFI新增门槛 |

### 融合逻辑
```python
# NFI信号触发 → Y委员会验证
if nfi_signal_triggered:
    y_vote = y_committee_vote(...)
    
    if y_vote.passed and y_vote.direction == nfi_side:
        confidence += 0.15  # 方向匹配增强
    elif y_vote.passed and y_vote.direction != nfi_side:
        confidence -= 0.10  # 方向冲突警告
    else:
        confidence -= 0.05  # 未通过轻微降低
```

### 评分逻辑详解（Pine Script原版）

#### 1. RSI评分 (0-3分)
```
# Deep超卖: RSI < 30-8 = 22 → 3分
# 中度超卖: RSI < 30 → 2分
# 轻度超卖: RSI < 30+8 = 38 → 1分
```

#### 2. Stochastic评分 (0-3分)
```
# 金叉+深度超卖: K上穿D + K < 20-8 = 12 → 3分
# 金叉+超卖: K上穿D + K < 20 → 2分
# 金叉+低位: K上穿D + K < 35 → 1分
# 双超卖: K<20 + D<20 → 1分
# 单超卖: K<20 → 1分
```

#### 3. Bollinger Bands评分 (0-3分)
```
# 显著跌破: close < bb_lower - (bb_width * 15%) → 3分
# 跌破: close < bb_lower → 2分
# 触及下轨区: close < bb_lower + (bb_mid-bb_lower)*30% → 1分
```

#### 4. CCI评分 (0-3分)
```
# 深度超卖: CCI < -200 → 3分
# 中度超卖: CCI < -100 → 2分
# 轻度超卖: CCI < -50 → 1分
```

#### 5. Williams %R评分 (0-3分)
```
# 深度超卖: WR < -95 → 3分
# 中度超卖: WR < -80 → 2分
# 轻度超卖: WR < -65 → 1分
```

#### 6. MFI评分 (0-3分)
```
# 深度流出: MFI < 15 → 3分
# 中度流出: MFI < 20 → 2分
# 轻度流出: MFI < 30 → 1分
```

#### 7. ADX/DI评分 (0-3分)
```
# 强趋势+交叉: ADX>25 + DI方向交叉 → 高分
# 中等趋势: ADX>25 → 中等分
# 弱趋势: ADX>20 → 低分
```

#### 8. Divergence评分 (0-3分)
```
# 强背离: 背离检测在最近3bar内 → 3分
# 活跃背离: 背离在最近8bar内 → 有效
# 看涨背离: 价格新低 + RSI未新低 + RSI<50
# 看跌背离: 价格新高 + RSI未新高 + RSI>50
```

### 总分计算逻辑
```python
# 做多总分 (dip)
dipRaw = rsiDipPts + stDipPts + bbDipPts + cciDipPts + wrDipPts + mfiDipPts + adxDipPts + divDipPts
# 做空总分 (peak)
peakRaw = rsiPeakPts + stPeakPts + bbPeakPts + cciPeakPts + wrPeakPts + mfiPeakPts + adxPeakPts + divPeakPts

# 激活组件计数
dipVoters = sum(1 for pts in [rsiDipPts, stDipPts, bbDipPts, cciDipPts, wrDipPts, mfiDipPts, adxDipPts, divDipPts] if pts >= 1)
peakVoters = sum(1 for pts in [rsiPeakPts, stPeakPts, bbPeakPts, cciPeakPts, wrPeakPts, mfiPeakPts, adxPeakPts, divPeakPts] if pts >= 1)

# 成交量倍数调整
dipScoreEff = dipRaw * volMultiplier
peakScoreEff = peakRaw * volMultiplier

maxScore = 24  # 8组件 × 3分
```

### ATR集成Trail计算
```python
# ATR动态调整Trail参数
trailATR = ATR(14)
trailATRavg = SMA(trailATR, 50)
atrScale = trailATR / trailATRavg  # 当前ATR相对平均ATR的比例
atrClamped = max(0.5, min(2.0, atrScale))  # 限制在0.5-2.0之间
atrFactor = 1.0 + (atrClamped - 1.0) * trailATRweight  # ATR权重混合

# 基础Trail参数 × ATR因子
baseTrailAct = trailActivation * atrFactor  # Trail激活盈利
baseTrailPct = trailPercent * atrFactor    # Trail回撤百分比
```

### ATR权重影响
- `trailATRweight = 0.0`: Trail完全基于原始参数，不考虑ATR
- `trailATRweight = 1.0`: Trail完全跟随ATR波动
- 推荐: `0.3` (30% ATR权重)

### Score动态Trail
```python
# Score收紧: 当反向score增加，Trail收紧
# Score放宽: 当自己score强，Trail放宽
if oppositeScore > 0:
    trailPct *= (1 - trailTightenRate * oppositeScore/24)
if selfScore > minTotalScore:
    trailPct *= (1 + trailLoosenRate * selfScore/24)
```

### Re-Entry v3逻辑
```python
# 退出后追踪高低点，等待回踩确认
# Long Re-Entry条件:
#   1. 上次退出方向=Long
#   2. 回踩深度 >= rePullbackPct (0.5%)
#   3. EMA确认: close > emaFast and close > emaSlow
#   4. dipVoters >= reMinVoters (3)
#   5. 冷却时间 >= reCooldownBars (5)
#   6. 重入场次数 < reMaxEntries (3)
#   7. 时间窗口 <= reMaxBarsWindow (80)
```

### Pullback v2逻辑
```python
# ADX强趋势中EMA回弹入场
# Long Pullback条件:
#   1. ADX >= adxStrong (25)
#   2. 价格接近EMA: |close - emaSlow| <= pbMaxDist (0.3%)
#   3. 回弹确认: 连续pbBounceBar根阳线
#   4. pbMinVoters >= 2
#   5. 止损压缩: SL = normal_SL * pbSLratio (0.65)
```

### 统一入场决策
```python
# 三种入场信号类型:
#   normalDipSig: 标准委员会投票信号
#   reEntryLong: Re-Entry v3信号
#   pullbackLongSig: Pullback v2信号

# 入场优先级: normal > RE > PB
# Entry ID命名:
#   "LONG": 标准信号
#   "RE Long": Re-Entry信号
#   "PB Long": Pullback信号
```

### Score-集成Trail计算
```python
# 反向Score影响Trail收紧
counterScoreNorm = peakRaw / maxScore  # Long仓的反向是peak
ownScoreNorm = dipRaw / maxScore       # Long仓的自己是dip

scoreFactor = 1.0 - counterScoreNorm * trailTightenRate + ownScoreNorm * trailLoosenRate
scoreFactor = max(0.15, min(1.5, scoreFactor))

effTrailPct = baseTrailPct * scoreFactor
```

### Breakeven三阶段保护
```python
# Phase 2 (盈利0.5%): SL移至entryPrice
# Phase 3 (盈利1.0%): SL锁定0.3%盈利
if curProfit >= bePhase3pct (1.0%):
    slPrice = entryPrice * (1 + bePhase3lock/100)  # 锁定0.3%
elif curProfit >= bePhase2pct (0.5%):
    slPrice = entryPrice  # 保本
```

### Webhook JSON格式
```json
// 开多
{"action":"open_long","ticker":"BTC","price":"84000","score":"12","voters":"6"}
// 平多
{"action":"close_long","ticker":"BTC","price":"85000"}
// 开空
{"action":"open_short","ticker":"ETH","price":"3200","score":"15","voters":"7"}
// 平空
{"action":"close_short","ticker":"ETH","price":"3100"}
```

### 出场优先级
```python
# 1. 反向信号 → 关闭所有同方向仓位 + 开反向仓
# 2. Trail触发 → 动态追踪止盈
# 3. SL触发 → 固定止损
# 4. 模式关闭: "Sadece Long"模式收到Peak信号 → 关闭Long（不开Short）
```

### 状态变量
```python
# 持仓状态
posDir: 0=无仓, 1=Long, -1=Short
entryPrice: 入场价
highestSinceEntry: 入场后最高价
lowestSinceEntry: 入场后最低价
trailStopPrice: Trail止损价
trailActive: Trail是否激活
slPrice: 固定止损价
barsSinceEntry: 入场后bar数

# Re-Entry状态
lastExitDir: 上次退出方向
barsSinceExit: 退出后bar数
lastHighAfterExit: 退出后最高价
lastLowAfterExit: 退出后最低价
reEntryCount: 重入场次数
reExitOccurred: 是否发生过退出
```

### 成交量倍数逻辑
```
# 强放量: vol_ratio >= 2.5 → multiplier = 1.25
# 中放量: vol_ratio >= 1.5 → multiplier = 1.15
# 正常: multiplier = 1.0

final_score = total_score * vol_multiplier
```

---

## 版本历史

| 版本 | 说明 |
|------|------|
| v0.1.3 | 基础NFI策略 |
| v0.1.4 | 参数放宽 |
| v0.1.5 | BTC双向交易 |
| v0.2.0 | Y(4.0)委员会投票融合 |

---

## 参考链接

- TradingView原版: https://cn.tradingview.com/script/Mr7em8sC/
- GitHub仓库: https://github.com/nasplycc/LuckyNiuMaNote
- Docker Hub: https://hub.docker.com/r/nasplycc/luckyniumanote-trader

---

_本文件记录Y(4.0)完整策略参数，作为长期参考。后续调优应参考此文件。_