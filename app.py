from flask import Flask, render_template, jsonify, redirect, url_for
import json
import os
from datetime import datetime
from scanner import generate_scan, check_token_holdings

app = Flask(__name__)

@app.route("/")
def home():
    results = {}
    last_scan = "Never"
    wallet_metrics = []

    if os.path.exists("copurchase_signals.json"):
        try:
            with open("copurchase_signals.json", "r") as f:
                data = json.load(f)
            for entry in data:
                token = entry.get("token")
                wallets = entry.get("wallets", [])
                results[token] = {
                    "wallet_count": len(wallets),
                    "wallets": wallets
                }
            last_scan = datetime.fromtimestamp(os.path.getmtime("copurchase_signals.json")).strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
    
    if os.path.exists("wallet_metrics.json"):
        try:
            with open("wallet_metrics.json", "r") as f:
                wallet_metrics = json.load(f)
        except:
            pass

    return render_template("index.html", results=results, last_scan=last_scan, wallet_metrics=wallet_metrics)

@app.route("/scan")
def scan():
    data = generate_scan()
    return redirect(url_for('home'))

@app.route("/api/scan")
def api_scan():
    data = generate_scan()
    return jsonify({"status": "success", "tokens_found": len(data), "data": data})

@app.route("/api/metrics")
def api_metrics():
    if not os.path.exists("wallet_metrics.json"):
        return jsonify({"error": "No metrics data found"}), 404
    
    with open("wallet_metrics.json", "r") as f:
        metrics = json.load(f)
    
    return jsonify({"status": "success", "wallet_count": len(metrics), "metrics": metrics})

@app.route("/check_holdings/<token>")
def check_holdings(token):
    if not os.path.exists("copurchase_signals.json"):
        return jsonify({"error": "No scan data found"}), 404

    with open("copurchase_signals.json", "r") as f:
        data = json.load(f)

    token_data = None
    for entry in data:
        if entry.get("token") == token:
            token_data = entry
            break

    if not token_data:
        return jsonify({"error": "Token not found"}), 404

    wallets = token_data.get("wallets", [])
    result = check_token_holdings(token, wallets)
    result["token"] = token

    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
