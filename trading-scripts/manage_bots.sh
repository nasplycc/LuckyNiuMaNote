#!/bin/bash
# 量化交易机器人管理脚本

cd /home/ubuntu/LuckyNiuMaNote/trading-scripts

case "$1" in
  start)
    echo "启动所有交易机器人..."
    pm2 start ecosystem.config.json
    ;;
  stop)
    echo "停止所有交易机器人..."
    pm2 stop ecosystem.config.json
    ;;
  restart)
    echo "重启所有交易机器人..."
    pm2 restart ecosystem.config.json
    ;;
  delete)
    echo "删除所有交易机器人进程..."
    pm2 delete ecosystem.config.json
    ;;
  status)
    echo "查看所有交易机器人状态..."
    pm2 list
    ;;
  logs)
    echo "查看实时日志..."
    pm2 logs
    ;;
  start-nfi)
    echo "启动NFI机器人..."
    pm2 start auto_trader_nostalgia_for_infinity.py --name auto-trader
    ;;
  *)
    echo "用法: $0 {start|stop|restart|delete|status|logs|start-nfi}"
    echo ""
    echo "命令说明:"
    echo "  start      - 启动6个新交易机器人"
    echo "  stop       - 停止6个新交易机器人"
    echo "  restart    - 重启6个新交易机器人"
    echo "  delete     - 删除6个新交易机器人进程"
    echo "  status     - 查看所有PM2进程状态"
    echo "  logs       - 查看实时日志"
    echo "  start-nfi  - 启动NFI机器人(如果未运行)"
    echo ""
    echo "现有的7个机器人:"
    echo "  1. auto-trader              - NFI策略(原版)"
    echo "  2. trader-boll-macd         - BOLL+MACD共振"
    echo "  3. trader-rsi-macd          - RSI+MACD双确认"
    echo "  4. trader-vwap              - VWAP突破"
    echo "  5. trader-supertrend        - SuperTrend趋势跟随"
    echo "  6. trader-adx               - ADX趋势强度过滤"
    echo "  7. trader-bb-mean-reversion - 布林带震荡套利"
    ;;
esac
