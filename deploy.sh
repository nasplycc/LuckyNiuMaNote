#!/bin/bash
# =============================================================================
# 赛博牛马交易网站 - 一键部署脚本
# 功能: 重新编译网站 + 部署 + 重启机器人
# =============================================================================

set -e  # 遇到错误立即退出

echo "=========================================="
echo "🚀 赛博牛马一键部署启动"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目路径
PROJECT_DIR="/home/ubuntu/LuckyNiuMaNote"
FRONTEND_DIR="$PROJECT_DIR/frontend"
TRADING_DIR="$PROJECT_DIR/trading-scripts"

# 1. 进入项目目录
echo "📁 进入项目目录..."
cd "$PROJECT_DIR"

# 2. 重新编译网站
echo ""
echo "🔨 步骤 1/4: 重新编译网站..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠️  node_modules 不存在，正在安装依赖...${NC}"
    npm install
fi

echo "📝 执行 npm run build..."
npm run build 2>&1 | tail -10

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 网站编译成功${NC}"
else
    echo -e "${RED}❌ 网站编译失败${NC}"
    exit 1
fi

# 3. 重启网站后端
echo ""
echo "🌐 步骤 2/4: 重启网站后端..."
pm2 restart lucky-backend

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 网站后端已重启${NC}"
else
    echo -e "${YELLOW}⚠️  尝试启动新实例...${NC}"
    cd "$PROJECT_DIR"
    pm2 start server.js --name lucky-backend
fi

# 等待服务启动
sleep 2

# 4. 重启交易机器人
echo ""
echo "🤖 步骤 3/4: 重启交易机器人..."

# 重启 NFI 原版
echo "  ↳ 重启 NFI原版..."
pm2 restart auto-trader 2>/dev/null || pm2 start "$TRADING_DIR/run_auto_trader.sh" --name auto-trader

# 重启 BOLL+MACD
echo "  ↳ 重启 BOLL+MACD V3..."
pm2 restart trader-boll-macd 2>/dev/null || pm2 start "$TRADING_DIR/run_trader_01.sh" --name trader-boll-macd

# 重启 SuperTrend
echo "  ↳ 重启 SuperTrend×4.0..."
pm2 restart trader-supertrend 2>/dev/null || pm2 start "$TRADING_DIR/run_trader_04.sh" --name trader-supertrend

# 重启 ADX
echo "  ↳ 重启 ADX趋势过滤..."
pm2 restart trader-adx 2>/dev/null || pm2 start "$TRADING_DIR/run_trader_05.sh" --name trader-adx

echo -e "${GREEN}✅ 所有机器人已重启${NC}"

# 5. 检查实时数据服务
echo ""
echo "📊 步骤 4/4: 检查实时数据服务..."
pm2 list | grep -q "realtime-data" || pm2 start "$TRADING_DIR/realtime_data_cron.sh" --name realtime-data

# 6. 显示状态
echo ""
echo "=========================================="
echo "📋 部署完成 - 服务状态"
echo "=========================================="
pm2 list | grep -E "name|lucky|trader|auto|realtime"

echo ""
echo "=========================================="
echo "🌐 访问地址"
echo "=========================================="
echo "网站: https://luckyniuma.com/"
echo "API:  https://luckyniuma.com/api/position"
echo ""
echo -e "${GREEN}✅ 一键部署完成！${NC}"
echo ""
