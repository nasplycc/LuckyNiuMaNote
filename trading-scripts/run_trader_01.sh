#!/bin/bash
cd /home/ubuntu/LuckyNiuMaNote/trading-scripts
source .venv/bin/activate
exec python scripts/trader_01_boll_macd.py
