#!/bin/bash
# 实时数据更新定时任务
# 每30秒更新一次网站实时数据

SCRIPT_DIR="/home/ubuntu/LuckyNiuMaNote/trading-scripts"

while true; do
    cd "$SCRIPT_DIR" && .venv/bin/python generate_realtime_data.py > /dev/null 2>&1
    sleep 30
done
