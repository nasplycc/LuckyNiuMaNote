#!/bin/bash
cd /home/ubuntu/LuckyNiuMaNote/trading-scripts
source .venv/bin/activate
exec python scripts/trader_02_rsi_macd.py
