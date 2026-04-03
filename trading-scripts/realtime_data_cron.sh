#!/bin/bash
# 实时数据更新定时任务
# 每30秒更新一次网站实时数据 + dashboard JSON 导出

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while true; do
    cd "$SCRIPT_DIR" || exit 1

    .venv/bin/python generate_realtime_data.py > /dev/null 2>&1
    .venv/bin/python export-dashboard-data.py > /dev/null 2>&1

    sleep 60
done
