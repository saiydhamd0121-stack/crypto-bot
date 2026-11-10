import os
import time
import json
import urllib.parse
import threading
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# ==========================================
# 1. إعدادات الحساب والقنوات المباشرة
# ==========================================
TELEGRAM_BOT_TOKEN = "8730034376:AAHnBrqKjyuICdw69mHbszrbi0MFyMcNVGo"
PUBLIC_PROMO_CHANNEL = "-1003991149946"
VIP_CHANNEL_ID = "-1003991149946"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "SUIUSDT", "AVAXUSDT"
]

BINANCE_URLS = [
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api3.binance.com"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ==========================================
# 2. محرك الاتصال وتوليد الشارتات
# ==========================================
def fetch_binance(endpoint):
    for base in BINANCE_URLS:
        try:
            url = f"{base}{endpoint}"
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None

def send_telegram_photo(chat_id, photo_url, caption):
    """تحميل الشارت خفيف الحجم وإرساله كملف لمنع أخطاء الروابط الطويلة"""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False, "Token or Chat ID missing"
    try:
        img_resp = requests.get(photo_url, timeout=10)
        if img_resp.status_code != 200:
            return False, f"Image download failed: HTTP {img_resp.status_code}"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {
            'photo': ('chart.png', img_resp.content, 'image/png')
        }
        data = {
            'chat_id': chat_id,
            'caption': caption
        }
        r = requests.post(url, data=data, files=files, timeout=15)
        res_json = r.json()
        if res_json.get("ok"):
            return True, "Success"
        return False, res_json.get("description", "Telegram Error")
    except Exception as e:
        return False, str(e)

def get_klines_data(symbol, interval="15m", limit=20):
    res = fetch_binance(f"/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")
    return res if isinstance(res, list) else None

def generate_chart_url(symbol, klines, wall_price=None):
    try:
        labels = [time.strftime('%H:%M', time.gmtime(k[0] / 1000)) for k in klines]
        prices = [float(k[4]) for k in klines]

        datasets = [
            {
                "label": f"{symbol} Price Flow",
                "data": prices,
                "borderColor": "#00E676",
                "backgroundColor": "rgba(0, 230, 118, 0.08)",
                "fill": True,
                "borderWidth": 2,
                "pointRadius": 0
            }
        ]

        if wall_price:
            datasets.append({
                "label": "Whale Wall",
                "data": [wall_price] * len(prices),
                "borderColor": "#FF1744",
                "borderDash": [5, 5],
                "borderWidth": 1.5,
                "fill": False,
                "pointRadius": 0
            })

        chart_config = {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "title": {"display": True, "text": f"Whale Radar Terminal | {symbol}", "fontColor": "#ffffff"},
                "legend": {"labels": {"fontColor": "#b0bec5"}},
                "scales": {
                    "xAxes": [{"ticks": {"fontColor": "#78909c"}}],
                    "yAxes": [{"position": "right", "ticks": {"fontColor": "#78909c"}}]
                }
            }
        }
        encoded = urllib.parse.quote(json.dumps(chart_config))
        return f"https://quickchart.io/chart?c={encoded}&w=650&h=320&bkg=%230e1621"
    except Exception:
        return "https://placehold.co/600x300/0e1621/ffffff?text=Chart+Active"

# ==========================================
# 3. التحليل الكمي للسيولة المؤسسية
# ==========================================
def analyze_institutional_depth(symbol):
    try:
        res = fetch_binance(f"/api/v3/depth?symbol={symbol}&limit=50")
        if not res:
            return 50.0, 0.0, 0.0, (0.0, 0.0), (0.0, 0.0)

        bids = res.get("bids", [])
        asks = res.get("asks", [])

        bids_usd = sum(float(b[0]) * float(b[1]) for b in bids)
        asks_usd = sum(float(a[0]) * float(a[1]) for a in asks)
        total_usd = bids_usd + asks_usd

        if total_usd == 0:
            return 50.0, 0.0, 0.0, (0.0, 0.0), (0.0, 0.0)

        bid_ratio = (bids_usd / total_usd) * 100
        top_bid_wall = max((float(b[0]) * float(b[1]), float(b[0])) for b in bids) if bids else (0.0, 0.0)
        top_ask_wall = max((float(a[0]) * float(a[1]), float(a[0])) for a in asks) if asks else (0.0, 0.0)

        return bid_ratio, bids_usd, asks_usd, top_bid_wall, top_ask_wall
    except Exception:
        return 50.0, 0.0, 0.0, (0.0, 0.0), (0.0, 0.0)

def track_order_flow(symbol):
    try:
        trades = fetch_binance(f"/api/v3/trades?symbol={symbol}&limit=100")
        if not trades or not isinstance(trades, list):
            return None

        buy_vol = 0.0
        sell_vol = 0.0
        institutional_orders = 0
        largest_trade = 0.0
        last_price = float(trades[-1]['price'])

        is_major = symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        whale_cut = 100000 if is_major else 40000

        for t in trades:
            price = float(t['price'])
            qty = float(t['qty'])
            usd_val = price * qty

            if usd_val > largest_trade:
                largest_trade = usd_val

            if t.get('isBuyerMaker', False):
                sell_vol += usd_val
            else:
                buy_vol += usd_val

            if usd_val >= whale_cut:
                institutional_orders += 1

        return {
            "symbol": symbol,
            "price": last_price,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
            "delta": buy_vol - sell_vol,
            "inst_orders": institutional_orders,
            "largest_trade": largest_trade
        }
    except Exception:
        return None

# ==========================================
# 4. الرصد الآلي المستمر
# ==========================================
def market_scanner_loop():
    time.sleep(15)
    while True:
        try:
            for sym in SYMBOLS:
                bid_ratio, bids_usd, asks_usd, top_bid, top_ask = analyze_institutional_depth(sym)
                flow = track_order_flow(sym)

                if not flow:
                    continue

                heavy_depth = (bids_usd + asks_usd) >= 500000
                extreme_obi = (bid_ratio >= 75.0 or bid_ratio <= 25.0) and heavy_depth
                strong_flow = abs(flow["delta"]) >= 75000 and flow["inst_orders"] >= 1

                if extreme_obi or strong_flow:
                    klines = get_klines_data(sym)
                    if not klines:
                        continue

                    is_bullish = bid_ratio >= 50
                    active_wall_price = top_bid[1] if is_bullish else top_ask[1]
                    active_wall_size = top_bid[0] if is_bullish else top_ask[0]
                    chart_url = generate_chart_url(sym, klines, active_wall_price)

                    price_fmt = f"{flow['price']:.8f}" if flow['price'] < 0.01 else f"{flow['price']:,.2f}"
                    bias = "تجميع مؤسسي (Bullish)" if is_bullish else "تفريغ وجدار بيع (Bearish)"

                    caption = (
                        f"🐋 Whale Radar Terminal | تحليل السيولة المؤسسية\n\n"
                        f"الأصل: #{flow['symbol']} | السعر: ${price_fmt}\n"
                        f"الاتجاه الكمي: {bias}\n\n"
                        f"▫️ نسبة اختلال الدفتر (OBI): {bid_ratio:.1f}%\n"
                        f"▫️ جدار السيولة النشط: ${active_wall_size:,.0f} عند ${active_wall_price}\n"
                        f"▫️ صافي دلتا الفوليوم: ${flow['delta']:,.0f}\n"
                        f"▫️ صفقات الحيتان: {flow['inst_orders']}\n\n"
                        f"🎓 التحليل التعليمي: اختبار مباشر لمستويات الجدار مع امتصاص للسيولة المقابلة."
                    )
                    send_telegram_photo(VIP_CHANNEL_ID, chart_url, caption)
                    if PUBLIC_PROMO_CHANNEL != VIP_CHANNEL_ID:
                        send_telegram_photo(PUBLIC_PROMO_CHANNEL, chart_url, caption)

                time.sleep(2)
        except Exception:
            pass
        time.sleep(25)

# ==========================================
# 5. نقاط الفحص السحابي (Endpoints)
# ==========================================
@app.route('/')
def home():
    return jsonify({
        "engine": "Whale Radar Pro Visual Terminal v3.0",
        "status": "online"
    })

@app.route('/trigger-hourly')
def trigger_manual():
    sample_sym = "SOLUSDT"
    flow = track_order_flow(sample_sym)
    bid_ratio, bids_usd, asks_usd, top_bid, top_ask = analyze_institutional_depth(sample_sym)
    klines = get_klines_data(sample_sym)

    if flow and klines:
        chart_url = generate_chart_url(sample_sym, klines, top_bid[1])
        test_caption = (
            f"📡 Whale Radar Pro | تقرير السيولة المصور (فحص حي)\n\n"
            f"الأصل: #{sample_sym} | السعر: ${flow['price']:,.2f}\n"
            f"جدار الشراء المرصود: ${top_bid[0]:,.0f} عند سعر ${top_bid[1]:,.2f}\n"
            f"صافي دلتا الفوليوم: ${flow['delta']:,.0f}\n\n"
            f"الخط المتقطع على الشارت يوضح تمركز سيولة الحوت الحالية."
        )
        ok, reason = send_telegram_photo(PUBLIC_PROMO_CHANNEL, chart_url, test_caption)
        return jsonify({
            "status": "success",
            "photo_sent": ok,
            "detail": reason,
            "chart_url": chart_url
        })
    return jsonify({"status": "error", "message": "Failed to fetch market data"}), 500

scanner_thread = threading.Thread(target=market_scanner_loop, daemon=True)
scanner_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
