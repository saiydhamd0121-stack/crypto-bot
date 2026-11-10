import os
import time
import json
import threading
import requests
from flask import Flask, request, jsonify

# ==========================================
# 1. إعدادات البيئة والخادم
# ==========================================
app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PUBLIC_PROMO_CHANNEL = os.environ.get("PUBLIC_PROMO_CHANNEL", "")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "")

# قائمة الأزواج القيادية وعملات الزخم السريع (High-Volatility & Meme)
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "SUIUSDT", "AVAXUSDT"
]

BINANCE_API_BASE = "https://api.binance.com"

# ==========================================
# 2. محرك التيليجرام
# ==========================================
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

# ==========================================
# 3. محرك التحليل الكمي للسيولة (OBI & CVD)
# ==========================================
def analyze_order_book(symbol):
    """تحليل دفتر الطلبات لرصد اختلال السيولة (Order Book Imbalance)"""
    try:
        url = f"{BINANCE_API_BASE}/api/v3/depth?symbol={symbol}&limit=50"
        res = requests.get(url, timeout=5).json()
        bids = sum(float(b[1]) for b in res.get("bids", []))
        asks = sum(float(a[1]) for a in res.get("asks", []))
        total = bids + asks
        if total == 0:
            return 50.0, bids, asks
        bid_ratio = (bids / total) * 100
        return bid_ratio, bids, asks
    except Exception:
        return 50.0, 0, 0

def check_whale_trades(symbol):
    """رصد الصفقات وتحديد التباعد الحجمي الماركت (Delta)"""
    try:
        url = f"{BINANCE_API_BASE}/api/v3/trades?symbol={symbol}&limit=60"
        trades = requests.get(url, timeout=5).json()
        
        buy_vol = 0.0
        sell_vol = 0.0
        huge_trades_count = 0
        last_price = 0.0

        # خفض عتبة الحجم لعملات الميم والعملات البديلة لرصد صفقات الحيتان المناسبة لها
        is_meme_or_alt = symbol in ["PEPEUSDT", "SHIBUSDT", "DOGEUSDT", "SUIUSDT", "AVAXUSDT"]
        threshold = 20000 if is_meme_or_alt else 50000

        for t in trades:
            price = float(t['price'])
            qty = float(t['qty'])
            usd_val = price * qty
            last_price = price

            if t['isBuyerMaker']:
                sell_vol += usd_val
            else:
                buy_vol += usd_val

            if usd_val >= threshold:
                huge_trades_count += 1

        delta = buy_vol - sell_vol
        return {
            "symbol": symbol,
            "price": last_price,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
            "delta": delta,
            "huge_trades": huge_trades_count
        }
    except Exception:
        return None

# ==========================================
# 4. حلقة المسح التلقائي المستمرة (24/7 Scanner)
# ==========================================
def market_scanner_loop():
    time.sleep(12)
    startup_alert = (
        "⚡️ *Whale Radar Pro v3.0 | Multi-Asset Engine Activated*\n\n"
        "▫️ *تم تفعيل تغطية السيولة المؤسسية والعملات السريعة*\n"
        "▫️ قائمة الرصد: `BTC` | `ETH` | `SOL` | `BNB` | `XRP` | `DOGE` | `PEPE` | `SUI`\n"
        "▫️ المحركات النشطة: `Order Book Imbalance (OBI)` + `CVD Delta Tracker`\n"
        "▫️ حالة الاتصال: متصل ومستمر 24/7 على السحابة."
    )
    send_telegram_msg(VIP_CHANNEL_ID, startup_alert)
    if PUBLIC_PROMO_CHANNEL != VIP_CHANNEL_ID:
        send_telegram_msg(PUBLIC_PROMO_CHANNEL, startup_alert)

    while True:
        try:
            for sym in SYMBOLS:
                bid_ratio, bids, asks = analyze_order_book(sym)
                data = check_whale_trades(sym)

                if data and (bid_ratio >= 67.0 or bid_ratio <= 33.0 or data["huge_trades"] >= 2):
                    direction = "🟢 ضغط شراء مؤسسي وتراكم طلبات (Bullish)" if bid_ratio >= 50 else "🔴 تفريغ جداري وضغط بيع ماركت (Bearish)"
                    strength = "انفجارية عالية 🚨" if data["huge_trades"] >= 2 else "زخم متصاعد 📊"

                    # تنسيق السعر بناءً على العملة (خاصة للأصفار الكثيرة مثل PEPE و SHIB)
                    price_format = f"{data['price']:.8f}" if data['price'] < 0.01 else f"{data['price']:,.2f}"

                    alert_msg = (
                        f"🚨 *WHALE RADAR | تسارع سيولة استثنائي*\n\n"
                        f"🔹 *الأصل:* `#{data['symbol']}`\n"
                        f"🔹 *السعر اللحظي:* `${price_format}`\n"
                        f"🔹 *القراءة الكمية:* {direction}\n\n"
                        f"📈 *بيانات دفتر الطلبات والسيولة:*\n"
                        f"▫️ نسبة قوة عروض الشراء: `{bid_ratio:.1f}%`\n"
                        f"▫️ صافي دلتا الفوليوم التراكمي: `${data['delta']:,.0f}`\n"
                        f"▫️ عدد الصفقات الكبرى المرصودة: `{data['huge_trades']}`\n"
                        f"▫️ كثافة الزخم: *{strength}*\n\n"
                        f"💡 *القراءة:* رصد جدار سيولة نشط يمنع الانزلاق السعري في هذا النطاق."
                    )
                    # إرسال التفاصيل لقناة VIP
                    send_telegram_msg(VIP_CHANNEL_ID, alert_msg)

                    # إشعار تشويقي للقناة العامة
                    public_msg = (
                        f"⚡️ *رادار الحيتان رصد تسارع سيولة حاد على {data['symbol']}!*\n\n"
                        f"▫️ السعر الحالي: `${price_format}`\n"
                        f"▫️ صافي السيولة الماركت: `${data['delta']:,.0f}`\n"
                        f"▫️ تحليل مستويات الدخول وجدران السيولة متاح الآن داخل قناة VIP.\n\n"
                        f"👉 انضم للقناة الخاصة لتصلك التنبيهات لحظياً."
                    )
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, public_msg)

                time.sleep(2)
        except Exception:
            pass
        time.sleep(25)

# ==========================================
# 5. نقاط الفحص واستدعاء النبض
# ==========================================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "version": "Whale Radar Pro v3.0 Multi-Asset",
        "monitored_assets": SYMBOLS
    })

@app.route('/trigger-hourly')
def trigger_manual():
    sample_data = check_whale_trades("SOLUSDT")
    bid_ratio, _, _ = analyze_order_book("SOLUSDT")
    if sample_data:
        test_msg = (
            f"📡 *فحص النبض الساعي | تقرير السيولة اللحظي*\n\n"
            f"▫️ الزوج المفحوص: `SOLUSDT`\n"
            f"▫️ السعر الحالي: `${sample_data['price']:,.2f}`\n"
            f"▫️ سيطرة الشراء في الدفتر: `{bid_ratio:.1f}%`\n"
            f"▫️ صافي دلتا الفوليوم: `${sample_data['delta']:,.0f}`\n\n"
            f"✅ محرك المسح متعدد الأصول يعمل بكامل طاقته."
        )
        send_telegram_msg(PUBLIC_PROMO_CHANNEL, test_msg)
        return jsonify({"status": "success", "message": "Multi-asset pulse sent successfully"})
    return jsonify({"status": "error", "message": "Failed to fetch Binance data"}), 500

# ==========================================
# 6. تشغيل المحرك
# ==========================================
scanner_thread = threading.Thread(target=market_scanner_loop, daemon=True)
scanner_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

