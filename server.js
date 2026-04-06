const express = require('express');
const path = require('path');
const fs = require('fs');
const https = require('https');
const { spawnSync } = require('child_process');

const app = express();
const PORT = parseInt(process.env.PORT || '3000', 10);
const LISTEN_HOST = process.env.LISTEN_HOST || '0.0.0.0';
const DIST_DIR = path.resolve(__dirname, 'frontend/dist');
const DIST_INDEX = path.join(DIST_DIR, 'index.html');

if (process.env.TRUST_PROXY === '1') {
  app.set('trust proxy', 1);
}

// 主钱包地址
const WALLET_ADDRESS = '0xfFd91a584cf6419b92E58245898D2A9281c628eb';
const HL_API = 'https://api.hyperliquid.xyz/info';

/** 检测策略脚本是否由 Python 进程加载（pgrep 用脚本文件名匹配相对路径 argv，禁止仅用绝对路径） */
function isTraderProcessRunning(scriptFile) {
  const r = spawnSync('pgrep', ['-f', scriptFile], { encoding: 'utf8' });
  if (r.status !== 0) return false;
  const pids = r.stdout.trim().split('\n').filter(Boolean);
  for (const pid of pids) {
    try {
      const cmd = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').replace(/\0/g, ' ');
      if (/\bpython3?\b/i.test(cmd) && cmd.includes(scriptFile)) return true;
    } catch (_) { /* 非 Linux 或进程已退出 */ }
  }
  return false;
}

function firstTraderPidForScript(scriptFile) {
  const r = spawnSync('pgrep', ['-f', scriptFile], { encoding: 'utf8' });
  if (r.status !== 0) return null;
  const pids = r.stdout.trim().split('\n').filter(Boolean);
  for (const pid of pids) {
    try {
      const cmd = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').replace(/\0/g, ' ');
      if (/\bpython3?\b/i.test(cmd) && cmd.includes(scriptFile)) return pid;
    } catch (_) {}
  }
  return null;
}

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

// 静态文件服务 - React前端
app.use('/public', express.static(path.join(__dirname, 'public')));
app.use('/data-export', express.static(path.join(__dirname, 'data-export')));
app.use(express.static(DIST_DIR));

// 所有路由返回React应用的index.html (SPA支持)
app.get(['/', '/dashboard', '/strategy', '/learn', '/chart', '/entry/:slug'], (req, res) => {
  try {
    const html = fs.readFileSync(DIST_INDEX, 'utf8');
    res.type('html').send(html);
  } catch (err) {
    console.error('Failed to serve SPA index:', DIST_INDEX, err.message);
    res.status(500).send('SPA index not found');
  }
});

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
    
    const nfiPid = firstTraderPidForScript('auto_trader_nostalgia_for_infinity.py');
    if (nfiPid && status !== 'running') status = 'running';
    let traderProcess = 'unknown';
    if (nfiPid) {
      const et = spawnSync('ps', ['-o', 'etime=', '-p', nfiPid], { encoding: 'utf8' });
      traderProcess = (et.stdout || '').trim() || 'unknown';
    }
    
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

// 所有交易机器人状态汇总
app.get('/api/traders-status', (req, res) => {
  try {
    const traders = [
      { id: 'nfi',               name: 'NFI原版',        description: '多指标综合（EMA20/50/200 + RSI + BB + ATR），仅做空',                        logFile: 'trader_nfi.log',                 script: 'auto_trader_nostalgia_for_infinity.py' },
      { id: 'boll_macd',         name: 'BOLL+MACD V3',   description: 'MACD14(BTC)/BB15(ETH) 共振，1.5ATR止损/2.5ATR止盈 + 跟踪止损',             logFile: 'trader_01_boll_macd.log',         script: 'trader_01_boll_macd.py' },
      { id: 'supertrend',        name: 'SuperTrend×4.0', description: 'ATR×4.0优化版，过滤假信号，趋势跟随',                                        logFile: 'trader_04_supertrend.log',        script: 'trader_04_supertrend.py' },
      { id: 'adx',               name: 'ADX趋势过滤',    description: 'ADX衡量趋势强度，BTC:EMA15/ETH:EMA30优化',                                    logFile: 'trader_05_adx.log',               script: 'trader_05_adx.py' },
    ];

    const results = traders.map(trader => {
      const logPath = path.join(__dirname, 'logs', trader.logFile);
      let lastSignal = {};
      let lastLines = [];
      let lastActive = null;

      const status = isTraderProcessRunning(trader.script) ? 'running' : 'offline';

      if (fs.existsSync(logPath)) {
        lastActive = fs.statSync(logPath).mtime.getTime();
        const logContent = fs.readFileSync(logPath, 'utf-8');
        const lines = logContent.split('\n').filter(line => line.trim());
        lastLines = lines.slice(-10);

        for (let i = lines.length - 1; i >= Math.max(0, lines.length - 50); i--) {
          const line = lines[i];
          const match = line.match(/(BTC|ETH)\s+(HOLD|LONG|SHORT)[^:]*:\s*(.+)/);
          if (match && !lastSignal[match[1]]) {
            const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
            lastSignal[match[1]] = { action: match[2], reason: match[3].trim(), time: tsMatch ? tsMatch[1] : null };
          }
          const tradeMatch = line.match(/【(开仓|平仓)】(BTC|ETH)\s+(LONG|SHORT)/);
          if (tradeMatch && !lastSignal[tradeMatch[2]]) {
            const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
            lastSignal[tradeMatch[2]] = { action: tradeMatch[3], reason: tradeMatch[1], time: tsMatch ? tsMatch[1] : null };
          }
          if (Object.keys(lastSignal).length === 2) break;
        }
      }

      return { id: trader.id, name: trader.name, description: trader.description, status, lastSignal, lastActive, recentLogs: lastLines.slice(-3) };
    });

    res.json({ success: true, timestamp: Date.now(), traders: results });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
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
  min_volume_ratio: 0.45
};
const NFI_ETH_OVERRIDES = { rsi_fast_sell: 75, rsi_main_sell: 62, min_volume_ratio: 0.35 };

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
        const leverage = pos.leverage || {};

        return {
          coin: pos.coin,
          size: Math.abs(size),
          side: size > 0 ? 'LONG' : 'SHORT',
          leverage: leverage.value ? parseInt(leverage.value) : null,
          leverageType: (leverage.type || 'cross').charAt(0).toUpperCase() + (leverage.type || 'cross').slice(1),
          positionValue: parseFloat(pos.positionValue || 0),
          entryPx: parseFloat(pos.entryPx),
          currentPx: parseFloat(mids[pos.coin] || 0),
          pnl: parseFloat(pos.unrealizedPnl),
          roe: parseFloat(pos.returnOnEquity || 0),
          marginUsed: parseFloat(pos.marginUsed || 0),
          cumFunding: parseFloat((pos.cumFunding || {}).sinceOpen || 0),
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

    // 未实现盈亏（当前持仓浮动盈亏之和）
    const unrealizedPnl = positions.reduce((sum, p) => sum + p.pnl, 0);

    // 总资产 = 交易平台 USDC "总余额"（spotClearinghouseState）
    const usdcBalance = spotBalances.find(b => b.coin === 'USDC');
    const totalValue = usdcBalance ? usdcBalance.total : 0;
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
        totalPnlPct: totalPnlPct,
        unrealizedPnl: unrealizedPnl
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

// ==================== 前端静态资源 ====================
const frontendDistPath = path.join(__dirname, 'frontend', 'dist');

if (fs.existsSync(frontendDistPath)) {
  app.use(express.static(frontendDistPath));
  app.get(/^\/(?!api).*/, (req, res) => {
    res.sendFile(path.join(frontendDistPath, 'index.html'));
  });
} else {
  app.get(/^\/(?!api).*/, (req, res) => {
    res.status(503).send('前端资源未构建，请先执行 npm --prefix frontend run build');
  });
}

app.listen(PORT, LISTEN_HOST, () => {
  const publicUrl = process.env.SITE_PUBLIC_URL;
  console.log(`\n🐴 小牛马炒币网站启动成功！\n`);
  console.log(`监听: http://${LISTEN_HOST}:${PORT}`);
  if (publicUrl) console.log(`站点: ${publicUrl}`);
  console.log(`\n按 Ctrl+C 停止服务器\n`);
});
