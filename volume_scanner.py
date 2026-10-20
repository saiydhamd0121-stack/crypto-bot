
import time
import requests
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


# ================= TELEGRAM & CHANNEL CONFIG =================
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

VIP_CHANNEL_ID = "@YOUR_VIP_CHANNEL"
FREE_CHANNEL_ID = "@YOUR_FREE_CHANNEL"

# Payment and Contact Credentials
BINANCE_PAY_ID = "1284168199"
ADMIN_CONTACT = "https://instagram.com/python.automation1"

# Engine Parameters
INTERVAL = "15m"
LOOKBACK = 20
VOLUME_SPIKE_MULT = 2.5
RSI_PERIOD = 14
SLEEP_TIME = 60

VIP_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", 
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", 
    "NEARUSDT", "SUIUSDT", "LINKUSDT", "APTUSDT"
]
FREE_SYMBOLS = ["BTCUSDT", "ETHUSDT"]

alerted_candles = {}

def send_telegram(chat_id: str, msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[!] Send error: {e}", flush=True)
        return False

def get_klines(symbol: str, interval: str, limit: int = 70):
    url = "https://api.binance.com/api/v3/klines"
    try:
        res = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"[!] Fetch error {symbol}: {e}", flush=True)
    return None

def get_orderbook_pressure(symbol: str):
    url = "https://api.binance.com/api/v3/depth"
    try:
        res = requests.get(url, params={"symbol": symbol, "limit": 50}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            bids_vol = sum(float(b[1]) for b in data.get("bids", []))
            asks_vol = sum(float(a[1]) for a in data.get("asks", []))
            total = bids_vol + asks_vol
            if total > 0:
                return (bids_vol / total) * 100
    except:
        pass
    return 50.0

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0.0)
        losses.append(abs(diff) if diff < 0 else 0.0)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

def calculate_atr(klines, period=14):
    if len(klines) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(klines)):
        h = float(klines[i][2])
        l = float(klines[i][3])
        prev_c = float(klines[i - 1][4])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return sum(trs[-period:]) / period if trs else 0.0

def process_symbol(symbol: str):
    klines = get_klines(symbol, INTERVAL, limit=60)
    if not klines or len(klines) < 40:
        return

    current = klines[-1]
    prevs = klines[-(LOOKBACK + 1):-1]
    
    current_time = current[0]
    close_price = float(current[4])
    current_vol = float(current[5])

    avg_vol = sum(float(c[5]) for c in prevs) / len(prevs) if prevs else 1
    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

    closes = [float(k[4]) for k in klines]
    rsi = calculate_rsi(closes, RSI_PERIOD)
    if rsi is None:
        return

    bid_ratio = get_orderbook_pressure(symbol)
    atr = calculate_atr(klines, 14)
    if atr == 0:
        atr = close_price * 0.01

    bullish_setup = (vol_ratio >= VOLUME_SPIKE_MULT) and (rsi <= 35) and (bid_ratio >= 55.0)
    bearish_setup = (vol_ratio >= VOLUME_SPIKE_MULT) and (rsi >= 65) and (bid_ratio <= 45.0)

    if bullish_setup or bearish_setup:
        last_alert = alerted_candles.get(symbol)
        if last_alert != current_time:
            
            if bullish_setup:
                signal_side = "BUY / LONG"
                sl = close_price - (atr * 1.5)
                tp1 = close_price + (atr * 1.5)
                tp2 = close_price + (atr * 3.0)
                sentiment = f"Bids Dominance ({bid_ratio:.1f}%)"
            else:
                signal_side = "SELL / SHORT"
                sl = close_price + (atr * 1.5)
                tp1 = close_price - (atr * 1.5)
                tp2 = close_price - (atr * 3.0)
                sentiment = f"Asks Dominance ({100 - bid_ratio:.1f}%)"

            # 1. VIP Full Signal
            vip_report = (
                f"💎 <b>[VIP ALPHA SIGNAL] High Probability Setup</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Pair:</b> #{symbol} | ⏱ <b>Timeframe:</b> {INTERVAL}\n"
                f"🎯 <b>Action:</b> {signal_side}\n"
                f"💵 <b>Entry Price:</b> ${close_price:,.4f}\n\n"
                f"🛡 <b>Stop Loss (SL):</b> ${sl:,.4f}\n"
                f"🎯 <b>Take Profit 1 (TP1):</b> ${tp1:,.4f}\n"
                f"🚀 <b>Take Profit 2 (TP2):</b> ${tp2:,.4f}\n\n"
                f"📊 <b>Market Intelligence:</b>\n"
                f"• Volume Spike: <b>{vol_ratio:.2f}x</b> | RSI: <b>{rsi:.1f}</b>\n"
                f"• Depth Pressure: <b>{sentiment}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👑 <i>VIP Channel Active. Trade with proper risk management.</i>"
            )

            # 2. Free Channel Signal (Hidden targets with CTA)
            free_report = (
                f"🎁 <b>[FREE TRIAL ALERT - 3 DAYS]</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Pair:</b> #{symbol} | ⏱ <b>Timeframe:</b> {INTERVAL}\n"
                f"🎯 <b>Detected Action:</b> {signal_side}\n"
                f"⚡️ <b>Unusual Activity:</b> Volume Spike {vol_ratio:.2f}x\n\n"
                f"🔒 <b>Exact Entry:</b> [LOCKED FOR VIP]\n"
                f"🔒 <b>Stop Loss (SL):</b> [LOCKED FOR VIP]\n"
                f"🔒 <b>Targets (TP1 & TP2):</b> [LOCKED FOR VIP]\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 <b>Unlock full signals & all crypto pairs:</b>\n"
                f"💳 Instant Binance Pay ID:\n"
                f"👉 <code>{BINANCE_PAY_ID}</code>\n\n"
                f"📩 <b>Send payment proof via Instagram:</b>\n"
                f"{ADMIN_CONTACT}"
            )

            print(f"[+] Signal triggered for {symbol}...", flush=True)

            send_telegram(VIP_CHANNEL_ID, vip_report)

            if symbol in FREE_SYMBOLS:
                send_telegram(FREE_CHANNEL_ID, free_report)

            alerted_candles[symbol] = current_time
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running 24/7!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

def main():

    print("=" * 55, flush=True)
    print("🚀 Whale Intelligence Commercial Engine Online...", flush=True)
    print(f"💼 Binance Pay ID: {BINANCE_PAY_ID}")
    print(f"📸 Instagram: {ADMIN_CONTACT}")
    print(f"📊 VIP Assets: {len(VIP_WATCHLIST)} | Free Assets: {len(FREE_SYMBOLS)}")
    print("=" * 55, flush=True)

    while True:
        for symbol in VIP_WATCHLIST:
            process_symbol(symbol)
            time.sleep(0.3)
        time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    main()


