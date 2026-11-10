import os
import time
import json
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = "8730034376:AAHnBrqKjyuICdw69mHbszrbi0MFyMcNVGo"
PUBLIC_PROMO_CHANNEL = "-1003991149946"
VIP_CHANNEL_ID = "-1003991149946"


SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "SUIUSDT", "AVAXUSDT"
]

# نطاقات بينانس المفتوحة للسيرفرات السحابية مع هيدر متصفح لمنع الحظر
BINANCE_URLS = [
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api3.binance.com"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_binance(endpoint):
    """محاولة جلب البيانات عبر النطاقات المتاحة لتفادي حظر السيرفرات"""
    for base in BINANCE_URLS:
        try:
            url = f"{base}{endpoint}"
            r = requests.get(url, headers=HEADERS, timeout=4)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None

def send_telegram_msg(chat_id, text):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=8)
        return r.json().get("ok", False)
    except Exception:
        return False

def analyze_order_book(symbol):
    try:
        res = fetch_binance(f"/api/v3/depth?symbol={symbol}&limit=50")
        if not res:
            return 50.0, 0, 0
        bids = sum(float(b[1]) for b in res.get("bids", []))
        asks = sum(float(a[1]) for a in res.get("asks", []))
        total = bids + asks
        if total == 0:
            return 50.0, bids, asks
        return (bids / total) * 100, bids, asks
    except Exception:
        return 50.0, 0, 0

def check_whale_trades(symbol):
    try:
        trades = fetch_binance(f"/api/v3/trades?symbol={symbol}&limit=60")
        if not trades or not isinstance(trades, list):
            return None
        
        buy_vol = 0.0
        sell_vol = 0.0
        huge_trades_count = 0
        last_price = 0.0

        is_alt = symbol in ["PEPEUSDT", "SHIBUSDT", "DOGEUSDT", "SUIUSDT"]
        threshold = 20000 if is_alt else 50000

        for t in trades:
            price = float(t['price'])
            qty = float(t['qty'])
            usd_val = price * qty
            last_price = price

            if t.get('isBuyerMaker', False):
                sell_vol += usd_val
            else:
                buy_vol += usd_val

            if usd_val >= threshold:
                huge_trades_count += 1

        return {
            "symbol": symbol,
            "price": last_price,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
            "delta": buy_vol - sell_vol,
            "huge_trades": huge_trades_count
        }
    except Exception:
        return None

def market_scanner_loop():
    time.sleep(10)
    while True:
        try:
            for sym in SYMBOLS:
                bid_ratio, _, _ = analyze_order_book(sym)
                data = check_whale_trades(sym)

                if data and (bid_ratio >= 67.0 or bid_ratio <= 33.0 or data["huge_trades"] >= 2):
                    direction = "🟢 تراكم طلبات شراء مؤسسية (Bullish)" if bid_ratio >= 50 else "🔴 ضغط بيع وتفريغ جداري (Bearish)"
                    price_format = f"{data['price']:.8f}" if data['price'] < 0.01 else f"{data['price']:,.2f}"

                    alert_msg = (
                        f"🚨 *WHALE RADAR | تسارع سيولة استثنائي*\n\n"
                        f"🔹 *الأصل:* `#{data['symbol']}`\n"
                        f"🔹 *السعر اللحظي:* `${price_format}`\n"
                        f"🔹 *الاتجاه الكمي:* {direction}\n\n"
                        f"📊 *بيانات دفتر الطلبات (Top 50 Depth):*\n"
                        f"▫️ نسبة عروض الشراء: `{bid_ratio:.1f}%`\n"
                        f"▫️ صافي دلتا الفوليوم: `${data['delta']:,.0f}`\n"
                        f"▫️ صفقات الحيتان الخاطفة: `{data['huge_trades']}`\n"
                    )
                    send_telegram_msg(VIP_CHANNEL_ID, alert_msg)
                    if PUBLIC_PROMO_CHANNEL != VIP_CHANNEL_ID:
                        public_msg = (
                            f"⚡️ *رادار السيولة رصد حركة حوت على {data['symbol']}!*\n"
                            f"▫️ السعر: `${price_format}`\n"
                            f"▫️ صافي دلتا الفوليوم: `${data['delta']:,.0f}`\n\n"
                            f"👉 التفاصيل الكاملة متوفرة داخل قناة VIP."
                        )
                        send_telegram_msg(PUBLIC_PROMO_CHANNEL, public_msg)

                time.sleep(2)
        except Exception:
            pass
        time.sleep(25)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "version": "Whale Radar Pro v3.0 Multi-Asset",
        "monitored_assets": SYMBOLS
    })

@app.route('/trigger-hourly')
def trigger_manual():
    sample_data = check_whale_trades("BTCUSDT")
    bid_ratio, _, _ = analyze_order_book("BTCUSDT")
    if sample_data:
        test_msg = (
            f"📡 *فحص النبض الساعي | تقرير السيولة المؤسسي*\n\n"
            f"▫️ الأصل: `BTCUSDT`\n"
            f"▫️ السعر اللحظي: `${sample_data['price']:,.2f}`\n"
            f"▫️ نسبة هيمنة الشراء في الدفتر: `{bid_ratio:.1f}%`\n"
            f"▫️ صافي تدفق الفوليوم (Delta): `${sample_data['delta']:,.0f}`\n\n"
            f"✅ محرك البيانات تجاوز جدار الحماية بنجاح ويعمل 100%."
        )
        res = send_telegram_msg(PUBLIC_PROMO_CHANNEL, test_msg)
        return jsonify({
            "status": "success",
            "message": "Data fetched and alert dispatched",
            "telegram_sent": res,
            "btc_price": sample_data['price']
        })
    return jsonify({"status": "error", "message": "Failed to fetch from all endpoints"}), 500

scanner_thread = threading.Thread(target=market_scanner_loop, daemon=True)
scanner_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
