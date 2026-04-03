#!/usr/bin/env python3
"""
生成网站实时数据
包含：持仓、机器人状态、最新价格
"""

import json
import os
from datetime import datetime
from pathlib import Path
import requests

# Hyperliquid API
HL_API = "https://api.hyperliquid.xyz/info"


def read_hl_config():
    path = Path(__file__).parent / "config" / ".hl_config"
    if not path.exists():
        return {}
    data = {}
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            data[k.strip()] = v.strip()
    except Exception:
        return {}
    return data


def resolve_wallet():
    env_wallet = os.getenv("LUCKYNIUMA_WALLET")
    if env_wallet:
        return env_wallet
    hl_cfg = read_hl_config()
    if hl_cfg.get("MAIN_WALLET"):
        return hl_cfg["MAIN_WALLET"]
    return "0xfFd91a584cf6419b92E58245898D2A9281c628eb"

def hl_request(body):
    try:
        resp = requests.post(HL_API, json=body, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"API Error: {e}")
        return {}

def get_prices():
    """获取最新价格"""
    mids = hl_request({"type": "allMids"})
    return {
        "BTC": float(mids.get("BTC", 0)),
        "ETH": float(mids.get("ETH", 0))
    }

def get_account_state(wallet):
    """获取账户状态"""
    try:
        state = hl_request({
            "type": "clearinghouseState",
            "user": wallet
        })
        
        if not state:
            return None
            
        account_value = float(state.get("marginSummary", {}).get("accountValue", 0))
        
        positions = []
        for pos in state.get("assetPositions", []):
            p = pos.get("position", {})
            positions.append({
                "coin": p.get("coin"),
                "size": float(p.get("szi", 0)),
                "entry_price": float(p.get("entryPx", 0)),
                "mark_price": float(p.get("markPx", 0)),
                "unrealized_pnl": float(p.get("unrealizedPnl", 0)),
                "liquidation_price": float(p.get("liquidationPx", 0)) if p.get("liquidationPx") else None
            })
        
        return {
            "account_value": account_value,
            "positions": positions
        }
    except Exception as e:
        print(f"获取账户状态失败: {e}")
        return None

def get_robot_states():
    """获取机器人状态（从日志文件）"""
    log_dir = Path(__file__).parent.parent / "logs"
    robots = []
    
    robot_configs = [
        {"name": "NFI原版", "log": "trader_nfi.log", "id": "nfi"},
        {"name": "BOLL+MACD V3", "log": "trader_01_boll_macd.log", "id": "boll_macd"},
        {"name": "SuperTrend×4.0", "log": "trader_04_supertrend.log", "id": "supertrend"},
        {"name": "ADX趋势过滤", "log": "trader_05_adx.log", "id": "adx"},
    ]
    
    for cfg in robot_configs:
        log_path = log_dir / cfg["log"]
        status = "offline"
        last_log = ""
        
        if log_path.exists():
            try:
                # 检查文件修改时间
                mtime = log_path.stat().st_mtime
                from time import time
                if time() - mtime < 300:  # 5分钟内有更新
                    status = "running"
                
                # 读取最后几行日志
                with open(log_path, 'r') as f:
                    lines = f.readlines()
                    last_log = lines[-1].strip() if lines else ""
            except:
                pass
        
        robots.append({
            "id": cfg["id"],
            "name": cfg["name"],
            "status": status,
            "last_log": last_log[-100:]  # 最后100字符
        })
    
    return robots

def generate_data():
    """生成网站数据"""
    
    # 钱包地址
    wallet = resolve_wallet()
    
    # 获取数据
    prices = get_prices()
    account = get_account_state(wallet)
    robots = get_robot_states()
    
    # 构建数据
    data = {
        "timestamp": datetime.now().isoformat(),
        "prices": prices,
        "account": account,
        "robots": robots,
        "STATS": {
            "balance": account["account_value"] if account else 98,
            "earnings": 0,
            "returnPct": 0,
            "trades": 0
        },
        "SITE_CONFIG": {
            "name": "赛博牛马交易日记",
            "tagline": "AI Trading Journal",
            "description": "赛博牛马的加密货币交易实验 — 4个AI策略机器人实盘交易",
            "url": "https://luckyniuma.com",
            "twitter": "",
            "logo": "/logo.png",
            "logo256": "/logo_256.png",
        },
        "VERIFICATION": {
            "tradingAccount": wallet,
            "depositChain": "Arbitrum",
            "depositToken": "USDC",
        }
    }
    
    # 写入文件
    output_path = Path(__file__).parent.parent / "frontend" / "dist" / "realtime-data.json"
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"[{datetime.now()}] 实时数据已更新")
    print(f"  BTC: ${prices['BTC']}")
    print(f"  ETH: ${prices['ETH']}")
    if account:
        print(f"  账户价值: ${account['account_value']:.2f}")
        print(f"  持仓数量: {len(account['positions'])}")
    print(f"  机器人状态: {len([r for r in robots if r['status'] == 'running'])}/{len(robots)} 运行中")

if __name__ == "__main__":
    generate_data()
