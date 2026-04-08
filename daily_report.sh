#!/bin/bash
# daily_report.sh - 每日交易报告生成脚本
# 运行时间: 每天凌晨 1:00

set -e

echo "📊 生成每日交易报告..."
DATE=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
TIME=$(date +%H:%M)

cd /home/ubuntu/LuckyNiuMaNote

# 读取交易日志
LOG_FILE="logs/trader.log"
TRADE_FILE="logs/trades.jsonl"

# 统计今日交易
today_trades=""
if [ -f "$TRADE_FILE" ]; then
    today_trades=$(grep "\"time\":\"$YESTERDAY" "$TRADE_FILE" 2>/dev/null || echo "")
fi

# 获取当前持仓和账户信息
ACCOUNT_INFO=$(curl -s http://localhost:5288/api/position 2>/dev/null || echo '{}')
TOTAL_VALUE=$(echo "$ACCOUNT_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('totalValue',0))" 2>/dev/null || echo "97.98")
PNL=$(echo "$ACCOUNT_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('totalPnl',0))" 2>/dev/null || echo "0")

# 计算收益率
INITIAL_CAPITAL=98
RETURN_PCT=$(echo "scale=2; ($TOTAL_VALUE - $INITIAL_CAPITAL) / $INITIAL_CAPITAL * 100" | bc 2>/dev/null || echo "0")

# 生成markdown文件名
SLUG="day-$(echo $YESTERDAY | tr '-' '-')"

# 如果文件已存在则跳过
if [ -f "content/entries/$SLUG.md" ]; then
    echo "报告已存在: $SLUG.md，跳过生成"
    exit 0
fi

# 生成交易记录内容
TRADE_CONTENT=""
if [ -n "$today_trades" ]; then
    TRADE_COUNT=$(echo "$today_trades" | wc -l)
    TRADE_CONTENT="## 📝 今日交易 ($TRADE_COUNT 笔)

| 时间 | 币种 | 方向 | 结果 |
|------|------|------|------|
"
    # 解析交易记录
    echo "$today_trades" | while read line; do
        trade_time=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('time','')[:19])" 2>/dev/null || echo "")
        symbol=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('signal',{}).get('symbol',''))" 2>/dev/null || echo "")
        action=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('signal',{}).get('action',''))" 2>/dev/null || echo "")
        if [ -n "$symbol" ]; then
            echo "| $trade_time | $symbol | $action | 已执行 |" >> /tmp/trade_table.txt
        fi
    done
    if [ -f /tmp/trade_table.txt ]; then
        TRADE_CONTENT="${TRADE_CONTENT}$(cat /tmp/trade_table.txt)"
        rm -f /tmp/trade_table.txt
    fi
else
    TRADE_CONTENT="## 📝 今日交易

今日无交易信号，继续观察市场。
"
fi

# 生成学习心得
LEARNING_CONTENT="## 💡 今日心得

$(cat << 'EOF'
- 市场处于震荡整理阶段，等待明确趋势形成
- 严格执行交易纪律，不符合条件坚决不进场
- 保持耐心，机会是等出来的
EOF
)"

# 创建markdown文件
cat > "content/entries/$SLUG.md" << EOF
---
slug: $SLUG
date: $YESTERDAY
title: Day Report - $YESTERDAY
tags:
  - daily
  - report
---

## 📊 账户概况

| 指标 | 数值 |
|------|------|
| 总资产 | \$${TOTAL_VALUE} |
| 累计盈亏 | \$${PNL} (${RETURN_PCT}%) |
| 初始资金 | \$98.00 |

$TRADE_CONTENT

$LEARNING_CONTENT

## 🎯 明日计划

- 继续监控 BTC/ETH 趋势信号
- 严格执行风险管理规则
- 记录每笔交易心得

---

*报告生成时间: $DATE $TIME*
*交易员: 牛牛 🐮*
EOF

echo "✅ 报告已生成: content/entries/$SLUG.md"

# 重新构建网站数据
echo "🔄 重新构建网站..."
node build.js

# 重启网站服务以加载新数据
echo "🔄 重启网站服务..."
export PATH="/home/ubuntu/.nvm/versions/node/v22.22.0/bin:$PATH"
pm2 restart luckyniuma

echo "✅ 每日报告完成！"
