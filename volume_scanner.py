import os
import sys
import time
import math
import logging
import threading
from datetime import datetime
import requests
from flask import Flask

# ==============================================================================
# 1. إعدادات السجلات والنظام (System Logging)
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WhaleScannerVIP")

# ==============================================================================
# 2. خادم الويب الداخلي لحماية استضافة Render (24/7 Keep-Alive Server)
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return {
        "status": "online",
        "service": "Whale Scanner VIP Commercial Engine",
        "timestamp": datetime.utcnow().isoformat(),
        "monitored_pairs": 12
    }, 200

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting Flask keep-alive server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==============================================================================
# 3. الثوابت التجارية ومعلومات الاعتماد (Credentials & Monetization Config)
# ==============================================================================
TELEGRAM_BOT_TOKEN = "8730034376:AAEKzFHv6LGDj2bFOKHH-FrRLImlSGoSUxA"
CHANNEL_ID = -1004496384532
BINANCE_PAY_ID = "1284168199"
ADMIN_CONTACT = "@python.automation1"

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_24HR_URL = "https://api.binance.com/api/v3/ticker/24hr"

# قائمة الأصول الـ 12 المراقبة باستمرار
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT", "PEPEUSDT",
    "SUIUSDT", "LINKUSDT"
]

# معايير خوارزمية الرصد
VOLUME_THRESHOLD_MULTIPLIER = 2.2      # تضاعف الفوليوم عن المتوسط السابق
MINIMUM_PRICE_CHANGE_PCT = 0.35        # أقل تغير سعري مطلوب لتأكيد الزخم
COOLDOWN_PERIOD_SECONDS = 1800         # فترة التهدئة: 30 دقيقة لكل عملة لمنع التكرار
TIMEFRAME = "15m"                      # الفريم التحليلي الأساسي

# سجل إدارة التهدئة في الذاكرة
COOLDOWN_TRACKER = {}

# ==============================================================================
# 4. محرك التيليجرام وإرسال التنبيهات المنمقة (Telegram Messaging Engine)
# ==============================================================================
def escape_markdown(text: str) -> str:
    """تنظيف وتأمين النصوص المتغيرة لمنع تعطل كود التيليجرام"""
    reserved_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in reserved_chars:
        text = text.replace(char, f"\\{char}")
    return text

def send_telegram_alert(message_payload: str) -> bool:
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message_payload,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(endpoint, json=payload, timeout=12)
            if response.status_code == 200:
                logger.info("Signal broadcasted successfully to the VIP channel.")
                return True
            else:
                logger.warning(f"Telegram API warning (Attempt {attempt}): {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as err:
            logger.error(f"Network error communicating with Telegram (Attempt {attempt}): {err}")
        time.sleep(2)
        
    return False

# ==============================================================================
# 5. محرك تحليل السوق المتقدم (Market Data Processing & Volume Analysis)
# ==============================================================================
def fetch_binance_klines(symbol: str, interval: str = "15m", limit: int = 5):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        res = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
        logger.error(f"Binance Klines API error for {symbol}: Code {res.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Binance connection failed for {symbol}: {e}")
    return None

def fetch_24hr_context(symbol: str):
    params = {"symbol": symbol}
    try:
        res = requests.get(BINANCE_24HR_URL, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return {
                "24h_high": float(data.get("highPrice", 0.0)),
                "24h_low": float(data.get("lowPrice", 0.0)),
                "24h_change": float(data.get("priceChangePercent", 0.0))
            }
    except Exception as e:
        logger.error(f"Failed to fetch 24hr stats for {symbol}: {e}")
    return {"24h_high": 0.0, "24h_low": 0.0, "24h_change": 0.0}

def evaluate_symbol_breakout(symbol: str):
    now = time.time()
    
    # التحقق من نظام التهدئة لمنع إزعاج المشتركين
    last_alert_time = COOLDOWN_TRACKER.get(symbol, 0)
    if now - last_alert_time < COOLDOWN_PERIOD_SECONDS:
        return

    klines = fetch_binance_klines(symbol, interval=TIMEFRAME, limit=4)
    if not klines or len(klines) < 4:
        return

    # استخراج بيانات الشموع
    # klines: [timestamp, open, high, low, close, volume, ...]
    hist_candle_1 = klines[-4]
    hist_candle_2 = klines[-3]
    prev_candle   = klines[-2]
    curr_candle   = klines[-1]

    # حساب متوسط الفوليوم لآخر 3 شموع سابقة
    avg_prev_volume = (float(hist_candle_1[5]) + float(hist_candle_2[5]) + float(prev_candle[5])) / 3.0
    curr_volume = float(curr_candle[5])

    curr_open = float(curr_candle[1])
    curr_high = float(curr_candle[2])
    curr_low = float(curr_candle[3])
    curr_close = float(curr_candle[4])

    if avg_prev_volume <= 0:
        return

    volume_ratio = curr_volume / avg_prev_volume
    price_change_pct = ((curr_close - curr_open) / curr_open) * 100.0

    # فلتر الحيتان المزدوج: فوليوم مضاعف + تحرك سعري مؤكد
    if volume_ratio >= VOLUME_THRESHOLD_MULTIPLIER and abs(price_change_pct) >= MINIMUM_PRICE_CHANGE_PCT:
        extra_stats = fetch_24hr_context(symbol)
        
        # تحديد طبيعة واتجاه الصفقة
        if curr_close >= curr_open:
            action_type = "🟢 دخول سيولة تجميعية (BULLISH PUMP)"
            sentiment_tag = "شراء قوي / تراكم حيتان"
        else:
            action_type = "🔴 تصريف وسيولة بيعية (BEARISH DUMP)"
            sentiment_tag = "ضغط بيعي مكثف / خروج حيتان"

        current_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        # بناء التقرير بصياغة تجارية احترافية
        signal_body = (
            f"🚨 *WHALE VOLUME INJECTION DETECTED* 🚨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *الأصل المالي:* `{symbol}`\n"
            f"📊 *نوع الحركة:* {action_type}\n"
            f"💵 *السعر الحالي:* `${curr_close:,.4f}`\n"
            f"📈 *نسبة التغير اللحظي:* `{price_change_pct:+.2f}%`\n"
            f"🔥 *انفجار السيولة:* `{volume_ratio:.2f}x` أعلى من المعدل\n"
            f"⏱ *فريم الرصد:* `{TIMEFRAME}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *بيانات السوق (24 ساعة):*\n"
            f"• التغير اليومي: `{extra_stats['24h_change']:+.2f}%`\n"
            f"• أعلى قمة: `${extra_stats['24h_high']:,.4f}`\n"
            f"• أدنى قاع: `${extra_stats['24h_low']:,.4f}`\n"
            f"• حالة التدفق: *{sentiment_tag}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *إشارة حصرية بقناة VIP التلقائية*\n"
            f"💳 لتجديد الاشتراك أو الدفع عبر Binance Pay:\n"
            f"👉 ID: `{BINANCE_PAY_ID}`\n"
            f"📩 لتأكيد العمليات والتفعيل: {ADMIN_CONTACT}\n"
            f"🕒 توقيت الرصد: `{current_utc} UTC`"
        )

        success = send_telegram_alert(signal_body)
        if success:
            COOLDOWN_TRACKER[symbol] = now
            logger.info(f"Signal confirmed and locked under cooldown for {symbol}")

# ==============================================================================
# 6. المحرك الأساسي وجدولة المسح الدائم (Execution Loop)
# ==============================================================================
def start_continuous_scanner():
    logger.info("=" * 65)
    logger.info("🚀 Whale Scanner Commercial Engine Initiated Successfully")
    logger.info(f"💼 Binance Pay Revenue ID: {BINANCE_PAY_ID}")
    logger.info(f"📢 Broadcast Target Channel: {CHANNEL_ID}")
    logger.info(f"🔎 Actively monitoring {len(WATCHLIST)} major crypto pairs")
    logger.info("=" * 65)

    while True:
        try:
            for pair in WATCHLIST:
                evaluate_symbol_breakout(pair)
                # تأخير زمني محسوب لتفادي حظر Binance IP والحفاظ على كفاءة الخادم
                time.sleep(0.5)

            # استراحة بين كل جولة مسح شاملة
            time.sleep(25)

        except Exception as global_err:
            logger.critical(f"Unexpected runtime exception in main loop: {global_err}", exc_info=True)
            time.sleep(10)

# ==============================================================================
# 7. نقطة الانطلاق (Entry Point)
# ==============================================================================
if __name__ == "__main__":
    # تشغيل خادم الويب في Thread مستقل لمنع تعليق الكود
    server_thread = threading.Thread(target=run_flask_server, daemon=True)
    server_thread.start()

    # تشغيل محرك الرصد الرئيسي
    start_continuous_scanner()




