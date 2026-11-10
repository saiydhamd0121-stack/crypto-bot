import os
import time
import json
import urllib.parse
import threading
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# ==============================================================================
# 1. إعدادات المنظومة وهوية القنوات
# ==============================================================================
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

# ==============================================================================
# 2. محرك الاتصال وتوليد الشارتات السحابية
# ==============================================================================
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
    """إرسال بطاقة التحليل الفني مع الصورة بصيغة بيانات ثنائية لتفادي أخطاء الروابط"""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False, "Token or Chat ID missing"
    try:
        img_resp = requests.get(photo_url, timeout=12)
        if img_resp.status_code != 200:
            return False, f"Image fetch failed: HTTP {img_resp.status_code}"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {
            'photo': ('terminal_chart.png', img_resp.content, 'image/png')
        }
        data = {
            'chat_id': chat_id,
            'caption': caption
        }
        r = requests.post(url, data=data, files=files, timeout=15)
        res_json = r.json()
        if res_json.get("ok"):
            return True, "Success"
        return False, res_json.get("description", "Telegram API Error")
    except Exception as e:
        return False, str(e)

def get_klines_data(symbol, interval="15m", limit=24):
    res = fetch_binance(f"/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")
    return res if isinstance(res, list) else None

def generate_chart_url(symbol, klines, wall_price, tp_price):
    """توليد رسم بياني احترافي يوضح مسار السعر، جدار الحوت، ومستهدف السيولة"""
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
                "borderWidth": 2.2,
                "pointRadius": 0
            },
            {
                "label": "Liquidity Wall (Defense)",
                "data": [wall_price] * len(prices),
                "borderColor": "#FF1744",
                "borderDash": [6, 4],
                "borderWidth": 1.8,
                "fill": False,
                "pointRadius": 0
            },
            {
                "label": "Target Zone (TP)",
                "data": [tp_price] * len(prices),
                "borderColor": "#00B0FF",
                "borderDash": [3, 3],
                "borderWidth": 1.5,
                "fill": False,
                "pointRadius": 0
            }
        ]

        chart_config = {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "title": {"display": True, "text": f"WHALE RADAR PRO | {symbol} FLOW MATRIX", "fontColor": "#ffffff", "fontSize": 14},
                "legend": {"labels": {"fontColor": "#cfd8dc", "boxWidth": 12}},
                "scales": {
                    "xAxes": [{"ticks": {"fontColor": "#78909c"}, "gridLines": {"color": "rgba(255,255,255,0.05)"}}],
                    "yAxes": [{"position": "right", "ticks": {"fontColor": "#78909c"}, "gridLines": {"color": "rgba(255,255,255,0.05)"}}]
                }
            }
        }
        encoded = urllib.parse.quote(json.dumps(chart_config))
        return f"https://quickchart.io/chart?c={encoded}&w=700&h=350&bkg=%230b0e14"
    except Exception:
        return "https://placehold.co/700x350/0b0e14/ffffff?text=Whale+Radar+Engine"

# ==============================================================================
# 3. التحليل الكمي وحساب معايير التداول (OBI & Level-2 Metrics)
# ==============================================================================
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

        # استبعاد أول 3 مستويات لتفادي أخذ سعر الماركت اللحظي نفسه
        filtered_bids = [b for b in bids[3:] if (float(b[0]) * float(b[1])) > 50000]
        filtered_asks = [a for a in asks[3:] if (float(a[0]) * float(a[1])) > 50000]

        top_bid_wall = max(((float(b[0]) * float(b[1])), float(b[0])) for b in filtered_bids) if filtered_bids else (0.0, 0.0)
        top_ask_wall = max(((float(a[0]) * float(a[1])), float(a[0])) for a in filtered_asks) if filtered_asks else (0.0, 0.0)

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

def calculate_trade_setup(direction, price, wall_price):
    """حساب مستويات الدخول، وقف الخسارة، والأهداف بناءً على هندسة السيولة"""
    if direction == "BULLISH":
        entry = price
        # وقف الخسارة أدنى جدار الشراء بـ 0.3%
        stop_loss = wall_price * 0.997 if wall_price < price else price * 0.988
        risk = entry - stop_loss
        tp1 = entry + (risk * 1.8)
        tp2 = entry + (risk * 3.0)
    else:
        entry = price
        # وقف الخسارة أعلى جدار البيع بـ 0.3%
        stop_loss = wall_price * 1.003 if wall_price > price else price * 1.012
        risk = stop_loss - entry
        tp1 = entry - (risk * 1.8)
        tp2 = entry - (risk * 3.0)
    return entry, stop_loss, tp1, tp2

# ==============================================================================
# 4. الرصد اللحظي والتقارير التنفيذية (Institutional Loop)
# ==============================================================================
def market_scanner_loop():
    time.sleep(15)
    while True:
        try:
            for sym in SYMBOLS:
                bid_ratio, bids_usd, asks_usd, top_bid, top_ask = analyze_institutional_depth(sym)
                flow = track_order_flow(sym)

                if not flow:
                    continue

                total_depth = bids_usd + asks_usd
                # فلترة مشددة: حجم دفتر لا يقل عن 600 ألف دولار، واختلال OBI قاطع، ودلتا حقيقية
                heavy_depth = total_depth >= 600000
                extreme_obi = (bid_ratio >= 75.0 or bid_ratio <= 25.0) and heavy_depth
                strong_flow = abs(flow["delta"]) >= 60000 and flow["inst_orders"] >= 1

                if extreme_obi or strong_flow:
                    klines = get_klines_data(sym)
                    if not klines:
                        continue

                    is_bullish = bid_ratio >= 50
                    dir_tag = "BULLISH" if is_bullish else "BEARISH"
                    active_wall_price = top_bid[1] if is_bullish else top_ask[1]
                    active_wall_size = top_bid[0] if is_bullish else top_ask[0]

                    entry, sl, tp1, tp2 = calculate_trade_setup(dir_tag, flow['price'], active_wall_price)
                    chart_url = generate_chart_url(sym, klines, active_wall_price, tp1)

                    price_fmt = f"{flow['price']:.8f}" if flow['price'] < 0.01 else f"{flow['price']:,.2f}"
                    sl_fmt = f"{sl:.8f}" if sl < 0.01 else f"{sl:,.2f}"
                    tp1_fmt = f"{tp1:.8f}" if tp1 < 0.01 else f"{tp1:,.2f}"
                    tp2_fmt = f"{tp2:.8f}" if tp2 < 0.01 else f"{tp2:,.2f}"

                    bias_str = "🟢 شراء وتجميع مؤسسي (Accumulation)" if is_bullish else "🔴 تصريف وجدار بيعي (Distribution)"

                    # تقرير VIP التنفيذي المتكامل
                    vip_report = (
                        f"🐋 WHALE RADAR PRO | تنبيه سيولة مؤسسية\n\n"
                        f"الأصل: #{flow['symbol']} | السعر: ${price_fmt}\n"
                        f"الاتجاه الكمي: {bias_str}\n\n"
                        f"📊 قراءة عمق السيولة (Level-2 Order Book):\n"
                        f"▫️ نسبة هيمنة الدفتر (OBI): {bid_ratio:.1f}%\n"
                        f"▫️ جدار الحوت النشط: ${active_wall_size:,.0f} عند سعر ${active_wall_price}\n"
                        f"▫️ صافي دلتا التدفق: ${flow['delta']:,.0f}\n"
                        f"▫️ صفقات الحيتان الخاطفة: {flow['inst_orders']} صفقة (> $50k+)\n\n"
                        f"🎯 مستويات الخطة التنفيذية (Execution Plan):\n"
                        f"▪️ منطقة التمركز (Entry): ${price_fmt}\n"
                        f"▪️ وقف الخسارة (Invalidation): ${sl_fmt} (كسر الجدار)\n"
                        f"▪️ الهدف الأول (TP1): ${tp1_fmt} (تفريغ جزئي)\n"
                        f"▪️ الهدف الثاني (TP2): ${tp2_fmt} (جدار عكسي)\n\n"
                        f"🎓 التحليل التعليمي وإدارة المخاطر:\n"
                        f"الجدار المرصود يمثل خط دفاع المؤسسة لامتصاص المعروض، عدم كسر مستوى ${sl_fmt} يؤكد استمرار الدفع السعري نحو مستهدفات السيولة."
                    )
                    send_telegram_photo(VIP_CHANNEL_ID, chart_url, vip_report)

                    # تقرير القناة العامة الترويجي ذو القيمة العالية
                    if PUBLIC_PROMO_CHANNEL != VIP_CHANNEL_ID:
                        public_report = (
                            f"⚡️ WHALE RADAR ALERT | رصد تدفق أموال ثقيلة\n\n"
                            f"▫️ الأصل: #{flow['symbol']} | السعر: ${price_fmt}\n"
                            f"▫️ جدار سيولة مؤسسي نشط: ${active_wall_size:,.0f}\n"
                            f"▫️ صافي دلتا الفوليوم: ${flow['delta']:,.0f}\n\n"
                            f"🔒 أهداف الصفقة المحددة برقم، مستويات وقف الخسارة الآلية، والشارت المباشر متاحة داخل قناة VIP."
                        )
                        send_telegram_photo(PUBLIC_PROMO_CHANNEL, chart_url, public_report)

                time.sleep(2)
        except Exception:
            pass
        time.sleep(25)

# ==============================================================================
# 5. نقاط الفحص السحابي (Health & Trigger Endpoints)
# ==============================================================================
@app.route('/')
def home():
    return jsonify({
        "engine": "Whale Radar Pro Institutional Terminal v4.0",
        "chart_engine": "Dynamic Canvas QuickChart",
        "execution_matrix": "Active",
        "status": "online"
    })

@app.route('/trigger-hourly')
def trigger_manual():
    sample_sym = "BTCUSDT"
    flow = track_order_flow(sample_sym)
    bid_ratio, bids_usd, asks_usd, top_bid, top_ask = analyze_institutional_depth(sample_sym)
    klines = get_klines_data(sample_sym)

    if flow and klines:
        is_bullish = bid_ratio >= 50
        dir_tag = "BULLISH" if is_bullish else "BEARISH"
        active_wall_price = top_bid[1] if is_bullish else top_ask[1]
        active_wall_size = top_bid[0] if is_bullish else top_ask[0]

        entry, sl, tp1, tp2 = calculate_trade_setup(dir_tag, flow['price'], active_wall_price)
        chart_url = generate_chart_url(sample_sym, klines, active_wall_price, tp1)

        test_caption = (
            f"📡 تقرير فحص نبض السيولة الساعي | Whale Radar Pro\n\n"
            f"▫️ الأصل: #{sample_sym} | السعر: ${flow['price']:,.2f}\n"
            f"▫️ الجدار المؤسسي: ${active_wall_size:,.0f} عند ${active_wall_price:,.2f}\n"
            f"▫️ نسبة OBI في الدفتر: {bid_ratio:.1f}%\n\n"
            f"🎯 المستويات الحسابية:\n"
            f"▪️ الدخول: ${entry:,.2f}\n"
            f"▪️ الوقف: ${sl:,.2f}\n"
            f"▪️ المستهدف (TP): ${tp1:,.2f}\n\n"
            f"🎓 الشارت يوضح خط الدفاع المؤسسي والمستهدف بدقة."
        )
        ok, reason = send_telegram_photo(PUBLIC_PROMO_CHANNEL, chart_url, test_caption)
        return jsonify({
            "status": "success",
            "photo_sent": ok,
            "detail": reason,
            "trade_setup": {
                "entry": entry,
                "stop_loss": sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2
            },
            "chart_url": chart_url
        })
    return jsonify({"status": "error", "message": "Failed to fetch market data"}), 500

scanner_thread = threading.Thread(target=market_scanner_loop, daemon=True)
scanner_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
