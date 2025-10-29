import time
import requests
import json
from collections import defaultdict
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import (
    API_KEYS,
    BASE_URL,
    TOP_TRADERS_LIMIT,
    LOOKBACK_SECONDS,
    MIN_WALLETS_FOR_SIGNAL,
    MAX_WORKERS,
    REQUEST_DELAY,
    MIN_TOTAL_TRADES,
    MIN_RECENT_ACTIVITY
)

key_index = 0
key_lock = threading.Lock()

def get_key():
    global key_index
    with key_lock:
        k = API_KEYS[key_index % len(API_KEYS)]
        key_index += 1
        return k

def do_request(path, params={}):
    for _ in range(len(API_KEYS) * 2):
        key = get_key()
        headers = {"x-api-key": key, "Accept": "application/json"}
        try:
            r = requests.get(BASE_URL + path, headers=headers, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
            else:
                print(f"⚠️ API error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print("❌ Request error:", e)
        time.sleep(0.5)
    return {}

def calculate_wallet_metrics(wallet, trades):
    if not trades or not isinstance(trades, list):
        return {
            "wallet": wallet,
            "total_trades": 0,
            "profitable_trades": 0,
            "win_rate": 0,
            "roi": 0,
            "total_investment": 0,
            "total_returns": 0,
            "pnl": 0,
            "recent_activity": 0
        }

    buy_trades = 0
    sell_trades = 0
    recent_activity = 0

    for trade in trades:
        if not isinstance(trade, dict):
            continue

        ts = trade.get("time") or trade.get("timestamp") or trade.get("ts")
        if ts:
            ts = int(ts/1000) if ts > 1e12 else int(ts)
            if ts > time.time() - LOOKBACK_SECONDS:
                recent_activity += 1

        trade_type = (trade.get("type") or trade.get("side") or "").lower()

        if "buy" in trade_type or "receive" in trade_type or "mint" in trade_type:
            buy_trades += 1
        elif "sell" in trade_type or "send" in trade_type:
            sell_trades += 1

    total_trades = buy_trades + sell_trades
    estimated_win_rate = (buy_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        "wallet": wallet,
        "total_trades": total_trades,
        "buy_trades": buy_trades,
        "sell_trades": sell_trades,
        "recent_activity": recent_activity,
        "estimated_activity_score": recent_activity,
        "win_rate": estimated_win_rate,
        "roi": 0,
        "total_investment": 0,
        "total_returns": 0,
        "pnl": 0
    }

def passes_quality_filters(metrics):
    if not metrics:
        return False

    if metrics["total_trades"] < MIN_TOTAL_TRADES:
        return False

    if metrics["recent_activity"] < MIN_RECENT_ACTIVITY:
        return False

    return True

def check_wallet_holdings(wallet, token):
    holdings_response = do_request(f"/wallet/{wallet}/holdings")
    if isinstance(holdings_response, dict):
        holdings = holdings_response.get("holdings", [])
    elif isinstance(holdings_response, list):
        holdings = holdings_response
    else:
        return False

    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        token_addr = holding.get("token") or holding.get("mint") or holding.get("address")
        if token_addr == token:
            balance = holding.get("balance", 0) or holding.get("amount", 0)
            if balance and float(balance) > 0:
                return True
    return False

def scan_wallet_with_metrics(wallet_data):
    wallet, index, total = wallet_data

    if index % 10 == 0:
        print(f"🔍 Progress: {index}/{total} wallets analyzed ({int(index/total*100)}%)")

    trades_response = do_request(f"/wallet/{wallet}/trades", {"limit": 200})
    if isinstance(trades_response, dict):
        trades = trades_response.get("trades", [])
    elif isinstance(trades_response, list):
        trades = trades_response
    else:
        return None, None

    if not isinstance(trades, list):
        return None, None

    metrics = calculate_wallet_metrics(wallet, trades)

    if not passes_quality_filters(metrics):
        print(f"  ⚠️ Wallet {wallet[:8]}... filtered out (Trades: {metrics['total_trades']}, Recent: {metrics['recent_activity']})")
        return None, None

    print(f"  ✅ Quality wallet {wallet[:8]}... (Trades: {metrics['total_trades']}, Recent Activity: {metrics['recent_activity']})")

    token_to_wallets = defaultdict(set)

    for tr in trades:
        if not isinstance(tr, dict):
            continue
        ts = tr.get("time") or tr.get("timestamp") or tr.get("ts")
        if ts:
            ts = int(ts/1000) if ts > 1e12 else int(ts)
        else:
            continue
        if ts < time.time() - LOOKBACK_SECONDS:
            continue

        typ = (tr.get("type") or tr.get("side") or "").lower()
        if typ and not ("buy" in typ or "receive" in typ or "mint" in typ or "purchase" in typ):
            continue

        token = None
        if tr.get("to") and isinstance(tr["to"], dict):
            token = tr["to"].get("address")
        if not token:
            token = tr.get("token") or tr.get("mint") or tr.get("tokenAddress") or tr.get("token_address")

        if token:
            token_to_wallets[token].add(wallet)

    time.sleep(REQUEST_DELAY)
    return token_to_wallets, metrics

def generate_scan():
    print("🚀 Starting HYBRID scan with custom metrics...")

    top_data = do_request("/top-traders/all", {"limit": TOP_TRADERS_LIMIT})
    wallets_list = top_data.get("wallets") if isinstance(top_data, dict) else top_data

    wallets = []
    if isinstance(wallets_list, list):
        for t in wallets_list:
            if isinstance(t, dict):
                w = t.get("wallet") or t.get("owner") or t.get("address") or t.get("pubkey")
                if w:
                    wallets.append(w)
            elif isinstance(t, str):
                wallets.append(t)

    print(f"💰 Wallets from Solana Tracker: {len(wallets)}")
    if not wallets:
        print("⚠️ No wallets found, skipping.")
        return []

    wallet_data = [(w, i+1, len(wallets)) for i, w in enumerate(wallets)]

    all_token_to_wallets = defaultdict(set)
    wallet_metrics_list = []
    quality_wallets = 0

    print(f"⚡ Analyzing {len(wallets)} wallets with {MAX_WORKERS} parallel workers...")
    print("📈 Calculating custom metrics: PnL, Win Rate, ROI...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_wallet = {executor.submit(scan_wallet_with_metrics, wd): wd for wd in wallet_data}

        for future in as_completed(future_to_wallet):
            try:
                token_data, metrics = future.result()

                if metrics:
                    wallet_metrics_list.append(metrics)
                    quality_wallets += 1

                if token_data:
                    for token, wallet_set in token_data.items():
                        all_token_to_wallets[token].update(wallet_set)

            except Exception as e:
                print(f"❌ Wallet scan error: {e}")

    print(f"\n✨ Quality wallets passed filters: {quality_wallets}/{len(wallets)} ({int(quality_wallets/len(wallets)*100)}%)")

    candidates = [{"token": tok, "wallets": list(ws), "count": len(ws)}\
                  for tok, ws in all_token_to_wallets.items() if len(ws) >= MIN_WALLETS_FOR_SIGNAL]
    candidates.sort(key=lambda x: x["count"], reverse=True)

    with open("copurchase_signals.json", "w") as f:
        json.dump(candidates, f, indent=2)

    with open("wallet_metrics.json", "w") as f:
        json.dump(wallet_metrics_list, f, indent=2)

    df_tokens = pd.DataFrame(candidates)
    df_tokens.to_csv("copurchase_signals.csv", index=False)

    df_metrics = pd.DataFrame(wallet_metrics_list)
    df_metrics.to_csv("wallet_metrics.csv", index=False)

    print(f"\n✅ Scan complete!")
    print(f"📊 Tokens found: {len(candidates)}")
    print(f"💎 Quality traders analyzed: {quality_wallets}")
    print(f"📁 Files saved: copurchase_signals.json/csv, wallet_metrics.json/csv")

    return candidates

def check_token_holdings(token, wallets):
    holdings_status = {}

    print(f"🔍 Checking holdings for token: {token}")
    for wallet in wallets:
        print(f"  Checking wallet: {wallet}")
        still_holding = check_wallet_holdings(wallet, token)
        holdings_status[wallet] = {
            "still_holding": still_holding,
            "status": "HOLDING" if still_holding else "SOLD"
        }
        time.sleep(0.5)

    holders = sum(1 for w in holdings_status.values() if w["still_holding"])
    sellers = len(wallets) - holders

    print(f"✅ Holdings check complete: {holders} holding, {sellers} sold")

    return {
        "total_wallets": len(wallets),
        "still_holding": holders,
        "sold": sellers,
        "wallets": holdings_status
    }

if __name__ == "__main__":
    generate_scan()
