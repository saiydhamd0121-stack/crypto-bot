import os
import sys
import time
import math
import logging
import threading
from datetime import datetime
import requests
from flask import Flask, request, render_template_string, jsonify

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
# 2. الثوابت وإعدادات القنوات والترويج (Channels & Monetization Config)
# ==============================================================================
TELEGRAM_BOT_TOKEN = "8730034376:AAHnBrqKjyuICdw69mHbszrbi0MFyMcNVGo"

VIP_CHANNEL_ID = -1004496384532               # القناة الخاصة للمشتركين
PUBLIC_PROMO_CHANNEL = "@WhaleScanner_Alerts"  # القناة العامة لجلب الزبائن والترويج
BINANCE_PAY_ID = "1284168199"
ADMIN_CONTACT = "@python.automation1"
SUBSCRIPTION_PRICE = "30 USDT"

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_24HR_URL = "https://api.binance.com/api/v3/ticker/24hr"

# قائمة الأصول المراقبة
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT", "PEPEUSDT",
    "SUIUSDT", "LINKUSDT"
]

VOLUME_THRESHOLD_MULTIPLIER = 2.2
MINIMUM_PRICE_CHANGE_PCT = 0.35
COOLDOWN_PERIOD_SECONDS = 1800
TIMEFRAME = "15m"

COOLDOWN_TRACKER = {}

# ==============================================================================
# 3. واجهة الشراء والترويج (Commercial Web Landing & Checkout)
# ==============================================================================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Whale Scanner VIP | Institutional Crypto Radar</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: #0a0e17; color: #f0f4f8; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
        .card { background: #131b2e; border: 1px solid #1f2d4a; border-radius: 16px; max-width: 480px; width: 100%; padding: 32px; box-shadow: 0 12px 40px rgba(0,0,0,0.6); }
        .badge { background: #00d26a; color: #000; font-weight: bold; font-size: 11px; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; display: inline-block; margin-bottom: 15px; }
        h1 { font-size: 26px; font-weight: 800; margin-bottom: 8px; color: #ffffff; }
        p.subtitle { color: #8da2c0; font-size: 14px; margin-bottom: 24px; line-height: 1.5; }
        .features { background: #0c1220; border-radius: 12px; padding: 18px; margin-bottom: 24px; border: 1px solid #1a253d; }
        .feature-item { display: flex; align-items: center; margin-bottom: 12px; font-size: 14px; color: #d0dbe8; }
        .feature-item:last-child { margin-bottom: 0; }
        .feature-item span { color: #00d26a; margin-right: 10px; font-weight: bold; }
        .price-box { text-align: center; margin-bottom: 24px; }
        .price { font-size: 38px; font-weight: 800; color: #f0b90b; }
        .price-period { color: #8da2c0; font-size: 14px; }
        .pay-box { background: #1a253d; border-radius: 10px; padding: 16px; margin-bottom: 24px; text-align: center; border: 1px dashed #f0b90b; }
        .pay-label { font-size: 12px; color: #8da2c0; text-transform: uppercase; margin-bottom: 6px; }
        .pay-id { font-size: 20px; font-weight: 700; color: #ffffff; letter-spacing: 1px; }
        .form-group { margin-bottom: 16px; text-align: left; }
        label { display: block; font-size: 13px; color: #8da2c0; margin-bottom: 6px; }
        input { width: 100%; padding: 12px; background: #0c1220; border: 1px solid #233352; border-radius: 8px; color: #fff; font-size: 14px; }
        input:focus { outline: none; border-color: #00d26a; }
        button { width: 100%; padding: 14px; background: #f0b90b; color: #000; font-weight: 700; font-size: 15px; border: none; border-radius: 8px; cursor: pointer; transition: 0.2s; }
        button:hover { background: #e0aa00; }
        .status-msg { margin-top: 15px; font-size: 14px; text-align: center; display: none; }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">Live 24/7 Whale Engine</div>
        <h1>Whale Radar VIP</h1>
        <p class="subtitle">Institutional volume breakout scanner tracking whale entries with automated Take-Profit & Stop-Loss targets.</p>
        
        <div class="features">
            <div class="feature-item"><span>✓</span> 15m Institutional Volume Breakout Detection</div>
            <div class="feature-item"><span>✓</span> Automated Entry, TP1 (+1.5%), TP2 (+3%) & Stop Loss</div>
            <div class="feature-item"><span>✓</span> RSI Momentum & 24hr Context Filters</div>
            <div class="feature-item"><span>✓</span> Exclusive VIP Trading Community Access</div>
        </div>

        <div class="price-box">
            <div class="price">30 USDT</div>
            <div class="price-period">Monthly VIP Access</div>
        </div>

        <div class="pay-box">
            <div class="pay-label">Direct Binance Pay ID</div>
            <div class="pay-id">1284168199</div>
        </div>

        <form id="checkoutForm">
            <div class="form-group">
                <label>Telegram Username (e.g. @yourhandle)</label>
                <input type="text" id="tg_username" placeholder="@username" required>
            </div>
            <div class="form-group">
                <label>Binance Pay Transaction ID / Order ID</label>
                <input type="text" id="tx_id" placeholder="Transaction ID" required>
            </div>
            <button type="submit">Verify Payment & Join VIP</button>
        </form>

        <div id="statusMsg" class="status-msg"></div>
    </div>

    <script>
        document.getElementById('checkoutForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            const msg = document.getElementById('statusMsg');
            btn.disabled = true;
            btn.innerText = "Submitting verification...";

            const payload = {
                telegram: document.getElementById('tg_username').value,
                txid: document.getElementById('tx_id').value
            };

            try {
                const res = await fetch('/api/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                msg.style.display = 'block';
                if(data.success) {
                    msg.style.color = '#00d26a';
                    msg.innerHTML = "✅ Verification submitted! Our engine is verifying your payment. Access will be activated shortly.";
                    document.getElementById('checkoutForm').reset();
                } else {
                    msg.style.color = '#ff4d4d';
                    msg.innerHTML = "❌ " + (data.error || "Submission failed.");
                }
            } catch(err) {
                msg.style.display = 'block';
                msg.style.color = '#ff4d4d';
                msg.innerHTML = "❌ Network error. Please try again.";
            } finally {
                btn.disabled = false;
                btn.innerText = "Verify Payment & Join VIP";
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/verify', methods=['POST'])
def verify_payment():
    data = request.get_json() or {}
    tg_user = data.get('telegram', '').strip()
    tx_id = data.get('txid', '').strip()

    if not tg_user or not tx_id:
        return jsonify({"success": False, "error": "Missing Telegram username or Transaction ID"}), 400

    admin_alert = (
        f"💰 *NEW SUBSCRIPTION PAYMENT SUBMITTED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Client:* `{tg_user}`\n"
        f"🧾 *Binance TxID:* `{tx_id}`\n"
        f"💵 *Amount:* `{SUBSCRIPTION_PRICE}`\n"
        f"🕒 *Submitted at:* `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Please verify in your Binance app and grant access."
    )
    send_telegram_msg(VIP_CHANNEL_ID, admin_alert)
    return jsonify({"success": True, "message": "Verification received"}), 200

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting commercial checkout server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==============================================================================
# 4. محرك التيليجرام والنشر (Broadcast & Promo Engine)
# ==============================================================================
def send_telegram_msg(target_chat, message_payload: str) -> bool:
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message_payload,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    for attempt in range(1, 4):
        try:
            res = requests.post(endpoint, json=payload, timeout=12)
            if res.status_code == 200:
                return True
            logger.warning(f"Telegram API response for {target_chat}: {res.status_code} - {res.text}")
        except Exception as err:
            logger.error(f"Error sending message to {target_chat}: {err}")
        time.sleep(2)
    return False

# ==============================================================================
# 5. محرك التحليل الفني ومؤشر RSI (Technical Analysis Engine)
# ==============================================================================
def calculate_rsi(klines, period=14):
    if len(klines) < period + 1:
        return 50.0
    closes = [float(k[4]) for k in klines]
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def fetch_binance_klines(symbol: str, interval: str = "15m", limit: int = 20):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        res = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.error(f"Binance connection failed for {symbol}: {e}")
    return None

def fetch_24hr_context(symbol: str):
    try:
        res = requests.get(BINANCE_24HR_URL, params={"symbol": symbol}, timeout=10)
        if res.status_code == 200:
            d = res.json()
            return {
                "24h_high": float(d.get("highPrice", 0.0)),
                "24h_low": float(d.get("lowPrice", 0.0)),
                "24h_change": float(d.get("priceChangePercent", 0.0))
            }
    except Exception:
        pass
    return {"24h_high": 0.0, "24h_low": 0.0, "24h_change": 0.0}

def evaluate_symbol_breakout(symbol: str):
    now = time.time()
    if now - COOLDOWN_TRACKER.get(symbol, 0) < COOLDOWN_PERIOD_SECONDS:
        return

    klines = fetch_binance_klines(symbol, interval=TIMEFRAME, limit=18)
    if not klines or len(klines) < 16:
        return

    rsi_value = calculate_rsi(klines, period=14)

    curr_candle = klines[-1]
    prev_candle = klines[-2]
    hist_candle_1 = klines[-3]
    hist_candle_2 = klines[-4]

    avg_prev_volume = (float(hist_candle_1[5]) + float(hist_candle_2[5]) + float(prev_candle[5])) / 3.0
    curr_volume = float(curr_candle[5])

    curr_open = float(curr_candle[1])
    curr_close = float(curr_candle[4])

    if avg_prev_volume <= 0:
        return

    volume_ratio = curr_volume / avg_prev_volume
    price_change_pct = ((curr_close - curr_open) / curr_open) * 100.0

    if volume_ratio >= VOLUME_THRESHOLD_MULTIPLIER and abs(price_change_pct) >= MINIMUM_PRICE_CHANGE_PCT:
        extra_stats = fetch_24hr_context(symbol)
        current_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        # 1. حساب أهداف الصفقة
        if curr_close >= curr_open:
            action_type = "🟢 صفقة شراء / صعود حيتان (LONG PUMP)"
            promo_action = "🟢 BULLISH WHALE INFLOW"
            sentiment_tag = "تجميع مؤسساتي قوي"
            tp1 = curr_close * 1.015
            tp2 = curr_close * 1.030
            sl  = curr_close * 0.988
        else:
            action_type = "🔴 صفقة بيع / تصريف حيتان (SHORT DUMP)"
            promo_action = "🔴 BEARISH WHALE OUTFLOW"
            sentiment_tag = "ضغط تصريف بيعي"
            tp1 = curr_close * 0.985
            tp2 = curr_close * 0.970
            sl  = curr_close * 1.012

        # 2. الإشارة الكاملة لقناة المشتركين VIP
        vip_signal = (
            f"🚨 *WHALE VOLUME INJECTION DETECTED* 🚨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *العملة:* `#{symbol}`\n"
            f"📊 *نوع الصفقة:* {action_type}\n"
            f"💵 *سعر الدخول:* `${curr_close:,.4f}`\n"
            f"📈 *تغير الشمعة:* `{price_change_pct:+.2f}%`\n"
            f"🔥 *الفوليوم:* `{volume_ratio:.2f}x` أضعاف المعدل\n"
            f"⚡ *مؤشر RSI:* `{rsi_value}`\n"
            f"⏱ *الفريم:* `{TIMEFRAME}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *خطة التداول المعتمدة:*\n"
            f"• Target 1: `${tp1:,.4f}`\n"
            f"• Target 2: `${tp2:,.4f}`\n"
            f"• Stop Loss: `${sl:,.4f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *سياق السوق 24h:*\n"
            f"• تغير اليوم: `{extra_stats['24h_change']:+.2f}%`\n"
            f"• الحالة: *{sentiment_tag}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *Whale Radar VIP Engine*\n"
            f"💰 الاشتراك: `{SUBSCRIPTION_PRICE}` / شهر\n"
            f"💳 Binance Pay ID: `{BINANCE_PAY_ID}`\n"
            f"🕒 `{current_utc} UTC`"
        )

        # 3. المنشور الترويجي العالمي للقناة العامة (لجلب الزبائن)
        promo_signal = (
            f"🚨 *INSTITUTIONAL WHALE ALERT* 🚨\n\n"
            f"🪙 Asset: *${symbol.replace('USDT', '')}*\n"
            f"⚡ Action: *{promo_action}*\n"
            f"📈 Price Change: `{price_change_pct:+.2f}%` in 15m\n"
            f"🔥 Volume Spike: `{volume_ratio:.2f}x` above average!\n\n"
            f"🔒 *Target 1, Target 2 & Stop-Loss are unlocked for VIP Members only.*\n\n"
            f"💎 Join VIP to get complete entry/exit levels & live tracking:\n"
            f"👉 Subscription: *{SUBSCRIPTION_PRICE}* via Binance Pay ID `{BINANCE_PAY_ID}`\n"
            f"📩 Contact to join: {ADMIN_CONTACT}\n\n"
            f"#Crypto #WhaleAlert #Binance #{symbol.replace('USDT', '')}"
        )

        vip_sent = send_telegram_msg(VIP_CHANNEL_ID, vip_signal)
        promo_sent = send_telegram_msg(PUBLIC_PROMO_CHANNEL, promo_signal)

        if vip_sent or promo_sent:
            COOLDOWN_TRACKER[symbol] = now
            logger.info(f"Signal and global promo broadcasted for {symbol}")

# ==============================================================================
# 6. المحرك الأساسي وجدولة المسح الدائم (Execution Loop)
# ==============================================================================
def start_continuous_scanner():
    logger.info("=" * 65)
    logger.info("🚀 Whale Scanner Commercial Engine Initiated")
    logger.info(f"💼 Binance Pay Revenue ID: {BINANCE_PAY_ID}")
    logger.info(f"💲 Monthly Subscription Rate: {SUBSCRIPTION_PRICE}")
    logger.info(f"📢 VIP Target: {VIP_CHANNEL_ID}")
    logger.info(f"🌍 Public Global Promo: {PUBLIC_PROMO_CHANNEL}")
    logger.info("=" * 65)

    # رسالة إطلاق تجريبية فورية للقناة العامة
    promo_welcome = (
        "🟢 *Whale Radar Free Alerts is officially LIVE!*\n\n"
        "📡 Tracking institutional volume spikes across Binance 24/7.\n"
        "⚡ Signals will be posted here automatically.\n\n"
        "💎 For complete TP/SL targets & VIP community:\n"
        f"👉 Monthly pass: *{SUBSCRIPTION_PRICE}* via Binance Pay ID `{BINANCE_PAY_ID}`\n"
        f"📩 Support: {ADMIN_CONTACT}"
    )
    send_telegram_msg(PUBLIC_PROMO_CHANNEL, promo_welcome)

    while True:
        try:
            for pair in WATCHLIST:
                evaluate_symbol_breakout(pair)
                time.sleep(0.5)

            time.sleep(25)

        except Exception as global_err:
            logger.critical(f"Runtime error in scanner: {global_err}", exc_info=True)
            time.sleep(10)

# ==============================================================================
# 7. نقطة الانطلاق (Entry Point)
# ==============================================================================
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask_server, daemon=True)
    server_thread.start()
    start_continuous_scanner()



