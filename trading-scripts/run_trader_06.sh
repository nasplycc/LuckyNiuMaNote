#!/bin/bash
cd /home/ubuntu/LuckyNiuMaNote/trading-scripts
source .venv/bin/activate
exec python scripts/trader_06_bb_mean_reversion.py
