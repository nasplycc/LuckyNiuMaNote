#!/usr/bin/env python3
"""
Hyperliquid 资金划转脚本
从 Spot 账户划转到 Perp 账户（或反向）
"""
import sys
import json
from pathlib import Path
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account

def load_config():
    """Load config from .hl_config file"""
    config_path = Path(__file__).parent.parent / "config" / ".hl_config"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    config = {}
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                config[key] = value
    return config

def transfer_spot_to_perp(amount_usd: float):
    """从现货账户划转资金到合约账户"""
    config = load_config()
    main_wallet = config["MAIN_WALLET"]
    api_private_key = config["API_PRIVATE_KEY"]
    
    account = Account.from_key(api_private_key)
    exchange = Exchange(account, constants.MAINNET_API_URL, account_address=main_wallet)
    
    # 划转 USDC 从 spot 到 perp
    # amount 需要乘以 1e6 (USDC 有 6 位小数)
    amount_raw = int(amount_usd * 1e6)
    
    result = exchange.spot_transfer(amount_raw, "USDC", main_wallet)
    return result

def transfer_perp_to_spot(amount_usd: float):
    """从合约账户划转资金到现货账户"""
    config = load_config()
    main_wallet = config["MAIN_WALLET"]
    api_private_key = config["API_PRIVATE_KEY"]
    
    account = Account.from_key(api_private_key)
    exchange = Exchange(account, constants.MAINNET_API_URL, account_address=main_wallet)
    
    # 划转 USDC 从 perp 到 spot (负数表示反向划转)
    amount_raw = int(-amount_usd * 1e6)
    
    result = exchange.spot_transfer(amount_raw, "USDC", main_wallet)
    return result

def get_balances():
    """获取账户余额"""
    import requests
    config = load_config()
    main_wallet = config["MAIN_WALLET"]
    
    url = "https://api.hyperliquid.xyz/info"
    
    # Spot 余额
    spot_resp = requests.post(url, json={
        "type": "spotClearinghouseState",
        "user": main_wallet
    })
    spot_data = spot_resp.json()
    
    # Perp 余额
    perp_resp = requests.post(url, json={
        "type": "clearinghouseState",
        "user": main_wallet
    })
    perp_data = perp_resp.json()
    
    return {
        "spot": spot_data,
        "perp": perp_data
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Hyperliquid 资金划转")
    parser.add_argument("action", choices=["status", "to-perp", "to-spot"], 
                       help="操作: status=查看余额, to-perp=划转到合约, to-spot=划转到现货")
    parser.add_argument("--amount", type=float, default=0, 
                       help="划转金额 (USDC)")
    
    args = parser.parse_args()
    
    if args.action == "status":
        balances = get_balances()
        
        spot_usdc = 0
        for b in balances["spot"].get("balances", []):
            if b["coin"] == "USDC":
                spot_usdc = float(b["total"])
                break
        
        perp_value = float(balances["perp"].get("marginSummary", {}).get("accountValue", 0))
        
        print(f"📊 账户余额")
        print(f"现货账户 (Spot): {spot_usdc:.6f} USDC")
        print(f"合约账户 (Perp): {perp_value:.6f} USDC")
        print(f"总计: {spot_usdc + perp_value:.6f} USDC")
        
    elif args.action == "to-perp":
        if args.amount <= 0:
            print("❌ 请指定划转金额: --amount 50")
            sys.exit(1)
        
        print(f"🔄 划转 {args.amount} USDC 从现货到合约账户...")
        result = transfer_spot_to_perp(args.amount)
        print(f"结果: {json.dumps(result, indent=2)}")
        
    elif args.action == "to-spot":
        if args.amount <= 0:
            print("❌ 请指定划转金额: --amount 50")
            sys.exit(1)
        
        print(f"🔄 划转 {args.amount} USDC 从合约到现货账户...")
        result = transfer_perp_to_spot(args.amount)
        print(f"结果: {json.dumps(result, indent=2)}")
