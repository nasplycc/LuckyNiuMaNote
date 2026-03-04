const express = require('express');
const path = require('path');
const fs = require('fs');
const https = require('https');

const app = express();
const PORT = 3000;

// 主钱包地址
const WALLET_ADDRESS = '0xfFd91a584cf6419b92E58245898D2A9281c628eb';
const HL_API = 'https://api.hyperliquid.xyz/info';

// 调用 Hyperliquid API
function hlRequest(body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = https.request(HL_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length
      },
      timeout: 8000
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.write(data);
    req.end();
  });
}

// 读取生成的数据（直接读文件内容并解析）
const generatedDataPath = path.join(__dirname, 'src', 'generated-data.js');
const dataContent = fs.readFileSync(generatedDataPath, 'utf-8');

// 提取数据（简单粗暴的方式）
function extractData(content, varName) {
  const regex = new RegExp(`export const ${varName} = ([\\s\\S]*?);\\s*(?=export const|$)`, 'm');
  const match = content.match(regex);
  if (match) {
    return JSON.parse(match[1]);
  }
  return null;
}

const SITE_CONFIG = extractData(dataContent, 'SITE_CONFIG');
const STATS = extractData(dataContent, 'STATS');
const ENTRIES = extractData(dataContent, 'ENTRIES');
const VERIFICATION = extractData(dataContent, 'VERIFICATION');
const STRATEGY = extractData(dataContent, 'STRATEGY');
const LEARN_ENTRIES = extractData(dataContent, 'LEARN_ENTRIES');

// 静态文件服务
app.use('/public', express.static(path.join(__dirname, 'public')));
app.use(express.static(path.join(__dirname, 'public')));

// ==================== API 路由 ====================

// 交易机器人状态
app.get('/api/trader-status', (req, res) => {
  try {
    // 读取交易机器人日志获取最新状态
    const logPath = path.join(__dirname, 'logs', 'trader_nfi.log');
    let lastLines = [];
    let status = 'unknown';
    let lastSignal = {};
    
    if (fs.existsSync(logPath)) {
      const logContent = fs.readFileSync(logPath, 'utf-8');
      const lines = logContent.split('\n').filter(line => line.trim());
      lastLines = lines.slice(-20); // 最后20行
      
      // 解析最新状态
      for (let i = lines.length - 1; i >= 0; i--) {
        const line = lines[i];
        if (line.includes('no-entry')) {
          const match = line.match(/(BTC|ETH)\s+no-entry\s+\(([^)]+)\)/);
          if (match) {
            lastSignal[match[1]] = { action: 'HOLD', reason: match[2] };
          }
        }
        if (line.includes('NostalgiaForInfinity-inspired trader started')) {
          status = 'running';
          break;
        }
      }
    }
    
    // 计算运行时间
    const traderProcess = require('child_process').execSync('ps -o etime= -p $(pgrep -f "auto_trader_nostalgia_for_infinity.py") 2>/dev/null || echo "unknown"', { encoding: 'utf-8' }).trim();
    
    res.json({
      success: true,
      timestamp: Date.now(),
      status: status,
      uptime: traderProcess,
      strategy: 'NFI (NostalgiaForInfinity)',
      config: {
        tradeSide: { BTC: 'short_only', ETH: 'both' },
        checkInterval: '60s',
        cooldown: '4h'
      },
      lastSignals: lastSignal,
      recentLogs: lastLines.slice(-5)
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// 所有交易机器人状态汇总 (当前运行5个)
app.get('/api/traders-status', (req, res) => {
  try {
    const traders = [
      { id: 'nfi', name: 'NFI原版', logFile: 'trader_nfi.log', script: 'auto_trader_nostalgia_for_infinity.py' },
      { id: 'boll_macd', name: 'BOLL+MACD共振V3', logFile: 'trader_01_boll_macd.log', script: 'trader_01_boll_macd.py' },
      { id: 'supertrend', name: 'SuperTrend×4.0', logFile: 'trader_04_supertrend.log', script: 'trader_04_supertrend.py' },
      { id: 'adx', name: 'ADX趋势过滤', logFile: 'trader_05_adx.log', script: 'trader_05_adx.py' }
    ];
    
    const results = traders.map(trader => {
      const logPath = path.join(__dirname, 'logs', trader.logFile);
      let status = 'offline';
      let lastSignal = {};
      let lastLines = [];
      
      // 检查进程是否运行
      try {
        const { execSync } = require('child_process');
        execSync(`pgrep -f "${trader.script}"`, { stdio: 'ignore' });
        status = 'running';
      } catch (e) {
        status = 'offline';
      }
      
      // 读取日志
      if (fs.existsSync(logPath)) {
        const logContent = fs.readFileSync(logPath, 'utf-8');
        const lines = logContent.split('\n').filter(line => line.trim());
        lastLines = lines.slice(-10);
        
        // 解析最新信号
        for (let i = lines.length - 1; i >= Math.max(0, lines.length - 20); i--) {
          const line = lines[i];
          // BTC/ETH 信号
          const match = line.match(/(BTC|ETH)\s+(HOLD|LONG|SHORT).*?:\s*(.+)/);
          if (match && !lastSignal[match[1]]) {
            lastSignal[match[1]] = { action: match[2], reason: match[3] };
          }
        }
      }
      
      return {
        id: trader.id,
        name: trader.name,
        status: status,
        lastSignal: lastSignal,
        recentLogs: lastLines.slice(-3)
      };
    });
    
    res.json({
      success: true,
      timestamp: Date.now(),
      traders: results
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// NFI 策略指标计算（与 auto_trader_nostalgia_for_infinity.py 一致）
const NFI_EMA_FAST = 20, NFI_EMA_TREND = 50, NFI_EMA_LONG = 200;
const NFI_RSI_FAST = 4, NFI_RSI_MAIN = 14;
const NFI_ATR_PERIOD = 14, NFI_BB_PERIOD = 20, NFI_BB_STDDEV = 2.0;
const NFI_VOLUME_SMA = 30;
const NFI_TRADE_SIDE = 'short_only';  // both / long_only / short_only

const NFI_DEFAULTS = {
  rsi_fast_buy: 23, rsi_main_buy: 36,
  rsi_fast_sell: 79, rsi_main_sell: 62,
  bb_touch_buffer: 1.01, ema_pullback_buffer: 0.985,
  bb_reject_buffer: 0.99, ema_bounce_buffer: 1.015,
  regime_price_floor: 0.95, regime_price_ceiling: 1.05,
  max_breakdown_pct: 0.10, max_breakout_pct: 0.10,
  min_volume_ratio: 0.65
};
const NFI_ETH_OVERRIDES = { rsi_fast_sell: 75, rsi_main_sell: 62 };

function nfiEma(values, period) {
  if (!values.length) return [];
  const mult = 2 / (period + 1);
  const out = [values[0]];
  for (let i = 1; i < values.length; i++) {
    out.push(values[i] * mult + out[i - 1] * (1 - mult));
  }
  return out;
}

function nfiSma(values, period) {
  const out = [];
  let running = 0;
  for (let i = 0; i < values.length; i++) {
    running += values[i];
    if (i >= period) running -= values[i - period];
    const count = i >= period - 1 ? period : i + 1;
    out.push(running / count);
  }
  return out;
}

function nfiRollingStd(values, period) {
  const out = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - period + 1);
    const win = values.slice(start, i + 1);
    const mean = win.reduce((a, b) => a + b, 0) / win.length;
    const variance = win.reduce((s, x) => s + (x - mean) ** 2, 0) / win.length;
    out.push(Math.sqrt(variance));
  }
  return out;
}

function nfiBollingerBands(values, period, stdMult) {
  const mid = nfiSma(values, period);
  const std = nfiRollingStd(values, period);
  return {
    mid,
    upper: mid.map((m, i) => m + stdMult * std[i]),
    lower: mid.map((m, i) => m - stdMult * std[i])
  };
}

function nfiRsiWilder(values, period) {
  if (values.length < 2) return values.map(() => 50);
  const changes = values.slice(1).map((v, i) => v - values[i]);
  const gains = changes.map(c => Math.max(c, 0));
  const losses = changes.map(c => Math.max(-c, 0));
  const out = [50, ...Array(values.length - 1).fill(50)];
  if (changes.length < period) return out;
  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < changes.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    out[i + 1] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

function nfiAtrWilder(highs, lows, closes, period) {
  if (closes.length < 2) return closes.map(() => 0);
  const tr = [0];
  for (let i = 1; i < closes.length; i++) {
    tr.push(Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i - 1]),
      Math.abs(lows[i] - closes[i - 1])
    ));
  }
  const out = [0];
  let running = 0;
  for (let i = 1; i < closes.length; i++) {
    running += tr[i];
    out.push(i <= period ? running / i : (out[i - 1] * (period - 1) + tr[i]) / period);
  }
  return out;
}

async function fetchNfiKlines(symbol, limit = 260) {
  const url = 'https://api.hyperliquid.xyz/info';
  const end = Date.now();
  const start = end - limit * 60 * 60 * 1000;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: 'candleSnapshot',
      req: { coin: symbol, interval: '1h', startTime: start, endTime: end }
    })
  });
  const data = await res.json();
  return (data || []).map(c => ({
    timestamp: c.t,
    open: parseFloat(c.o),
    high: parseFloat(c.h),
    low: parseFloat(c.l),
    close: parseFloat(c.c),
    volume: parseFloat(c.v)
  }));
}

async function computeNfiIndicators(symbol) {
  const klines = await fetchNfiKlines(symbol);
  if (klines.length < NFI_EMA_LONG + 5) {
    return null;
  }
  const closes = klines.map(k => k.close);
  const highs = klines.map(k => k.high);
  const lows = klines.map(k => k.low);
  const volumes = klines.map(k => k.volume);

  const emaFast = nfiEma(closes, NFI_EMA_FAST);
  const emaTrend = nfiEma(closes, NFI_EMA_TREND);
  const emaLong = nfiEma(closes, NFI_EMA_LONG);
  const rsiFast = nfiRsiWilder(closes, NFI_RSI_FAST);
  const rsiMain = nfiRsiWilder(closes, NFI_RSI_MAIN);
  const atrVals = nfiAtrWilder(highs, lows, closes, NFI_ATR_PERIOD);
  const bb = nfiBollingerBands(closes, NFI_BB_PERIOD, NFI_BB_STDDEV);
  const volumeSma = nfiSma(volumes, NFI_VOLUME_SMA);

  const i = closes.length - 1;
  const price = closes[i];
  const prevClose = closes[i - 1];
  const prevRsiFast = rsiFast[i - 1];

  const params = { ...NFI_DEFAULTS, ...(symbol === 'ETH' ? NFI_ETH_OVERRIDES : {}) };

  const regimeLong = emaTrend[i] > emaLong[i] && price > emaLong[i] * params.regime_price_floor;
  const regimeShort = emaTrend[i] < emaLong[i] && price < emaLong[i] * params.regime_price_ceiling;
  const pullbackLong = price <= bb.lower[i] * params.bb_touch_buffer || price <= emaFast[i] * params.ema_pullback_buffer;
  const pullbackShort = price >= bb.upper[i] * params.bb_reject_buffer || price >= emaFast[i] * params.ema_bounce_buffer;
  const rsiLong = rsiFast[i] <= params.rsi_fast_buy && rsiMain[i] <= params.rsi_main_buy;
  const rsiShort = rsiFast[i] >= params.rsi_fast_sell && rsiMain[i] >= params.rsi_main_sell;
  const volumeOk = volumeSma[i] > 0 && volumes[i] >= volumeSma[i] * params.min_volume_ratio;
  const notBreakdown = price >= emaLong[i] * (1 - params.max_breakdown_pct);
  const notBreakout = price <= emaLong[i] * (1 + params.max_breakout_pct);
  const stabilizingLong = price >= prevClose || rsiFast[i] > prevRsiFast;
  const stabilizingShort = price <= prevClose || rsiFast[i] < prevRsiFast;

  const allowLong = ['both', 'long_only', 'long'].includes(NFI_TRADE_SIDE);
  const allowShort = ['both', 'short_only', 'short'].includes(NFI_TRADE_SIDE);
  const longOk = allowLong && regimeLong && pullbackLong && rsiLong && volumeOk && notBreakdown && stabilizingLong;
  const shortOk = allowShort && regimeShort && pullbackShort && rsiShort && volumeOk && notBreakout && stabilizingShort;

  return {
    price,
    ema_fast: emaFast[i],
    ema_trend: emaTrend[i],
    ema_long: emaLong[i],
    rsi_fast: rsiFast[i],
    rsi_main: rsiMain[i],
    atr: atrVals[i],
    bb_upper: bb.upper[i],
    bb_mid: bb.mid[i],
    bb_lower: bb.lower[i],
    volume: volumes[i],
    volume_sma: volumeSma[i],
    trend_up: emaTrend[i] > emaLong[i],
    trend_down: emaTrend[i] < emaLong[i],
    regime_long: regimeLong,
    regime_short: regimeShort,
    conditions: {
      regime_long: regimeLong,
      regime_short: regimeShort,
      pullback_long: pullbackLong,
      pullback_short: pullbackShort,
      rsi_long: rsiLong,
      rsi_short: rsiShort,
      volume_ok: volumeOk,
      not_breakout: notBreakout,
      stabilizing_short: stabilizingShort,
      short_ok: shortOk,
      long_ok: longOk
    },
    params: { rsi_fast_sell: params.rsi_fast_sell, rsi_main_sell: params.rsi_main_sell }
  };
}

// 技术指标数据 (NFI 策略)
app.get('/api/indicators', async (req, res) => {
  try {
    const symbols = ['BTC', 'ETH'];
    const indicators = {};
    for (const symbol of symbols) {
      const ind = await computeNfiIndicators(symbol);
      if (ind) indicators[symbol] = ind;
    }
    res.json({
      success: true,
      timestamp: Date.now(),
      indicators
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// 历史K线数据（带EMA和信号）
app.get('/api/chart/:symbol', async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const interval = (req.query.interval || '1h').toLowerCase();
    const is1m = interval === '1m';
    
    const url = 'https://api.hyperliquid.xyz/info';
    const end_time = Date.now();
    let start_time;
    let minutes;
    if (is1m) {
      minutes = parseInt(req.query.minutes) || (parseInt(req.query.hours) || 24) * 60;
      start_time = end_time - (minutes * 60 * 1000);
    } else {
      const days = parseInt(req.query.days) || 30;
      start_time = end_time - (days * 24 * 60 * 60 * 1000);
    }
    
    const payload = {
      type: 'candleSnapshot',
      req: {
        coin: symbol,
        interval: is1m ? '1m' : '1h',
        startTime: start_time,
        endTime: end_time
      }
    };
    
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    const candles = await response.json();
    const minCandles = is1m ? Math.max(9, Math.min(minutes || 1440, 55)) : 60;
    if (!candles || candles.length < minCandles) {
      return res.json({ success: false, error: '数据不足' });
    }
    
    // 解析K线
    const klines = candles.map(c => ({
      timestamp: c.t,
      open: parseFloat(c.o),
      high: parseFloat(c.h),
      low: parseFloat(c.l),
      close: parseFloat(c.c),
      volume: parseFloat(c.v)
    }));
    
    // 计算EMA
    const ema = (data, period) => {
      const multiplier = 2 / (period + 1);
      const ema = [data[0]];
      for (let i = 1; i < data.length; i++) {
        ema.push(data[i] * multiplier + ema[i-1] * (1 - multiplier));
      }
      return ema;
    };
    
    const closes = klines.map(k => k.close);
    const ema9 = ema(closes, 9);
    const ema21 = ema(closes, 21);
    const ema55 = ema(closes, 55);
    
    // 计算ATR（用于波动率过滤）
    const atr = (highs, lows, closes, period) => {
      const tr = [];
      for (let i = 1; i < closes.length; i++) {
        tr.push(Math.max(
          highs[i] - lows[i],
          Math.abs(highs[i] - closes[i - 1]),
          Math.abs(lows[i] - closes[i - 1])
        ));
      }
      const atrArr = [0];
      for (let i = 1; i < closes.length; i++) {
        const start = Math.max(0, i - period);
        const slice = tr.slice(start, i);
        atrArr.push(slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : 0);
      }
      return atrArr;
    };
    const highs = klines.map(k => k.high);
    const lows = klines.map(k => k.low);
    const atr14 = atr(highs, lows, closes, 14);
    
    // 添加EMA和ATR到K线
    klines.forEach((k, i) => {
      k.ema9 = ema9[i];
      k.ema21 = ema21[i];
      k.ema55 = ema55[i];
      k.atr = atr14[i];
    });
    
    // 图表信号：EMA排列 + 金叉/死叉 + fee_check（仅用于可视化参考）
    const TAKER_FEE = 0.00035;
    const MIN_PROFIT_AFTER_FEE = 0.005;
    const DEFAULT_POSITION_USD = 100;  // 用于 fee_check 的假设仓位
    
    const checkProfitAfterFees = (entryPrice, takeProfit, atrVal) => {
      const priceChangePct = Math.abs(takeProfit - entryPrice) / entryPrice;
      const grossProfit = DEFAULT_POSITION_USD * priceChangePct;
      const openFee = DEFAULT_POSITION_USD * TAKER_FEE;
      const closePositionValue = DEFAULT_POSITION_USD * (1 + priceChangePct);
      const closeFee = closePositionValue * TAKER_FEE;
      const totalFees = openFee + closeFee;
      const netProfit = grossProfit - totalFees;
      const netProfitPct = netProfit / DEFAULT_POSITION_USD;
      return netProfitPct >= MIN_PROFIT_AFTER_FEE;
    };
    
    const signals = [];
    for (let i = 1; i < klines.length; i++) {
      const prev = klines[i - 1];
      const curr = klines[i];
      
      if (!prev.ema9 || !prev.ema21 || !curr.ema9 || !curr.ema21 || !curr.ema55 || !curr.atr) continue;
      
      // 做多参考信号：trend_up + golden_cross + fee_check
      if (prev.ema9 <= prev.ema21 && curr.ema9 > curr.ema21) {
        const trendUp = curr.ema9 > curr.ema21 && curr.ema21 > curr.ema55;
        const stopLoss = curr.close - 2 * curr.atr;
        const takeProfit = curr.close + 3 * curr.atr;
        const feeValid = checkProfitAfterFees(curr.close, takeProfit, curr.atr);
        if (trendUp && feeValid) {
          signals.push({
            type: 'golden_cross',
            timestamp: curr.timestamp,
            price: curr.close,
            index: i,
            label: '金叉买入'
          });
        }
      }
      // 做空参考信号：trend_down + death_cross + fee_check
      else if (prev.ema9 >= prev.ema21 && curr.ema9 < curr.ema21) {
        const trendDown = curr.ema9 < curr.ema21 && curr.ema21 < curr.ema55;
        const stopLoss = curr.close + 2 * curr.atr;
        const takeProfit = curr.close - 3 * curr.atr;
        const feeValid = checkProfitAfterFees(curr.close, takeProfit, curr.atr);
        if (trendDown && feeValid) {
          signals.push({
            type: 'death_cross',
            timestamp: curr.timestamp,
            price: curr.close,
            index: i,
            label: '死叉卖出'
          });
        }
      }
    }
    
    res.json({
      success: true,
      symbol: symbol,
      interval: is1m ? '1m' : '1h',
      klines: klines,
      signals: signals
    });
    
  } catch (error) {
    console.error('Chart API error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// 实时持仓和账户数据
app.get('/api/position', async (req, res) => {
  try {
    // 并行请求
    const [perpState, spotState, mids] = await Promise.all([
      hlRequest({ type: 'clearinghouseState', user: WALLET_ADDRESS }),
      hlRequest({ type: 'spotClearinghouseState', user: WALLET_ADDRESS }),
      hlRequest({ type: 'allMids' })
    ]);

    // 解析 Perp 账户
    const marginSummary = perpState.marginSummary || {};
    const perpValue = parseFloat(marginSummary.accountValue || 0);
    
    // 解析持仓
    const positions = (perpState.assetPositions || [])
      .filter(p => parseFloat(p.position.szi) !== 0)
      .map(p => {
        const pos = p.position;
        const size = parseFloat(pos.szi);
        const entryPx = parseFloat(pos.entryPx);
        const currentPx = parseFloat(mids[pos.coin] || 0);
        const pnl = parseFloat(pos.unrealizedPnl);
        const pnlPct = entryPx > 0 ? ((currentPx - entryPx) / entryPx * 100) : 0;
        
        return {
          coin: pos.coin,
          size: size,
          side: size > 0 ? 'LONG' : 'SHORT',
          entryPx: entryPx,
          currentPx: currentPx,
          pnl: pnl,
          pnlPct: size > 0 ? pnlPct : -pnlPct,
          liquidationPx: pos.liquidationPx ? parseFloat(pos.liquidationPx) : null
        };
      });

    // 解析 Spot 余额
    const spotBalances = (spotState.balances || [])
      .filter(b => parseFloat(b.total) > 0)
      .map(b => ({
        coin: b.coin,
        total: parseFloat(b.total)
      }));
    
    const spotValue = spotBalances.reduce((sum, b) => {
      if (b.coin === 'USDC') return sum + b.total;
      const price = parseFloat(mids[b.coin] || 0);
      return sum + b.total * price;
    }, 0);

    // 总资产
    const totalValue = perpValue + spotValue;
    const initialCapital = 98;
    const totalPnl = totalValue - initialCapital;
    const totalPnlPct = (totalPnl / initialCapital) * 100;

    res.json({
      success: true,
      timestamp: Date.now(),
      account: {
        perpValue: perpValue,
        spotValue: spotValue,
        totalValue: totalValue,
        initialCapital: initialCapital,
        totalPnl: totalPnl,
        totalPnlPct: totalPnlPct
      },
      positions: positions,
      spotBalances: spotBalances,
      prices: {
        BTC: parseFloat(mids.BTC || 0),
        ETH: parseFloat(mids.ETH || 0)
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ==================== 页面路由 ====================

// 简单的 markdown 渲染
function renderMarkdown(text) {
  return text
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', year: 'numeric' });
}

function getHTML(content) {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>赛博牛马的交易日志 🤖🐴</title>
  <link rel="icon" href="/favicon-32.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-primary: #0a0a0f;
      --bg-secondary: #0d1117;
      --bg-card: #161b22;
      --text-primary: #e6edf3;
      --text-secondary: #8b949e;
      --text-muted: #6e7681;
      --accent: #00ff9f;
      --accent-dim: #00cc7f;
      --accent-glow: rgba(0, 255, 159, 0.3);
      --cyber-pink: #ff0080;
      --cyber-blue: #00d4ff;
      --cyber-purple: #bf00ff;
      --border: #30363d;
      --grid-color: rgba(0, 255, 159, 0.03);
    }
    
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.8;
      min-height: 100vh;
      background-image: 
        linear-gradient(var(--grid-color) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
      background-size: 50px 50px;
    }
    
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: radial-gradient(ellipse at top, rgba(0, 255, 159, 0.08) 0%, transparent 50%),
                  radial-gradient(ellipse at bottom right, rgba(255, 0, 128, 0.05) 0%, transparent 50%);
      pointer-events: none;
      z-index: -1;
    }
    
    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 20px;
    }
    
    /* Header - Cyber Style */
    header {
      text-align: center;
      padding: 50px 0;
      position: relative;
    }
    
    header::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 80%;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--accent), var(--cyber-pink), transparent);
    }
    
    .logo {
      width: 140px;
      height: 140px;
      margin: 0 auto 25px;
      border-radius: 50%;
      border: 3px solid var(--accent);
      box-shadow: 0 0 30px var(--accent-glow), 0 0 60px var(--accent-glow), inset 0 0 30px rgba(0, 255, 159, 0.1);
      animation: glow 3s ease-in-out infinite;
      display: block;
    }
    
    @keyframes glow {
      0%, 100% { box-shadow: 0 0 30px var(--accent-glow), 0 0 60px var(--accent-glow); }
      50% { box-shadow: 0 0 40px var(--accent-glow), 0 0 80px var(--accent-glow); }
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    h1 {
      font-size: 2.8em;
      background: linear-gradient(135deg, var(--accent) 0%, var(--cyber-blue) 50%, var(--cyber-pink) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: 15px;
      font-weight: 700;
    }
    
    .subtitle {
      color: var(--text-secondary);
      font-size: 1.1em;
      font-family: 'JetBrains Mono', monospace;
    }
    
    /* Stats - Cyber Dashboard */
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 20px;
      margin: 40px 0;
    }
    
    .stat-card {
      background: var(--bg-card);
      padding: 25px;
      border-radius: 8px;
      border: 1px solid var(--border);
      transition: all 0.3s;
      position: relative;
      overflow: hidden;
    }
    
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(90deg, var(--accent), var(--cyber-blue));
      opacity: 0;
      transition: opacity 0.3s;
    }
    
    .stat-card:hover {
      transform: translateY(-5px);
      border-color: var(--accent);
      box-shadow: 0 10px 40px rgba(0, 255, 159, 0.15);
    }
    
    .stat-card:hover::before {
      opacity: 1;
    }
    
    .stat-label {
      color: var(--text-muted);
      font-size: 0.85em;
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .stat-value {
      font-size: 2.2em;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .stat-value.green {
      color: var(--accent);
      text-shadow: 0 0 20px var(--accent-glow);
    }
    
    .stat-value.blue {
      color: var(--cyber-blue);
      text-shadow: 0 0 20px rgba(0, 212, 255, 0.5);
    }
    
    .stat-value.pink {
      color: var(--cyber-pink);
      text-shadow: 0 0 20px rgba(255, 0, 128, 0.5);
    }
    
    /* Wallet Card - Cyber Panel */
    .wallet-card {
      background: var(--bg-card);
      padding: 30px;
      border-radius: 8px;
      border: 1px solid var(--accent);
      margin: 30px 0;
      position: relative;
      overflow: hidden;
      box-shadow: 0 0 30px rgba(0, 255, 159, 0.1);
    }
    
    .wallet-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--cyber-pink), var(--cyber-blue));
    }
    
    .wallet-card h3 {
      color: var(--accent);
      margin-bottom: 20px;
      font-size: 1.3em;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .wallet-card code {
      background: var(--bg-primary);
      padding: 12px 16px;
      border-radius: 4px;
      color: var(--accent);
      font-size: 0.9em;
      display: block;
      margin: 10px 0;
      word-break: break-all;
      font-family: 'JetBrains Mono', monospace;
      border: 1px solid var(--border);
    }
    
    .wallet-info {
      color: var(--text-secondary);
      font-size: 0.9em;
      margin-top: 20px;
      padding: 15px;
      background: var(--bg-secondary);
      border-radius: 4px;
      border-left: 3px solid var(--cyber-blue);
    }
    
    .wallet-info strong {
      color: var(--cyber-blue);
    }
    
    /* Entries Section */
    .entries {
      margin-top: 50px;
    }
    
    .entries > h2 {
      color: var(--accent);
      margin-bottom: 30px;
      font-size: 1.8em;
      display: flex;
      align-items: center;
      gap: 15px;
    }
    
    .entries > h2::after {
      content: '';
      flex: 1;
      height: 1px;
      background: linear-gradient(90deg, var(--accent), transparent);
    }
    
    .entry {
      background: var(--bg-card);
      padding: 30px;
      margin-bottom: 25px;
      border-radius: 8px;
      border: 1px solid var(--border);
      transition: all 0.3s;
      position: relative;
      overflow: hidden;
    }
    
    .entry::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 3px;
      height: 100%;
      background: linear-gradient(180deg, var(--accent), var(--cyber-pink));
      opacity: 0;
      transition: opacity 0.3s;
    }
    
    .entry:hover {
      border-color: var(--accent);
      transform: translateX(8px);
      box-shadow: -8px 0 30px rgba(0, 255, 159, 0.1);
    }
    
    .entry:hover::before {
      opacity: 1;
    }
    
    .entry h2 {
      margin-bottom: 12px;
      font-size: 1.5em;
    }
    
    .entry h2 a {
      color: var(--text-primary);
      text-decoration: none;
      transition: all 0.3s;
    }
    
    .entry h2 a:hover {
      color: var(--accent);
      text-shadow: 0 0 15px var(--accent-glow);
    }
    
    .entry-meta {
      color: var(--text-muted);
      font-size: 0.9em;
      margin-bottom: 15px;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .entry-content {
      color: var(--text-secondary);
      line-height: 1.9;
    }
    
    .entry-content p {
      margin: 15px 0;
    }
    
    .entry-content h2 {
      color: var(--accent);
      margin: 30px 0 15px;
      font-size: 1.4em;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }
    
    .entry-content h3 {
      color: var(--cyber-blue);
      margin: 25px 0 15px;
      font-size: 1.2em;
    }
    
    .entry-content ul, .entry-content ol {
      margin: 15px 0;
      padding-left: 25px;
    }
    
    .entry-content li {
      margin: 10px 0;
    }
    
    .entry-content blockquote {
      border-left: 3px solid var(--cyber-pink);
      padding: 15px 20px;
      margin: 20px 0;
      background: rgba(255, 0, 128, 0.05);
      color: var(--text-secondary);
      font-style: italic;
    }
    
    .entry-content code {
      background: var(--bg-secondary);
      padding: 3px 8px;
      border-radius: 4px;
      color: var(--cyber-blue);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
    }
    
    .entry-content table {
      width: 100%;
      margin: 20px 0;
      border-collapse: collapse;
    }
    
    .entry-content th,
    .entry-content td {
      padding: 12px 15px;
      border: 1px solid var(--border);
      text-align: left;
    }
    
    .entry-content th {
      background: var(--bg-secondary);
      color: var(--accent);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.85em;
      letter-spacing: 0.05em;
    }
    
    .entry-content td {
      background: var(--bg-card);
    }
    
    .entry-content strong {
      color: var(--text-primary);
    }
    
    /* Tags */
    .tag {
      display: inline-block;
      background: rgba(0, 255, 159, 0.1);
      color: var(--accent);
      padding: 4px 12px;
      border-radius: 2px;
      font-size: 0.8em;
      margin-right: 8px;
      border: 1px solid rgba(0, 255, 159, 0.2);
      font-family: 'JetBrains Mono', monospace;
    }
    
    /* Links */
    a { 
      color: var(--accent); 
      text-decoration: none;
      transition: all 0.3s;
    }
    
    a:hover { 
      text-shadow: 0 0 10px var(--accent-glow);
    }
    
    .read-link {
      display: inline-block;
      margin-top: 15px;
      padding: 8px 16px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--accent);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85em;
      transition: all 0.3s;
    }
    
    .read-link:hover {
      background: var(--accent);
      color: var(--bg-primary);
      border-color: var(--accent);
      box-shadow: 0 0 20px var(--accent-glow);
    }
    
    .back-link {
      display: inline-block;
      margin: 20px 0;
      padding: 10px 20px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      transition: all 0.3s;
    }
    
    .back-link:hover {
      border-color: var(--accent);
      box-shadow: 0 0 15px var(--accent-glow);
    }
    
    /* Footer */
    footer {
      text-align: center;
      padding: 40px 0;
      margin-top: 50px;
      border-top: 1px solid var(--border);
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
      position: relative;
    }
    
    footer::before {
      content: '';
      position: absolute;
      top: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 100px;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--accent), transparent);
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
      width: 8px;
    }
    
    ::-webkit-scrollbar-track {
      background: var(--bg-primary);
    }
    
    ::-webkit-scrollbar-thumb {
      background: var(--border);
      border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
      background: var(--accent);
    }
    
    /* Mobile */
    @media (max-width: 600px) {
      .container { padding: 15px; }
      h1 { font-size: 2em; }
      .logo { width: 100px; height: 100px; }
      .stat-value { font-size: 1.6em; }
      .entry { padding: 20px; }
    }
    
    /* 实时持仓卡片样式 */
    .position-card {
      background: var(--bg-card);
      border: 1px solid var(--cyber-blue);
      border-radius: 8px;
      padding: 20px;
      margin: 30px 0;
      position: relative;
      overflow: hidden;
      box-shadow: 0 0 30px rgba(0, 212, 255, 0.15);
    }
    
    .position-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--cyber-blue), var(--accent), var(--cyber-pink));
      animation: gradientMove 3s linear infinite;
    }
    
    @keyframes gradientMove {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }
    
    .position-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 15px;
      border-bottom: 1px solid var(--border);
    }
    
    .position-header h3 {
      color: var(--cyber-blue);
      font-size: 1.2em;
      margin: 0;
    }
    
    .live-badge {
      background: rgba(0, 255, 159, 0.1);
      color: var(--accent);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.75em;
      font-family: 'JetBrains Mono', monospace;
      animation: pulse 2s ease-in-out infinite;
    }
    
    .position-item {
      background: var(--bg-secondary);
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 15px;
      border: 1px solid var(--border);
    }
    
    .position-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
    }
    
    .position-row:not(:last-child) {
      border-bottom: 1px solid var(--border);
    }
    
    .position-row .coin {
      font-size: 1.3em;
      font-weight: 700;
      color: var(--text-primary);
      font-family: 'JetBrains Mono', monospace;
    }
    
    .position-row .side {
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 0.8em;
      font-weight: 600;
      text-transform: uppercase;
    }
    
    .position-row .side.long {
      background: rgba(0, 255, 159, 0.15);
      color: var(--accent);
      border: 1px solid var(--accent);
    }
    
    .position-row .side.short {
      background: rgba(255, 0, 128, 0.15);
      color: var(--cyber-pink);
      border: 1px solid var(--cyber-pink);
    }
    
    .position-row .size {
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-secondary);
    }
    
    .position-row .label {
      color: var(--text-muted);
      font-size: 0.9em;
    }
    
    .position-row .value {
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-primary);
    }
    
    .position-row .value.price-live {
      color: var(--cyber-blue);
    }
    
    .pnl-row .value.profit {
      color: var(--accent);
      text-shadow: 0 0 10px var(--accent-glow);
      font-weight: 600;
    }
    
    .pnl-row .value.loss {
      color: var(--cyber-pink);
      text-shadow: 0 0 10px rgba(255, 0, 128, 0.5);
      font-weight: 600;
    }
    
    .prices-bar {
      display: flex;
      justify-content: center;
      gap: 30px;
      padding: 15px;
      background: var(--bg-secondary);
      border-radius: 4px;
      margin-top: 10px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
      color: var(--text-secondary);
    }
    
    .position-footer {
      text-align: right;
      margin-top: 15px;
      padding-top: 15px;
      border-top: 1px solid var(--border);
      font-size: 0.8em;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }
    
    .no-position {
      text-align: center;
      padding: 30px;
      color: var(--text-muted);
      font-style: italic;
    }
    
    .loading {
      text-align: center;
      padding: 30px;
      color: var(--cyber-blue);
    }
    
    .error {
      text-align: center;
      padding: 30px;
      color: var(--cyber-pink);
    }
    
    .stat-value.green { color: var(--accent); text-shadow: 0 0 20px var(--accent-glow); }
    .stat-value.blue { color: var(--cyber-blue); text-shadow: 0 0 20px rgba(0, 212, 255, 0.5); }
    .stat-value.pink { color: var(--cyber-pink); text-shadow: 0 0 20px rgba(255, 0, 128, 0.5); }
    .stat-value.red { color: var(--cyber-pink); text-shadow: 0 0 20px rgba(255, 0, 128, 0.5); }
    
    .stat-detail {
      font-size: 0.7em;
      color: var(--text-muted);
      margin-top: 5px;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .live-dot {
      color: var(--accent);
      font-size: 0.8em;
      animation: pulse 2s ease-in-out infinite;
      margin-left: 5px;
    }
    
    .live-card {
      position: relative;
    }
    
    .live-card::after {
      content: 'LIVE';
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(0, 255, 159, 0.1);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 0.6em;
      font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.05em;
    }
  </style>
</head>
<body>
  <div class="container">
    ${content}
    <footer>
      <p>🤖🐴 赛博牛马 × AI Trading Experiment</p>
      <p style="margin-top: 10px; font-size: 0.8em;">Powered by OpenClaw</p>
    </footer>
  </div>
</body>
</html>`;
}

// 首页
app.get('/', (req, res) => {
  const statsHTML = `
    <div class="stat-card">
      <div class="stat-label">📅 启动资金</div>
      <div class="stat-value green">$98</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">💰 当前余额</div>
      <div class="stat-value blue">$${STATS.balance.toFixed(2)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">📈 总收益</div>
      <div class="stat-value pink">${STATS.returnPct >= 0 ? '+' : ''}${STATS.returnPct.toFixed(1)}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">🎯 完成交易</div>
      <div class="stat-value green">${STATS.trades}</div>
    </div>
  `;
  
  // 钱包地址卡片
  const walletHTML = VERIFICATION ? `
    <div class="wallet-card">
      <h3>💰 交易钱包</h3>
      <div>
        <span style="color: var(--text-muted); font-size: 0.85em; font-family: 'JetBrains Mono', monospace;">WALLET ADDRESS</span>
        <code>${VERIFICATION.tradingAccount}</code>
      </div>
      <div class="wallet-info">
        <strong>充值说明:</strong><br>
        • 网络: <strong>${VERIFICATION.depositChain}</strong><br>
        • 币种: <strong>${VERIFICATION.depositToken}</strong><br>
        • 备注: ${VERIFICATION.depositNote}
      </div>
    </div>
  ` : '';
  
  const entriesHTML = ENTRIES.slice(0, 10).map(entry => {
    const preview = entry.content.substring(0, 200).replace(/\*/g, '').replace(/\n/g, ' ');
    return `
    <div class="entry">
      <h2><a href="/entry/${entry.slug}">${entry.title}</a></h2>
      <div class="entry-meta">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </div>
      <div class="entry-content">
        <p>${preview}...</p>
      </div>
      <a href="/entry/${entry.slug}" class="read-link">阅读全文 →</a>
    </div>
  `}).join('');
  
  const content = `
    <header>
      <img src="/logo_256.png" alt="赛博牛马" class="logo">
      <h1>🤖🐴 赛博牛马的交易日志</h1>
      <p class="subtitle">// AI Trading Experiment v1.0</p>
      <div style="margin-top: 20px; display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
        <a href="/" style="background: var(--bg-card); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border); font-size: 0.9em;">🏠 首页</a>
        <a href="/strategy" style="background: var(--bg-card); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--accent); font-size: 0.9em;">🎯 交易策略</a>
        <a href="/learn" style="background: var(--bg-card); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border); font-size: 0.9em;">📚 学习资料</a>
      </div>
    </header>
    
    <div class="stats" id="stats-container">
      ${statsHTML}
    </div>
    
    <!-- 实时持仓区域 -->
    <div class="position-card" id="position-card" style="display:none;">
      <div class="position-header">
        <h3>📊 实时持仓</h3>
        <span class="live-badge">● LIVE</span>
      </div>
      <div id="position-content">
        <div class="loading">加载中...</div>
      </div>
      <div class="position-footer">
        <span id="update-time">--</span>
      </div>
    </div>
    
    <!-- 交易机器人状态 -->
    <div class="position-card" id="trader-status-card" style="display:none; border-color: var(--cyber-blue);">
      <div class="position-header">
        <h3 style="color: var(--cyber-blue);">🤖 交易机器人状态</h3>
        <span class="live-badge">● LIVE</span>
      </div>
      <div id="trader-status-content">
        <div class="loading">加载中...</div>
      </div>
      <div class="position-footer">
        <span id="trader-status-update-time">--</span>
      </div>
    </div>
    
    <!-- 所有交易机器人状态汇总 -->
    <div class="position-card" id="all-traders-card" style="border-color: var(--cyber-purple);">
      <div class="position-header">
        <h3 style="color: var(--cyber-purple);">🤖🐮 赛博牛马交易军团 (4个核心策略)</h3>
        <span class="live-badge">● LIVE</span>
      </div>
      <div id="all-traders-content">
        <div class="loading">加载中...</div>
      </div>
      <div style="margin-top: 10px; padding: 10px; background: var(--bg-card); border-radius: 6px; font-size: 0.75em; color: var(--text-muted);">
        📝 当前运行: NFI原版 | BOLL+MACD V3 | SuperTrend×4.0 | ADX优化版
      </div>
      <div class="position-footer">
        <span id="all-traders-update-time">--</span>
      </div>
    </div>
    
    <!-- NFI 策略技术指标展示 -->
    <div class="position-card" id="indicators-card" style="display:none; border-color: var(--accent);">
      <div class="position-header">
        <h3 style="color: var(--accent);">📈 NFI 技术指标 (1小时)</h3>
        <span class="live-badge">● LIVE</span>
      </div>
      <div style="font-size: 0.75em; color: var(--text-muted); margin-bottom: 10px; padding: 0 4px;">
        字段：EMA20/50/200 均线 | RSI 超买超卖 | ATR 波动率 | 成交量≥65%均量。BTC short_only 只做空；ETH both 多空都做。
      </div>
      <div id="indicators-content">
        <div class="loading">加载中...</div>
      </div>
      <div class="position-footer">
        <span id="indicators-update-time">--</span>
      </div>
    </div>
    
    ${walletHTML}
    
    <div class="entries">
      <h2>📝 交易日志</h2>
      ${entriesHTML}
    </div>
    
    <script>
      // 实时持仓更新
      async function updatePosition() {
        try {
          const res = await fetch('/api/position');
          const data = await res.json();
          
          if (!data.success) {
            document.getElementById('position-content').innerHTML = '<div class="error">获取数据失败</div>';
            return;
          }
          
          const { account, positions, prices } = data;
          
          // 更新顶部统计
          const statsContainer = document.getElementById('stats-container');
          const pnlClass = account.totalPnl >= 0 ? 'green' : 'red';
          const pnlSign = account.totalPnl >= 0 ? '+' : '';
          statsContainer.innerHTML = \`
            <div class="stat-card">
              <div class="stat-label">📅 启动资金</div>
              <div class="stat-value green">$\${account.initialCapital}</div>
            </div>
            <div class="stat-card live-card">
              <div class="stat-label">💰 总资产 <span class="live-dot">●</span></div>
              <div class="stat-value blue">$\${account.totalValue.toFixed(2)}</div>
              <div class="stat-detail">$\${account.spotValue.toFixed(2)} + $\${account.perpValue.toFixed(2)}</div>
            </div>
            <div class="stat-card live-card">
              <div class="stat-label">📈 总收益 <span class="live-dot">●</span></div>
              <div class="stat-value \${pnlClass}">\${pnlSign}\${account.totalPnlPct.toFixed(2)}%</div>
            </div>
            <div class="stat-card live-card">
              <div class="stat-label">💵 未实现盈亏 <span class="live-dot">●</span></div>
              <div class="stat-value \${pnlClass}">\${pnlSign}$\${account.totalPnl.toFixed(2)}</div>
            </div>
          \`;
          
          // 显示持仓卡片
          const card = document.getElementById('position-card');
          card.style.display = 'block';
          
          let html = '';
          
          if (positions.length === 0) {
            html = '<div class="no-position">当前无持仓</div>';
          } else {
            positions.forEach(pos => {
              const pnlClass = pos.pnl >= 0 ? 'profit' : 'loss';
              const pnlSign = pos.pnl >= 0 ? '+' : '';
              const sideClass = pos.side === 'LONG' ? 'long' : 'short';
              
              html += \`
                <div class="position-item">
                  <div class="position-row">
                    <span class="coin">\${pos.coin}</span>
                    <span class="side \${sideClass}">\${pos.side}</span>
                    <span class="size">\${pos.size}</span>
                  </div>
                  <div class="position-row">
                    <span class="label">开仓价</span>
                    <span class="value">$\${pos.entryPx.toLocaleString()}</span>
                  </div>
                  <div class="position-row">
                    <span class="label">现价</span>
                    <span class="value price-live">$\${pos.currentPx.toLocaleString()}</span>
                  </div>
                  <div class="position-row pnl-row">
                    <span class="label">盈亏</span>
                    <span class="value \${pnlClass}">\${pnlSign}$\${pos.pnl.toFixed(2)} (\${pnlSign}\${pos.pnlPct.toFixed(2)}%)</span>
                  </div>
                </div>
              \`;
            });
          }
          
          // 显示价格
          html += \`
            <div class="prices-bar">
              <span>BTC: $\${prices.BTC.toLocaleString()}</span>
              <span>ETH: $\${prices.ETH.toLocaleString()}</span>
            </div>
          \`;
          
          document.getElementById('position-content').innerHTML = html;
          document.getElementById('update-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
          
        } catch (err) {
          console.error('Failed to update position:', err);
        }
      }
      
      // NFI 指标更新
      async function updateIndicators() {
        try {
          const res = await fetch('/api/indicators');
          const data = await res.json();
          
          if (!data.success || !data.indicators) {
            document.getElementById('indicators-content').innerHTML = '\u003cdiv class="error"\u003e获取指标失败\u003c/div\u003e';
            return;
          }
          
          const indicators = data.indicators;
          const card = document.getElementById('indicators-card');
          card.style.display = 'block';
          
          let html = '';
          
          for (const [symbol, ind] of Object.entries(indicators)) {
            const trendUp = ind.trend_up;
            const trendDown = ind.trend_down;
            
            let trendIcon = '➡️';
            let trendText = '震荡整理';
            let trendColor = 'var(--text-muted)';
            let trendBg = 'rgba(110, 118, 129, 0.1)';
            
            if (trendUp) {
              trendIcon = '📈';
              trendText = '上升趋势 (EMA50>200)';
              trendColor = 'var(--accent)';
              trendBg = 'rgba(0, 255, 159, 0.1)';
            } else if (trendDown) {
              trendIcon = '📉';
              trendText = '下降趋势 (EMA50<200)';
              trendColor = 'var(--cyber-pink)';
              trendBg = 'rgba(255, 0, 128, 0.1)';
            }
            
            const c = ind.conditions || {};
            const isEth = symbol === 'ETH';
            const longOk = c.long_ok;
            const shortOk = c.short_ok;
            const rsiSell = ind.params ? ind.params.rsi_fast_sell : 79;
            const rsiMainSell = ind.params ? ind.params.rsi_main_sell : 62;
            const rsiBuyFast = isEth ? 21 : 23;
            const rsiBuyMain = isEth ? 34 : 36;
            
            html += '\u003cdiv style="margin-bottom: 20px; padding: 20px; background: var(--bg-secondary); border-radius: 12px; border: 1px solid var(--border);"\u003e';
            
            html += '\u003cdiv style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 8px;"\u003e';
            html += '\u003cdiv style="display: flex; align-items: center; gap: 10px;"\u003e';
            html += '\u003cspan style="font-size: 1.5em; font-weight: 700; color: var(--text-primary);"\u003e' + symbol + '\u003c/span\u003e';
            html += '\u003cspan style="font-size: 1.2em;"\u003e' + trendIcon + '\u003c/span\u003e';
            html += '\u003c/div\u003e';
            html += '\u003cspan style="padding: 6px 12px; background: ' + trendBg + '; color: ' + trendColor + '; border-radius: 20px; font-weight: 600; font-size: 0.9em;"\u003e' + trendText + '\u003c/span\u003e';
            if (isEth) {
              if (longOk && shortOk) {
                html += '\u003cspan style="padding: 6px 14px; background: linear-gradient(135deg, rgba(0,255,159,0.2), rgba(255,0,128,0.2)); border: 2px solid var(--accent); border-radius: 20px; font-weight: 700; font-size: 0.95em; color: var(--text-primary);"\u003e🎯 可双向\u003c/span\u003e';
              } else if (longOk) {
                html += '\u003cspan style="padding: 6px 14px; background: linear-gradient(135deg, rgba(0,255,159,0.2), rgba(0,255,159,0.05)); border: 2px solid var(--accent); border-radius: 20px; font-weight: 700; font-size: 0.95em; color: var(--accent);"\u003e🟢 可做多\u003c/span\u003e';
              } else if (shortOk) {
                html += '\u003cspan style="padding: 6px 14px; background: linear-gradient(135deg, rgba(255,0,128,0.2), rgba(255,0,128,0.05)); border: 2px solid var(--cyber-pink); border-radius: 20px; font-weight: 700; font-size: 0.95em; color: var(--cyber-pink);"\u003e🔴 可做空\u003c/span\u003e';
              } else {
                html += '\u003cspan style="padding: 6px 12px; background: rgba(110,118,129,0.15); color: var(--text-muted); border-radius: 20px; font-weight: 600; font-size: 0.9em;"\u003e⏳ 等待中\u003c/span\u003e';
              }
            } else {
              if (shortOk) {
                html += '\u003cspan style="padding: 6px 14px; background: linear-gradient(135deg, rgba(255,0,128,0.2), rgba(255,0,128,0.05)); border: 2px solid var(--cyber-pink); border-radius: 20px; font-weight: 700; font-size: 0.95em; color: var(--cyber-pink);"\u003e🎯 可做空\u003c/span\u003e';
              } else {
                html += '\u003cspan style="padding: 6px 12px; background: rgba(110,118,129,0.15); color: var(--text-muted); border-radius: 20px; font-weight: 600; font-size: 0.9em;"\u003e⏳ 等待中\u003c/span\u003e';
              }
            }
            html += '\u003c/div\u003e';
            
            html += '\u003cdiv style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 15px 0;"\u003e';
            html += '\u003cdiv style="padding: 12px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.75em; color: var(--text-muted); margin-bottom: 4px;"\u003eEMA20\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 1.1em; font-weight: 700; color: var(--accent); font-family: monospace;"\u003e$' + (ind.ema_fast ? ind.ema_fast.toFixed(2) : '-') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003cdiv style="padding: 12px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.75em; color: var(--text-muted); margin-bottom: 4px;"\u003eEMA50\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 1.1em; font-weight: 700; color: var(--cyber-blue); font-family: monospace;"\u003e$' + (ind.ema_trend ? ind.ema_trend.toFixed(2) : '-') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003cdiv style="padding: 12px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.75em; color: var(--text-muted); margin-bottom: 4px;"\u003eEMA200\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 1.1em; font-weight: 700; color: var(--cyber-pink); font-family: monospace;"\u003e$' + (ind.ema_long ? ind.ema_long.toFixed(2) : '-') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            
            html += '\u003cdiv style="display: grid; grid-template-columns: repeat(' + (isEth ? 6 : 4) + ', 1fr); gap: 10px; margin: 12px 0;"\u003e';
            if (isEth) {
              html += '\u003cdiv style="padding: 10px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
              html += '\u003cdiv style="font-size: 0.7em; color: var(--text-muted);"\u003eRSI(4)≤' + rsiBuyFast + '\u003c/div\u003e';
              html += '\u003cdiv style="font-size: 1em; font-weight: 600; font-family: monospace;"\u003e' + (ind.rsi_fast != null ? ind.rsi_fast.toFixed(1) : '-') + (c.rsi_long ? ' ✓' : ' ✗') + '\u003c/div\u003e';
              html += '\u003c/div\u003e';
              html += '\u003cdiv style="padding: 10px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
              html += '\u003cdiv style="font-size: 0.7em; color: var(--text-muted);"\u003eRSI(14)≤' + rsiBuyMain + '\u003c/div\u003e';
              html += '\u003cdiv style="font-size: 1em; font-weight: 600; font-family: monospace;"\u003e' + (ind.rsi_main != null ? ind.rsi_main.toFixed(1) : '-') + (c.rsi_long ? ' ✓' : ' ✗') + '\u003c/div\u003e';
              html += '\u003c/div\u003e';
            }
            html += '\u003cdiv style="padding: 10px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.7em; color: var(--text-muted);"\u003eRSI(4)≥' + rsiSell + '\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 1em; font-weight: 600; font-family: monospace;"\u003e' + (ind.rsi_fast != null ? ind.rsi_fast.toFixed(1) : '-') + (c.rsi_short ? ' ✓' : ' ✗') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003cdiv style="padding: 10px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.7em; color: var(--text-muted);"\u003eRSI(14)≥' + rsiMainSell + '\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 1em; font-weight: 600; font-family: monospace;"\u003e' + (ind.rsi_main != null ? ind.rsi_main.toFixed(1) : '-') + (c.rsi_short ? ' ✓' : ' ✗') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003cdiv style="padding: 10px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.7em; color: var(--text-muted);"\u003eATR(14)\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 1em; font-weight: 600; font-family: monospace;"\u003e' + (ind.atr ? ind.atr.toFixed(2) : '-') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003cdiv style="padding: 10px; background: var(--bg-card); border-radius: 8px; text-align: center;"\u003e';
            html += '\u003cdiv style="font-size: 0.7em; color: var(--text-muted);"\u003e成交量≥65%\u003c/div\u003e';
            html += '\u003cdiv style="font-size: 0.9em; font-weight: 600;"\u003e' + (c.volume_ok ? '✓' : '✗') + '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            html += '\u003c/div\u003e';
            
            if (isEth) {
              html += '\u003cdiv style="margin: 12px 0; padding: 10px 12px; background: var(--bg-card); border-radius: 8px; font-size: 0.8em;"\u003e';
              html += '\u003cdiv style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;"\u003e';
              html += '\u003cdiv style="padding: 8px; background: rgba(0,255,159,0.05); border-radius: 6px; border: 1px solid rgba(0,255,159,0.2);"\u003e';
              html += '\u003cdiv style="color: var(--accent); font-weight: 600; margin-bottom: 4px; font-size: 0.85em;"\u003e🟢 做多条件 (both)\u003c/div\u003e';
              html += '\u003cdiv style="display: flex; flex-wrap: wrap; gap: 4px 8px;"\u003e';
              html += '\u003cspan title="EMA50>EMA200 且 价格>EMA200×0.95"\u003eRegime ' + (c.regime_long ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="价格≤BB下轨×1.01 或 价格≤EMA20×0.985"\u003ePullback ' + (c.pullback_long ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="RSI(4)≤' + rsiBuyFast + ' 且 RSI(14)≤' + rsiBuyMain + '"\u003eRSI ' + (c.rsi_long ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="成交量≥均量×65%"\u003eVolume ' + (c.volume_ok ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003c/div\u003e';
              html += '\u003c/div\u003e';
              html += '\u003cdiv style="padding: 8px; background: rgba(255,0,128,0.05); border-radius: 6px; border: 1px solid rgba(255,0,128,0.2);"\u003e';
              html += '\u003cdiv style="color: var(--cyber-pink); font-weight: 600; margin-bottom: 4px; font-size: 0.85em;"\u003e🔴 做空条件 (both)\u003c/div\u003e';
              html += '\u003cdiv style="display: flex; flex-wrap: wrap; gap: 4px 8px;"\u003e';
              html += '\u003cspan title="EMA50小于EMA200 且 价格小于EMA200×1.05"\u003eRegime ' + (c.regime_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="价格≥BB上轨×0.99 或 价格≥EMA20×1.015"\u003ePullback ' + (c.pullback_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="RSI(4)≥' + rsiSell + ' 且 RSI(14)≥' + rsiMainSell + '"\u003eRSI ' + (c.rsi_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="成交量≥均量×65%"\u003eVolume ' + (c.volume_ok ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="价格≤EMA200×1.10 未突破"\u003eNoBreakout ' + (c.not_breakout ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="收盘≤前收 或 RSI(4)下降 确认回落"\u003eStabilizing ' + (c.stabilizing_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003c/div\u003e';
              html += '\u003c/div\u003e';
              html += '\u003c/div\u003e';
              html += '\u003c/div\u003e';
            } else {
              html += '\u003cdiv style="margin: 12px 0; padding: 10px 12px; background: var(--bg-card); border-radius: 8px; font-size: 0.8em;"\u003e';
              html += '\u003cdiv style="color: var(--text-muted); margin-bottom: 6px; font-weight: 600;"\u003e🔴 做空条件 (short_only)\u003c/div\u003e';
              html += '\u003cdiv style="display: flex; flex-wrap: wrap; gap: 8px 12px;"\u003e';
              html += '\u003cspan title="EMA50小于EMA200 且 价格小于EMA200×1.05"\u003eRegime ' + (c.regime_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="价格≥BB上轨×0.99 或 价格≥EMA20×1.015"\u003ePullback ' + (c.pullback_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="RSI(4)≥' + rsiSell + ' 且 RSI(14)≥' + rsiMainSell + '"\u003eRSI ' + (c.rsi_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="成交量≥均量×65%"\u003eVolume ' + (c.volume_ok ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="价格≤EMA200×1.10 未突破"\u003eNoBreakout ' + (c.not_breakout ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003cspan title="收盘≤前收 或 RSI(4)下降 确认回落"\u003eStabilizing ' + (c.stabilizing_short ? '✓' : '✗') + '\u003c/span\u003e';
              html += '\u003c/div\u003e';
              html += '\u003c/div\u003e';
            }
            
            html += '\u003cdiv style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);"\u003e';
            html += '\u003cdiv style="text-align: center;"\u003e\u003cdiv style="font-size: 0.75em; color: var(--text-muted); margin-bottom: 4px;"\u003e价格 / BB\u003c/div\u003e';
            const bbPos = ind.bb_upper && ind.bb_lower ? (ind.price >= ind.bb_upper ? '上轨' : (ind.price <= ind.bb_lower ? '下轨' : '中轨')) : '-';
            html += '\u003cdiv style="font-size: 1em; font-weight: 600;"\u003e$' + (ind.price ? ind.price.toFixed(2) : '-') + ' / ' + bbPos + '\u003c/div\u003e\u003c/div\u003e';
            html += '\u003cdiv style="text-align: center;"\u003e\u003cdiv style="font-size: 0.75em; color: var(--text-muted); margin-bottom: 4px;"\u003eRegime\u003c/div\u003e';
            const regimeText = ind.regime_long ? '多 ✓' : (ind.regime_short ? '空 ✓' : '等待');
            html += '\u003cdiv style="font-size: 0.95em; font-weight: 600;"\u003e' + regimeText + '\u003c/div\u003e\u003c/div\u003e';
            html += '\u003c/div\u003e';
            
            html += '\u003c/div\u003e';
          }
          
          document.getElementById('indicators-content').innerHTML = html;
          document.getElementById('indicators-update-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
          
        } catch (err) {
          console.error('Failed to update indicators:', err);
        }
      }
      
      // 交易机器人状态更新
      async function updateTraderStatus() {
        try {
          const res = await fetch('/api/trader-status');
          const data = await res.json();
          
          if (!data.success) {
            document.getElementById('trader-status-content').innerHTML = '<div class="error">获取状态失败</div>';
            return;
          }
          
          const card = document.getElementById('trader-status-card');
          card.style.display = 'block';
          
          let html = '';
          
          // 运行状态
          const statusColor = data.status === 'running' ? 'var(--accent)' : 'var(--cyber-pink)';
          const statusText = data.status === 'running' ? '🟢 运行中' : '🔴 异常';
          
          html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 15px;">';
          html += '<div style="padding: 12px; background: var(--bg-card); border-radius: 8px; text-align: center;">';
          html += '<div style="font-size: 0.8em; color: var(--text-muted); margin-bottom: 4px;">运行状态</div>';
          html += '<div style="font-size: 1.1em; font-weight: 700; color: ' + statusColor + ';">' + statusText + '</div>';
          html += '</div>';
          html += '<div style="padding: 12px; background: var(--bg-card); border-radius: 8px; text-align: center;">';
          html += '<div style="font-size: 0.8em; color: var(--text-muted); margin-bottom: 4px;">运行时长</div>';
          html += '<div style="font-size: 1em; font-weight: 600; color: var(--cyber-blue);">' + (data.uptime || 'unknown') + '</div>';
          html += '</div>';
          html += '</div>';
          
          // 策略配置
          html += '<div style="margin: 12px 0; padding: 12px; background: var(--bg-card); border-radius: 8px;">';
          html += '<div style="font-size: 0.85em; color: var(--text-muted); margin-bottom: 8px;">📋 策略配置</div>';
          html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.9em;">';
          html += '<div>BTC: <span style="color: var(--cyber-pink);">' + (data.config?.tradeSide?.BTC || 'short_only') + '</span></div>';
          html += '<div>ETH: <span style="color: var(--accent);">' + (data.config?.tradeSide?.ETH || 'both') + '</span></div>';
          html += '<div>检查间隔: ' + (data.config?.checkInterval || '60s') + '</div>';
          html += '<div>冷却期: ' + (data.config?.cooldown || '4h') + '</div>';
          html += '</div>';
          html += '</div>';
          
          // 最新信号
          if (data.lastSignals) {
            html += '<div style="margin: 12px 0; padding: 12px; background: var(--bg-card); border-radius: 8px;">';
            html += '<div style="font-size: 0.85em; color: var(--text-muted); margin-bottom: 8px;">📊 最新信号</div>';
            html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">';
            
            for (const [symbol, signal] of Object.entries(data.lastSignals)) {
              const isHold = signal.action === 'HOLD';
              const signalColor = isHold ? 'var(--text-muted)' : (signal.action === 'BUY' ? 'var(--accent)' : 'var(--cyber-pink)');
              const signalIcon = isHold ? '⏳' : (signal.action === 'BUY' ? '🟢' : '🔴');
              
              html += '<div style="padding: 8px; background: var(--bg-secondary); border-radius: 6px; text-align: center;">';
              html += '<div style="font-weight: 600;">' + symbol + '</div>';
              html += '<div style="font-size: 0.85em; color: ' + signalColor + ';">' + signalIcon + ' ' + (isHold ? '等待中' : signal.action) + '</div>';
              if (signal.reason) {
                html += '<div style="font-size: 0.75em; color: var(--text-muted);">' + signal.reason + '</div>';
              }
              html += '</div>';
            }
            
            html += '</div>';
            html += '</div>';
          }
          
          // 最近日志
          if (data.recentLogs && data.recentLogs.length > 0) {
            html += '<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);">';
            html += '<div style="font-size: 0.8em; color: var(--text-muted); margin-bottom: 6px;">📝 最近日志</div>';
            html += '<div style="font-size: 0.75em; font-family: monospace; color: var(--text-secondary);">';
            data.recentLogs.slice(-3).forEach(log => {
              const logParts = log.split(' - ');
              if (logParts.length >= 3) {
                html += '<div style="margin: 2px 0;">' + logParts[0].split(' ')[1] + ' ' + logParts[2] + '</div>';
              }
            });
            html += '</div>';
            html += '</div>';
          }
          
          document.getElementById('trader-status-content').innerHTML = html;
          document.getElementById('trader-status-update-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
          
        } catch (err) {
          console.error('Failed to update trader status:', err);
        }
      }
      
      // 所有交易机器人状态汇总
      async function updateAllTradersStatus() {
        try {
          const res = await fetch('/api/traders-status');
          const data = await res.json();
          
          if (!data.success) {
            document.getElementById('all-traders-content').innerHTML = '<div class="error">获取状态失败</div>';
            return;
          }
          
          const content = document.getElementById('all-traders-content');
          
          // 统计在线数量
          const runningCount = data.traders.filter(t => t.status === 'running').length;
          const totalCount = data.traders.length;
          
          let html = '<div style="margin-bottom: 15px; text-align: center;">';
          html += '<span style="font-size: 1.2em; color: var(--accent);">🟢 ' + runningCount + '</span>';
          html += '<span style="color: var(--text-muted);"> / ' + totalCount + ' 在线</span>';
          html += '</div>';
          
          html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;">';
          
          data.traders.forEach(trader => {
            const isRunning = trader.status === 'running';
            const statusColor = isRunning ? 'var(--accent)' : 'var(--cyber-pink)';
            const statusIcon = isRunning ? '🟢' : '🔴';
            
            html += '<div style="padding: 12px; background: var(--bg-card); border-radius: 8px; border-left: 3px solid ' + statusColor + ';">';
            html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
            html += '<div style="font-weight: 600; color: var(--text-primary);">' + statusIcon + ' ' + trader.name + '</div>';
            html += '<div style="font-size: 0.75em; color: ' + statusColor + ';">' + (isRunning ? '运行中' : '离线') + '</div>';
            html += '</div>';
            
            // 最新信号
            if (trader.lastSignal && Object.keys(trader.lastSignal).length > 0) {
              html += '<div style="font-size: 0.8em; margin-top: 8px;">';
              Object.entries(trader.lastSignal).forEach(([coin, signal]) => {
                const actionColor = signal.action === 'LONG' ? 'var(--accent)' : signal.action === 'SHORT' ? 'var(--cyber-pink)' : 'var(--text-muted)';
                html += '<div style="margin: 2px 0;">';
                html += '<span style="color: var(--cyber-blue); font-weight: 600;">' + coin + '</span>: ';
                html += '<span style="color: ' + actionColor + ';">' + signal.action + '</span>';
                if (signal.reason) {
                  html += ' <span style="color: var(--text-muted);">(' + signal.reason.substring(0, 30) + '...)</span>';
                }
                html += '</div>';
              });
              html += '</div>';
            } else {
              html += '<div style="font-size: 0.8em; color: var(--text-muted); margin-top: 8px;">暂无信号</div>';
            }
            
            html += '</div>';
          });
          
          html += '</div>';
          
          // 最近日志汇总
          html += '<div style="margin-top: 15px; padding: 12px; background: var(--bg-card); border-radius: 8px;">';
          html += '<div style="font-size: 0.8em; color: var(--text-muted); margin-bottom: 8px;">📝 最近动态</div>';
          html += '<div style="font-size: 0.75em; font-family: monospace; max-height: 100px; overflow-y: auto;">';
          
          // 收集所有日志按时间排序
          let allLogs = [];
          data.traders.forEach(trader => {
            if (trader.recentLogs) {
              trader.recentLogs.forEach(log => {
                allLogs.push({ trader: trader.name, log: log });
              });
            }
          });
          
          // 显示最近5条
          allLogs.slice(-5).forEach(item => {
            const logParts = item.log.split(' - ');
            if (logParts.length >= 3) {
              const time = logParts[0].split(' ')[1] || '';
              const msg = logParts[2] || '';
              html += '<div style="margin: 2px 0; color: var(--text-secondary);">';
              html += '<span style="color: var(--cyber-blue);">[' + time + ']</span> ';
              html += '<span style="color: var(--accent);">' + item.trader + '</span>: ';
              html += msg;
              html += '</div>';
            }
          });
          
          html += '</div>';
          html += '</div>';
          
          content.innerHTML = html;
          document.getElementById('all-traders-update-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
          
        } catch (err) {
          console.error('Failed to update all traders status:', err);
          document.getElementById('all-traders-content').innerHTML = '<div class="error">加载失败</div>';
        }
      }
      
      // 立即更新一次，然后每 30 秒更新
      updatePosition();
      updateIndicators();
      updateTraderStatus();
      updateAllTradersStatus();
      setInterval(updatePosition, 30000);
      setInterval(updateIndicators, 30000);
      setInterval(updateTraderStatus, 30000);
      setInterval(updateAllTradersStatus, 30000);
    </script>
  `;
  
  res.send(getHTML(content));
});

// K线图表页面
app.get('/chart', (req, res) => {
  const content = `
    <header>
      <h1>📊 1分钟K线图表 + EMA</h1>
      <p class="subtitle">当前实盘策略：NFI short_only；下方 EMA 金叉/死叉仅作图表参考</p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div style="margin: 20px 0; display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 10px;">
      <span style="color: var(--text-muted); margin-right: 5px;">时间范围:</span>
      <button onclick="setRange1m(10)" id="btn-range-10m" style="padding: 8px 14px; margin: 0 2px; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; cursor: pointer;">10分钟</button>
      <button onclick="setRange1m(30)" id="btn-range-30m" style="padding: 8px 14px; margin: 0 2px; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; cursor: pointer;">30分钟</button>
      <button onclick="setRange1m(60)" id="btn-range-60m" style="padding: 8px 14px; margin: 0 2px; background: var(--accent); color: var(--bg-primary); border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">1小时</button>
      <button onclick="setRange1m(1440)" id="btn-range-24h" style="padding: 8px 14px; margin: 0 2px; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; cursor: pointer;">24小时</button>
    </div>
    
    <style>@media (max-width: 900px) { .chart-grid { grid-template-columns: 1fr !important; } }</style>
    <div class="chart-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
      <div>
        <h3 style="margin-bottom: 10px; color: var(--accent);">BTC</h3>
        <div id="chart-container-btc" style="background: var(--bg-card); padding: 20px; border-radius: 8px; border: 1px solid var(--border); min-height: 350px;">
          <div style="text-align: center; padding: 50px; color: var(--text-muted);">加载中...</div>
        </div>
        <div id="signals-container-btc" style="margin-top: 15px;"></div>
      </div>
      <div>
        <h3 style="margin-bottom: 10px; color: var(--accent);">ETH</h3>
        <div id="chart-container-eth" style="background: var(--bg-card); padding: 20px; border-radius: 8px; border: 1px solid var(--border); min-height: 350px;">
          <div style="text-align: center; padding: 50px; color: var(--text-muted);">加载中...</div>
        </div>
        <div id="signals-container-eth" style="margin-top: 15px;"></div>
      </div>
    </div>
    <div style="margin-top: 15px; padding: 12px 16px; background: var(--bg-card); border-radius: 6px; border: 1px solid var(--border); font-size: 0.85em; color: var(--text-muted);">
      <strong style="color: var(--text-primary);">📋 当前实盘规则：</strong> NFI short_only（默认只做空），基于 EMA/RSI/布林带/成交量过滤。此页展示的 EMA 金叉死叉仅用于辅助观察，不等同实盘入场条件。
    </div>
    
    <!-- 引入 Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <script>
      function renderSignals(signals, containerId, emptyText) {
        const container = document.getElementById(containerId);
        
        if (!signals || signals.length === 0) {
          container.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-muted);">' + (emptyText || '当前时段无可交易信号') + '</div>';
          return;
        }
        
        let html = '<div style="background: var(--bg-card); padding: 20px; border-radius: 8px; border: 1px solid var(--border);">';
        html += '<h3 style="margin-bottom: 15px; color: var(--accent);">✅ 可交易信号 (' + signals.length + '个)</h3>';
        html += '<div style="display: grid; gap: 10px;">';
        
        signals.slice(-10).reverse().forEach(s => {
          const isGolden = s.type === 'golden_cross';
          const color = isGolden ? 'var(--accent)' : 'var(--cyber-pink)';
          const bg = isGolden ? 'rgba(0,255,159,0.1)' : 'rgba(255,0,128,0.1)';
          const icon = isGolden ? '🔥✨' : '❄️⚡';
          const text = isGolden ? '金叉买入' : '死叉卖出';
          const date = new Date(s.timestamp).toLocaleString('zh-CN');
          
          html += '<div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: ' + bg + '; border-radius: 6px; border-left: 3px solid ' + color + ';">';
          html += '<div>';
          html += '<div style="font-size: 1.2em; margin-bottom: 4px;">' + icon + ' ' + text + '</div>';
          html += '<div style="font-size: 0.85em; color: var(--text-muted);">' + date + '</div>';
          html += '</div>';
          html += '<div style="font-size: 1.3em; font-weight: 700; color: ' + color + '; font-family: monospace;">$' + s.price.toFixed(2) + '</div>';
          html += '</div>';
        });
        
        html += '</div></div>';
        container.innerHTML = html;
      }
      
      let currentChartBtc = null;
      let currentChartEth = null;
      let currentMinutes1m = 60;
      
      const rangeLabels = { 10: '10分钟', 30: '30分钟', 60: '1小时', 1440: '24小时' };
      
      function setRange1m(minutes) {
        currentMinutes1m = minutes;
        ['btn-range-10m', 'btn-range-30m', 'btn-range-60m', 'btn-range-24h'].forEach((id) => {
          const btn = document.getElementById(id);
          const isActive = (id === 'btn-range-10m' && minutes === 10) || (id === 'btn-range-30m' && minutes === 30) || (id === 'btn-range-60m' && minutes === 60) || (id === 'btn-range-24h' && minutes === 1440);
          btn.style.background = isActive ? 'var(--accent)' : 'var(--bg-card)';
          btn.style.color = isActive ? 'var(--bg-primary)' : 'var(--text-primary)';
          btn.style.border = isActive ? 'none' : '1px solid var(--border)';
          btn.style.fontWeight = isActive ? '600' : 'normal';
        });
        loadAllCharts();
      }
      
      async function loadChartForSymbol(symbol) {
        const chartContainerId = 'chart-container-' + symbol.toLowerCase();
        const signalsContainerId = 'signals-container-' + symbol.toLowerCase();
        const rangeText = rangeLabels[currentMinutes1m] || currentMinutes1m + '分钟';
        
        document.getElementById(chartContainerId).innerHTML = '<div style="text-align: center; padding: 50px; color: var(--text-muted);">正在加载 ' + symbol + '...</div>';
        
        try {
          const res = await fetch('/api/chart/' + symbol + '?interval=1m&minutes=' + currentMinutes1m);
          const data = await res.json();
          
          if (!data.success) {
            document.getElementById(chartContainerId).innerHTML = '<div style="text-align: center; padding: 50px; color: var(--cyber-pink);">加载失败: ' + (data.error || '未知错误') + '</div>';
            return;
          }
          
          renderChart1m(data, symbol);
          const emptyText = '近' + rangeText + '无可交易信号';
          renderSignals(data.signals, signalsContainerId, emptyText);
          
        } catch (err) {
          console.error('加载' + symbol + '图表失败:', err);
          document.getElementById(chartContainerId).innerHTML = '<div style="text-align: center; padding: 50px; color: var(--cyber-pink);">加载失败</div>';
        }
      }
      
      function loadAllCharts() {
        loadChartForSymbol('BTC');
        loadChartForSymbol('ETH');
      }
      
      function renderChart1m(data, symbol) {
        const chartContainerId = 'chart-container-' + symbol.toLowerCase();
        const container = document.getElementById(chartContainerId);
        const canvasId = 'klineChart-' + symbol.toLowerCase();
        const rangeText = rangeLabels[currentMinutes1m] || '1小时';
        container.innerHTML = '<canvas id="' + canvasId + '"></canvas>';
        
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        const labels = data.klines.map(k => new Date(k.timestamp));
        const prices = data.klines.map(k => k.close);
        const ema9 = data.klines.map(k => k.ema9);
        const ema21 = data.klines.map(k => k.ema21);
        const ema55 = data.klines.map(k => k.ema55);
        
        const goldenCrossPoints = data.signals
          .filter(s => s.type === 'golden_cross')
          .map(s => ({ x: new Date(s.timestamp), y: s.price }));
        
        const deathCrossPoints = data.signals
          .filter(s => s.type === 'death_cross')
          .map(s => ({ x: new Date(s.timestamp), y: s.price }));
        
        const chartRef = symbol === 'BTC' ? currentChartBtc : currentChartEth;
        if (chartRef) chartRef.destroy();
        const newChart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [
              { label: '价格', data: prices, borderColor: '#00d4ff', backgroundColor: 'rgba(0, 212, 255, 0.1)', borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 },
              { label: 'EMA9', data: ema9, borderColor: '#00ff9f', borderWidth: 2, pointRadius: 0, pointHoverRadius: 3, tension: 0.3 },
              { label: 'EMA21', data: ema21, borderColor: '#bf00ff', borderWidth: 2, pointRadius: 0, pointHoverRadius: 3, tension: 0.3 },
              { label: 'EMA55', data: ema55, borderColor: '#ff0080', borderWidth: 2, pointRadius: 0, pointHoverRadius: 3, tension: 0.3, borderDash: [5, 5] },
              { label: '金叉', data: goldenCrossPoints, backgroundColor: '#00ff9f', borderColor: '#00ff9f', pointStyle: 'triangle', pointRadius: 10, pointHoverRadius: 12, showLine: false },
              { label: '死叉', data: deathCrossPoints, backgroundColor: '#ff0080', borderColor: '#ff0080', pointStyle: 'triangle', pointRadius: 10, pointHoverRadius: 12, rotation: 180, showLine: false }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            height: 500,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              title: { display: true, text: data.symbol + '/USD 1分钟K线 + EMA（近' + rangeText + '）', color: '#e6edf3', font: { size: 16 } },
              legend: { labels: { color: '#8b949e' } },
              tooltip: {
                backgroundColor: 'rgba(22, 27, 34, 0.95)',
                titleColor: '#e6edf3',
                bodyColor: '#8b949e',
                borderColor: '#30363d',
                borderWidth: 1,
                callbacks: { label: function(context) { let l = context.dataset.label || ''; if (l) l += ': '; if (context.parsed.y !== null) l += '$' + context.parsed.y.toFixed(2); return l; } }
              }
            },
            scales: {
              x: { type: 'time', time: { displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MM-dd' } }, ticks: { color: '#6e7681' }, grid: { color: '#30363d' } },
              y: { ticks: { color: '#6e7681', callback: function(v) { return '$' + v.toLocaleString(); } }, grid: { color: '#30363d' } }
            }
          }
        });
        if (symbol === 'BTC') currentChartBtc = newChart; else currentChartEth = newChart;
      }
      
      // 初始加载
      loadAllCharts();
    </script>
  `;
  
  res.send(getHTML(content));
});

// 单篇文章
app.get('/entry/:slug', (req, res) => {
  const entry = ENTRIES.find(e => e.slug === req.params.slug);
  
  if (!entry) {
    return res.status(404).send(getHTML('<header><h1>404 - 文章未找到</h1><p><a href="/">← 返回首页</a></p></header>'));
  }
  
  const content = `
    <header>
      <h1>${entry.title}</h1>
      <p class="subtitle">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div class="entry" style="margin-top: 20px;">
      <div class="entry-content">
        ${renderMarkdown(entry.content)}
      </div>
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
  `;
  
  res.send(getHTML(content));
});

// 策略页面
app.get('/strategy', (req, res) => {
  const strat = STRATEGY?.strategy || {};
  const indicators = STRATEGY?.indicators || [];
  const entryRules = STRATEGY?.entryRules || {};
  const exitRules = STRATEGY?.exitRules || {};
  const risk = STRATEGY?.riskManagement || {};
  
  const indicatorsHTML = indicators.map(ind => `
    <div class="position-item" style="margin-bottom: 10px;">
      <div class="position-row">
        <span class="coin" style="font-size: 1.1em;">${ind.name}</span>
        <span class="tag">周期: ${ind.period}</span>
      </div>
      <div style="color: var(--text-secondary); margin-top: 8px; font-size: 0.9em;">
        ${ind.description}
      </div>
    </div>
  `).join('');
  
  const longRules = (entryRules.long || []).map(rule => `<li style="margin: 8px 0;">${rule}</li>`).join('');
  const shortRules = (entryRules.short || []).map(rule => `<li style="margin: 8px 0;">${rule}</li>`).join('');
  
  const content = `
    <header>
      <h1>🎯 交易策略</h1>
      <p class="subtitle">${strat.name || '趋势跟踪策略'} <span class="tag">v${strat.version || '1.0'}</span></p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/learn" style="font-size: 0.85em;">📚 学习资料</a>
      </div>
    </header>
    
    <div class="wallet-card" style="margin-top: 30px;">
      <h3>📋 策略概述</h3>
      <p style="color: var(--text-secondary); line-height: 1.8;">${strat.description || '基于多时间框架均线系统的趋势跟踪策略'}</p>
      <div style="margin-top: 15px; display: flex; gap: 20px; flex-wrap: wrap;">
        <span class="tag">状态: ${strat.status === 'active' ? '✅ 运行中' : '⏸️ 暂停'}</span>
        <span class="tag">市场: ${(STRATEGY.markets?.primary || []).join(', ')}</span>
        <span class="tag">周期: ${STRATEGY.markets?.timeframe || '1h'}</span>
      </div>
    </div>
    
    <div class="position-card">
      <div class="position-header">
        <h3>📊 技术指标</h3>
      </div>
      ${indicatorsHTML || '<p style="color: var(--text-muted);">暂无指标配置</p>'}
    </div>
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 30px 0;">
      <div class="wallet-card" style="border-color: var(--accent);">
        <h3 style="color: var(--accent);">📈 做多条件</h3>
        <ul style="color: var(--text-secondary); padding-left: 20px;">
          ${longRules || '<li>暂无配置</li>'}
        </ul>
      </div>
      
      <div class="wallet-card" style="border-color: var(--cyber-pink);">
        <h3 style="color: var(--cyber-pink);">📉 做空条件</h3>
        <ul style="color: var(--text-secondary); padding-left: 20px;">
          ${shortRules || '<li>暂无配置</li>'}
        </ul>
      </div>
    </div>
    
    <div class="wallet-card">
      <h3>🚪 出场规则</h3>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">止损</div>
          <div class="stat-value" style="font-size: 1.5em; color: var(--cyber-pink);">${exitRules.stopLoss || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">止盈</div>
          <div class="stat-value" style="font-size: 1.5em; color: var(--accent);">${exitRules.takeProfit || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">移动止损</div>
          <div class="stat-value" style="font-size: 1.5em; color: var(--cyber-blue);">${exitRules.trailingStop || '-'}</div>
        </div>
      </div>
    </div>
    
    <div class="position-card">
      <div class="position-header">
        <h3>🛡️ 风险管理</h3>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">日最大回撤</div>
          <div class="stat-value pink" style="font-size: 1.5em;">${risk.maxDailyDrawdown || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">单笔止损</div>
          <div class="stat-value pink" style="font-size: 1.5em;">${risk.stopLossPerTrade || '-'}</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">最大杠杆</div>
          <div class="stat-value blue" style="font-size: 1.5em;">${STRATEGY.positionSizing?.maxLeverage || '-'}x</div>
        </div>
        <div class="stat-card" style="padding: 15px;">
          <div class="stat-label">冷静期</div>
          <div class="stat-value" style="font-size: 1.5em;">${risk.cooldownAfterLoss || '-'}</div>
        </div>
      </div>
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
  `;
  
  res.send(getHTML(content));
});

// 学习资料页面
app.get('/learn', (req, res) => {
  const learnHTML = LEARN_ENTRIES.map(entry => {
    const preview = entry.content.substring(0, 150).replace(/\*/g, '').replace(/\n/g, ' ');
    return `
    <div class="entry">
      <h2><a href="/learn/${entry.slug}">${entry.title}</a></h2>
      <div class="entry-meta">
        📅 ${formatDate(entry.date)}
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </div>
      <div class="entry-content">
        <p>${preview}...</p>
      </div>
      <a href="/learn/${entry.slug}" class="read-link">阅读全文 →</a>
    </div>
  `}).join('') || '<p style="color: var(--text-muted); text-align: center; padding: 40px;">暂无学习资料</p>';
  
  const content = `
    <header>
      <h1>📚 学习资料</h1>
      <p class="subtitle">交易策略、市场分析与风险管理</p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div class="entries">
      ${learnHTML}
    </div>
    
    <a href="/" class="back-link">← 返回首页</a>
  `;
  
  res.send(getHTML(content));
});

// 学习资料单篇文章
app.get('/learn/:slug', (req, res) => {
  const entry = LEARN_ENTRIES.find(e => e.slug === req.params.slug);
  
  if (!entry) {
    return res.status(404).send(getHTML('<header><h1>404 - 文章未找到</h1><p><a href="/">← 返回首页></p></header>'));
  }
  
  const content = `
    <header>
      <h1>${entry.title}</h1>
      <p class="subtitle">
        📅 ${formatDate(entry.date)} 
        ${entry.tags.map(t => `<span class="tag">#${t}</span>`).join('')}
      </p>
      <div style="margin-top: 15px; display: flex; justify-content: center; gap: 15px;">
        <a href="/" style="font-size: 0.85em;">← 返回首页</a>
        <a href="/learn" style="font-size: 0.85em;">📚 学习资料</a>
        <a href="/strategy" style="font-size: 0.85em;">🎯 交易策略</a>
      </div>
    </header>
    
    <div class="entry" style="margin-top: 20px;">
      <div class="entry-content">
        ${renderMarkdown(entry.content)}
      </div>
    </div>
    
    <a href="/learn" class="back-link">← 返回学习资料</a>
  `;
  
  res.send(getHTML(content));
});

// 404 处理
app.use((req, res) => {
  res.status(404).send(getHTML('<header><h1>404 - 页面未找到</h1><p><a href="/">← 返回首页</a></p></header>'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n🐴 小牛马炒币网站启动成功！\n`);
  console.log(`本地访问: http://localhost:${PORT}`);
  console.log(`公网访问: http://15.152.86.199:${PORT}`);
  console.log(`\n按 Ctrl+C 停止服务器\n`);
});
