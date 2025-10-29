# API Configuration
API_KEYS = [
    "c89d3b53-74e2-42ac-8c0c-8b4f393d60bb",
    "e6d255f4-d3ce-457f-b149-883b2f3e93e2"
]

BASE_URL = "https://data.solanatracker.io"

# Solana Tracker Settings
TOP_TRADERS_LIMIT = 3000

# Time Window
LOOKBACK_SECONDS = 6 * 60 * 60  # 6 hours

# Token Signal Settings
MIN_WALLETS_FOR_SIGNAL = 2  # Minimum wallets buying same token

# Performance Settings
MAX_WORKERS = 1  # Parallel workers (reduce to 1-2 if rate limiting)
REQUEST_DELAY = 1  # Seconds between requests

# Quality Filters (ACTUALLY USED)
MIN_TOTAL_TRADES = 1  # Minimum trades in wallet history
MIN_RECENT_ACTIVITY = 1  # Minimum trades in last 6 hours

# Legacy/Unused (kept for future when PnL data available)
MIN_WIN_RATE = 0.0
MIN_PROFITABLE_TRADES = 1
MIN_ROI = -100.0
