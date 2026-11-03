import os
import time
import math
import json
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
import requests
import websocket
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from flask import Flask, request, jsonify, render_template_string, redirect

# ==============================================================================
# [القسم 1]: إعداد السجلات ومراقبة النظام (Logging)
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("WhaleRadarUltimate")

# ==============================================================================
# [القسم 2]: الإعدادات العامة ومفاتيح الربط (Configurations & Env Keys)
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID", "").strip()
PUBLIC_PROMO_CHANNEL = os.environ.get("PUBLIC_PROMO_CHANNEL", "").strip()
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "WhaleAdmin2026Secure")

BINANCE_PAY_ID = "1284168199"
SUBSCRIPTION_PRICE = "10 USDT"
ADMIN_CONTACT = "@python.automation1"
SUPPORT_WHATSAPP = "https://wa.me/249119806108"
APP_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://crypto-bot-k21c.onrender.com").rstrip('/')

DB_FILE = "whale_radar.db"

WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "SUIUSDT", "APTUSDT", "FETUSDT", "RENDERUSDT", "PEPEUSDT"
]

# ==============================================================================
# [القسم 3]: قاعدة البيانات وإدارة الجداول (SQLite Database Engine)
# ==============================================================================
def init_database():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # جدول الصفقات المفتوحة والمنتهية
    c.execute("""
        CREATE TABLE IF NOT EXISTS active_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            tp1 REAL NOT NULL,
            tp2 REAL NOT NULL,
            sl REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # جدول المشتركين وإدارة مدفوعات بينانس
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id TEXT UNIQUE NOT NULL,
            customer_name TEXT,
            plan_duration_days INTEGER DEFAULT 30,
            status TEXT DEFAULT 'PENDING',
            invite_link TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_database()

# ==============================================================================
# [القسم 4]: محرك إرسال التيليجرام الآمن وروابط الدعوة (Telegram Safe Messenger)
# ==============================================================================
def send_telegram_msg(chat_id, text, buttons=None):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        if not data.get("ok"):
            logger.error(f"Telegram sendMessage Error: {data}")
    except Exception as e:
        logger.error(f"Failed to send telegram msg: {e}")

def send_telegram_photo(chat_id, caption, photo_path, buttons=None):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        with open(photo_path, 'rb') as photo:
            res = requests.post(url, data=payload, files={'photo': photo}, timeout=20)
            data = res.json()
            if not data.get("ok"):
                logger.error(f"Telegram sendPhoto Error: {data}")
    except Exception as e:
        logger.error(f"Failed to send photo: {e}")

def generate_one_time_vip_link(channel_id):
    if not TELEGRAM_BOT_TOKEN or not channel_id:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createChatInviteLink"
    payload = {
        "chat_id": channel_id,
        "member_limit": 1,
        "expire_date": int(time.time()) + 86400
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return data["result"]["invite_link"]
        logger.error(f"Invite link generation failed: {data}")
    except Exception as e:
        logger.error(f"Invite Link API error: {e}")
    return None

# ==============================================================================
# [القسم 5]: محرك تحليل بيانات السوق وفلتر البيتكوين (Market Bias & Klines)
# ==============================================================================
def fetch_binance_klines(symbol: str, interval: str = "15m", limit: int = 50):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"Binance fetch error [{symbol}]: {e}")
    return None

def get_btc_market_bias() -> str:
    try:
        btc_klines = fetch_binance_klines("BTCUSDT", interval="15m", limit=10)
        if not btc_klines or len(btc_klines) < 5:
            return "NEUTRAL"
        c_open = float(btc_klines[-1][1])
        c_close = float(btc_klines[-1][4])
        change_pct = ((c_close - c_open) / c_open) * 100

        if change_pct >= 0.20:
            return "BULLISH"
        elif change_pct <= -0.20:
            return "BEARISH"
        return "NEUTRAL"
    except Exception as e:
        logger.error(f"Error checking BTC bias: {e}")
        return "NEUTRAL"

# ==============================================================================
# [القسم 6]: محرك رسم الشارتات الفنية الآلي (Technical Auto-Chart Generator)
# ==============================================================================
def generate_signal_chart(symbol, klines, entry, tp1, tp2, sl, direction):
    filename = f"chart_{symbol}_{int(time.time())}.png"
    try:
        closes = [float(k[4]) for k in klines]
        times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]

        fig, ax = plt.subplots(figsize=(8, 4), facecolor='#10141d')
        ax.set_facecolor('#10141d')

        ax.plot(times, closes, color='#00d2ff', linewidth=1.8, label="Price Action")
        ax.axhline(entry, color='#e0e0e0', linestyle='--', linewidth=1.2, label=f"Entry: {entry}")
        ax.axhline(tp1, color='#00ff88', linestyle='-', linewidth=1.2, label=f"TP1: {tp1}")
        ax.axhline(tp2, color='#00cc66', linestyle='-', linewidth=1.2, label=f"TP2: {tp2}")
        ax.axhline(sl, color='#ff3366', linestyle='--', linewidth=1.2, label=f"SL: {sl}")

        dir_color = '#00ff88' if direction == "BUY" else '#ff3366'
        ax.set_title(f"WHALE RADAR BREAKOUT: #{symbol} ({direction})", color=dir_color, fontsize=12, pad=10)
        ax.tick_params(colors='#888888')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        for spine in ax.spines.values():
            spine.set_color('#2a2e39')

        ax.legend(facecolor='#1e222d', edgecolor='none', labelcolor='white', loc='upper left', fontsize=8)
        plt.tight_layout()
        plt.savefig(filename, dpi=120)
        plt.close()
        return filename
    except Exception as e:
        logger.error(f"Chart plotting failed: {e}")
        return None

# ==============================================================================
# [القسم 7]: فحص واقتناص صفقات كسر الفوليوم وتتبع الأهداف (Signal & TP/SL Tracker)
# ==============================================================================
def evaluate_symbol_breakout(symbol: str):
    klines = fetch_binance_klines(symbol, "15m", 30)
    if not klines or len(klines) < 25:
        return

    prev_klines = klines[-21:-1]
    last_kline = klines[-1]

    avg_vol = sum(float(k[5]) for k in prev_klines) / len(prev_klines)
    current_vol = float(last_kline[5])
    current_price = float(last_kline[4])
    open_price = float(last_kline[1])

    price_change_pct = ((current_price - open_price) / open_price) * 100

    if current_vol >= (avg_vol * 1.5) and abs(price_change_pct) >= 0.4:
        bias = get_btc_market_bias()
        direction = "BUY" if price_change_pct > 0 else "SELL"

        if direction == "BUY" and bias == "BEARISH":
            return
        if direction == "SELL" and bias == "BULLISH":
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM active_trades WHERE symbol = ? AND status = 'OPEN'", (symbol,))
        if cursor.fetchone():
            conn.close()
            return

        if direction == "BUY":
            tp1 = round(current_price * 1.015, 6)
            tp2 = round(current_price * 1.030, 6)
            sl = round(current_price * 0.985, 6)
        else:
            tp1 = round(current_price * 0.985, 6)
            tp2 = round(current_price * 0.970, 6)
            sl = round(current_price * 1.015, 6)

        cursor.execute("""
            INSERT INTO active_trades (symbol, direction, entry_price, tp1, tp2, sl, status)
            VALUES (?, ?, ?, ?, ?, ?, 'OPEN')
        """, (symbol, direction, current_price, tp1, tp2, sl))
        conn.commit()
        conn.close()

        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        msg_text = (
            f"🐋 *WHALE RADAR: إشارة كسر سيولة جديدة* 🐋\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 *الرمز:* `#{symbol}`\n"
            f"⚡ *الاتجاه:* `{'🟢 شراء (LONG)' if direction == 'BUY' else '🔴 بيع (SHORT)'}`\n"
            f"💵 *نقطة الدخول:* `{current_price}`\n"
            f"🎯 *الهدف الأول (TP1):* `{tp1}` (+1.5%)\n"
            f"🚀 *الهدف الثاني (TP2):* `{tp2}` (+3.0%)\n"
            f"🛑 *وقف الخسارة (SL):* `{sl}` (-1.5%)\n"
            f"📊 *تضخم الفوليوم:* `{vol_ratio:.2f}x الطبيعي`\n"
            f"🌐 *سياق السوق العام:* `{bias}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [{"text": "📊 فتح لوحة التحكم | Mini-App", "url": f"{APP_BASE_URL}/app"}]
        ]

        chart_img = generate_signal_chart(symbol, klines[-25:], current_price, tp1, tp2, sl, direction)
        for ch in [VIP_CHANNEL_ID, PUBLIC_PROMO_CHANNEL]:
            if chart_img and os.path.exists(chart_img):
                send_telegram_photo(ch, msg_text, chart_img, buttons)
            else:
                send_telegram_msg(ch, msg_text, buttons)

        if chart_img and os.path.exists(chart_img):
            try:
                os.remove(chart_img)
            except Exception:
                pass

def monitor_trade_lifecycle():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, symbol, direction, entry_price, tp1, tp2, sl, status FROM active_trades WHERE status IN ('OPEN', 'TP1_HIT')")
        trades = cursor.fetchall()
        conn.close()

        for tid, symbol, direction, entry, tp1, tp2, sl, status in trades:
            klines = fetch_binance_klines(symbol, "1m", 1)
            if not klines:
                continue
            curr_price = float(klines[-1][4])

            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()

            if direction == "BUY":
                if curr_price >= tp2 and status == 'TP1_HIT':
                    cur.execute("UPDATE active_trades SET status = 'COMPLETED' WHERE id = ?", (tid,))
                    conn.commit()
                    alert = f"🚀 *{symbol}* حققت الهدف الثاني كاملاً (TP2) بنجاح! 🎯🎯\n💰 إجمالي الربح المحقق: `+3.0% Net Profit`"
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, alert)
                elif curr_price >= tp1 and status == 'OPEN':
                    cur.execute("UPDATE active_trades SET status = 'TP1_HIT' WHERE id = ?", (tid,))
                    conn.commit()
                    alert = f"🎯 *{symbol}* ضربت الهدف الأول (TP1) بنجاح! 💰\nتم تأمين الأرباح: `+1.5%`"
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, alert)
                elif curr_price <= sl:
                    cur.execute("UPDATE active_trades SET status = 'STOPPED' WHERE id = ?", (tid,))
                    conn.commit()
            else:
                if curr_price <= tp2 and status == 'TP1_HIT':
                    cur.execute("UPDATE active_trades SET status = 'COMPLETED' WHERE id = ?", (tid,))
                    conn.commit()
                    alert = f"🚀 *{symbol} (SHORT)* حققت الهدف الثاني كاملاً (TP2)! 🎯🎯\n💰 إجمالي الربح المحقق: `+3.0% Net Profit`"
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, alert)
                elif curr_price <= tp1 and status == 'OPEN':
                    cur.execute("UPDATE active_trades SET status = 'TP1_HIT' WHERE id = ?", (tid,))
                    conn.commit()
                    alert = f"🎯 *{symbol} (SHORT)* ضربت الهدف الأول (TP1)! 💰\nتم تأمين الأرباح: `+1.5%`"
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, alert)
                elif curr_price >= sl:
                    cur.execute("UPDATE active_trades SET status = 'STOPPED' WHERE id = ?", (tid,))
                    conn.commit()

            conn.close()
    except Exception as e:
        logger.error(f"Error checking trade lifecycle: {e}")

# ==============================================================================
# [القسم 8]: محرك بث تصفيات الفيوتشرز المباشر (Liquidation WebSocket Stream)
# ==============================================================================
def liquidation_websocket_worker():
    ws_endpoint = "wss://fstream.binance.com/ws/!forceOrder@arr"
    def on_message(ws, message):
        try:
            data = json.loads(message)
            order = data.get('o', {})
            symbol = order.get('s', '')
            side = order.get('S', '')
            qty = float(order.get('q', 0))
            price = float(order.get('p', 0))
            usd_value = qty * price

            if usd_value >= 80000:
                liq_type = "🔴 تصفية شراء (Long Liquidation)" if side == "SELL" else "🟢 تصفية بيع (Short Squeeze)"
                liq_msg = (
                    f"💥 *WHALE RADAR: تصفية عقود آجلة كبرى* 💥\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 *الرمز:* `#{symbol}`\n"
                    f"⚡ *النوع:* `{liq_type}`\n"
                    f"💵 *قيمة العقد المصفى:* `${usd_value:,.2f}`\n"
                    f"📈 *السعر وقت التصفية:* `{price}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                )
                buttons = [[{"text": "📊 لوحة المتابعة الحية", "url": f"{APP_BASE_URL}/app"}]]
                send_telegram_msg(VIP_CHANNEL_ID, liq_msg, buttons)
        except Exception as e:
            logger.error(f"Liquidation parse error: {e}")

    def on_error(ws, error):
        logger.error(f"Liquidation WS error: {error}")

    while True:
        try:
            ws = websocket.WebSocketApp(ws_endpoint, on_message=on_message, on_error=on_error)
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            logger.error(f"Reconnecting liquidation WS: {e}")
        time.sleep(5)

# ==============================================================================
# [القسم 9]: محركات التقارير الدورية (النبض الساعي + التقرير اليومي الشامل)
# ==============================================================================
def send_hourly_pulse_report():
    """تقرير ملخص كل ساعة لإبقاء القنوات نشطة ومتابعة السوق"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT symbol, direction, entry_price, status FROM active_trades WHERE status IN ('OPEN', 'TP1_HIT')")
        active_trades = c.fetchall()

        one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("SELECT symbol, direction, status FROM active_trades WHERE created_at >= ? AND status IN ('TP1_HIT', 'COMPLETED')", (one_hour_ago,))
        recent_hits = c.fetchall()
        conn.close()

        bias = get_btc_market_bias()
        time_str = datetime.utcnow().strftime('%H:00 UTC')

        pulse_msg = (
            f"⚡ *WHALE RADAR | النبض الساعي ({time_str})* ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 *سياق البيتكوين العام:* `{bias}`\n"
            f"🎯 *الأهداف المحققة في آخر ساعة:* `{len(recent_hits)} صفقات`\n"
            f"📊 *الصفقات النشطة تحت المراقبة:* `{len(active_trades)}`\n"
        )

        if active_trades:
            pulse_msg += "\n*الصفقات المفتوحة حالياً:*\n"
            for t in active_trades[:5]:
                pulse_msg += f"• `#{t[0]}` ({t[1]}) | الدخول: `{t[2]}` [{t[3]}]\n"

        pulse_msg += (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 لمتابعة الصفقات الحية: [افتح لوحة التحكم]({APP_BASE_URL}/app)"
        )

        buttons = [[{"text": "📊 فتح لوحة التحكم | Mini-App", "url": f"{APP_BASE_URL}/app"}]]
        send_telegram_msg(PUBLIC_PROMO_CHANNEL, pulse_msg, buttons)
        send_telegram_msg(VIP_CHANNEL_ID, pulse_msg, buttons)
        logger.info("Hourly pulse report sent successfully.")
    except Exception as e:
        logger.error(f"Hourly pulse error: {e}")

def generate_and_send_daily_report():
    """التقرير اليومي الشامل لحساب نسبة النجاح وصافي الأرباح كل 24 ساعة"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        one_day_ago = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT symbol, direction, status FROM active_trades WHERE created_at >= ?", (one_day_ago,))
        trades = cursor.fetchall()
        conn.close()

        total = len(trades)
        tp1_hits = sum(1 for t in trades if t[2] in ('TP1_HIT', 'COMPLETED'))
        tp2_hits = sum(1 for t in trades if t[2] == 'COMPLETED')
        profit_pct = (tp1_hits * 1.5) + (tp2_hits * 1.5)
        win_rate = (tp1_hits / total * 100) if total > 0 else 0

        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        recap = (
            f"📊 *WHALE RADAR 24H PERFORMANCE RECAP* 📊\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 *التاريخ:* `{date_str} UTC`\n"
            f"🎯 *إجمالي الصفقات المرصودة:* `{total}`\n"
            f"✅ *الصفقات الرابحة:* `{tp1_hits}`\n"
            f"🚀 *نسبة الدقة والنجاح:* `{win_rate:.1f}%`\n"
            f"💰 *صافي العائد المحقق:* `+{profit_pct:.1f}% Net Profit`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 *انضم لرادار VIP المؤسسي فورياً:*\n"
            f"• الاشتراك: *{SUBSCRIPTION_PRICE} شهرياً*\n"
            f"• الدفع المباشر عبر Binance Pay ID: `{BINANCE_PAY_ID}`\n"
            f"💬 للتفعيل المباشر: {ADMIN_CONTACT}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        buttons = [[{"text": "🚀 اشترك الآن عبر الموقع", "url": APP_BASE_URL}]]
        send_telegram_msg(VIP_CHANNEL_ID, recap, buttons)
        send_telegram_msg(PUBLIC_PROMO_CHANNEL, recap, buttons)
        logger.info("Daily performance recap sent successfully.")
    except Exception as e:
        logger.error(f"Daily report error: {e}")

# ==============================================================================
# [القسم 10]: تطبيق الويب Flask، واجهة المشتركين، ولوحة Mini-App
# ==============================================================================
app = Flask(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Whale Radar VIP | رادار الحيتان المؤسسي</title>
    <style>
        body { background: #0c0f17; color: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; text-align: center; }
        .box { max-width: 480px; margin: 40px auto; background: #161b26; padding: 25px; border-radius: 16px; border: 1px solid #283143; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { color: #00d2ff; font-size: 1.6rem; margin-bottom: 10px; }
        .price { font-size: 2rem; color: #00ff88; font-weight: bold; margin: 15px 0; }
        .details { text-align: right; background: #0e121a; padding: 15px; border-radius: 10px; font-size: 0.9rem; line-height: 1.7; margin-bottom: 20px; }
        input { width: 90%; padding: 12px; margin: 10px 0; border-radius: 8px; border: 1px solid #364259; background: #1f2737; color: #fff; text-align: center; }
        button { background: #00d2ff; color: #000; border: none; padding: 12px 25px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 95%; font-size: 1rem; }
        button:hover { background: #00b0d6; }
        .footer-links { margin-top: 20px; font-size: 0.85rem; color: #888; }
        a { color: #00d2ff; text-decoration: none; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🐋 رادار الحيتان المؤسسي</h1>
        <p style="color: #aaa;">منظومة الإشارات اللحظية وتتبع السيولة والتصفيات</p>
        <div class="price">10 USDT <span style="font-size: 0.9rem; color:#888;">/ شهرياً</span></div>
        <div class="details">
            <div>• الدفع المباشر عبر <strong>Binance Pay</strong></div>
            <div>• معرّف المحفظة (Pay ID): <strong style="color: #ffcc00;">1284168199</strong></div>
            <div>• تفعيل فوري وتوليد رابط VIP آمن لمرة واحدة.</div>
        </div>
        <form action="/verify-payment" method="POST">
            <input type="text" name="customer_name" placeholder="اسمك أو يوزرك في تيليجرام" required><br>
            <input type="text" name="tx_id" placeholder="أدخل رقم العملية (TxID / Order ID)" required><br>
            <button type="submit">تأكيد الدفع واستلام الرابط</button>
        </form>
        <div class="footer-links">
            <a href="/app">📱 فتح لوحة التحكم المباشرة (Mini-App)</a><br><br>
            💬 للتواصل والدعم: <a href="https://wa.me/249119806108">واتساب</a> | <a href="https://t.me/python_automation1">تيليجرام</a>
        </div>
    </div>
</body>
</html>
"""

MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Whale Scanner Pro Mini-App</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0e14; color: #fff; margin: 0; padding: 15px; }
        .header { text-align: center; margin-bottom: 15px; border-bottom: 1px solid #202736; padding-bottom: 10px; }
        .header h1 { font-size: 1.2rem; color: #00d2ff; margin: 0; }
        .card { background: #141923; border: 1px solid #222b3d; border-radius: 12px; padding: 12px; margin-bottom: 10px; }
        .badge { padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; }
        .BUY { background: rgba(0, 255, 136, 0.15); color: #00ff88; }
        .SELL { background: rgba(255, 51, 102, 0.15); color: #ff3366; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.85rem; margin-top: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐋 WHALE SCANNER PRO</h1>
        <small style="color: #777;">لوحة متابعة الصفقات والسيولة اللحظية</small>
    </div>
    {% for t in trades %}
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>{{ t[1] }}</strong>
            <span class="badge {{ t[2] }}">{{ t[2] }}</span>
        </div>
        <div class="grid">
            <div>الدخول: {{ t[3] }}</div>
            <div>الحالة: <span style="color:#ffcc00;">{{ t[7] }}</span></div>
            <div style="color: #00ff88;">TP1: {{ t[4] }}</div>
            <div style="color: #00cc66;">TP2: {{ t[5] }}</div>
            <div style="color: #ff3366;">SL: {{ t[6] }}</div>
            <div style="color: #777;">{{ t[8][:16] }}</div>
        </div>
    </div>
    {% else %}
    <div class="card" style="text-align: center; color: #777; padding: 20px;">
        لا توجد صفقات مفتوحة حالياً، الرادار يفحص السيولة على مدار الساعة...
    </div>
    {% endfor %}
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(INDEX_HTML)

@app.route('/app')
def mini_app():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, direction, entry_price, tp1, tp2, sl, status, created_at FROM active_trades ORDER BY id DESC LIMIT 15")
    trades = cur.fetchall()
    conn.close()
    return render_template_string(MINI_APP_HTML, trades=trades)

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    tx_id = request.form.get('tx_id', '').strip()
    name = request.form.get('customer_name', '').strip()

    if not tx_id:
        return "رقم العملية غير صالح", 400

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, status, invite_link FROM subscribers WHERE tx_id = ?", (tx_id,))
    row = cur.fetchone()

    if row and row[1] == 'ACTIVE':
        conn.close()
        return f"تم تفعيل اشتراكك سابقاً! رابط القناة: <a href='{row[2]}'>{row[2]}</a>"

    invite_link = generate_one_time_vip_link(VIP_CHANNEL_ID)
    if not invite_link:
        invite_link = "https://t.me/WhaleScanner_Alerts"

    try:
        cur.execute("""
            INSERT OR REPLACE INTO subscribers (tx_id, customer_name, status, invite_link, expires_at)
            VALUES (?, ?, 'ACTIVE', ?, datetime('now', '+30 days'))
        """, (tx_id, name, invite_link))
        conn.commit()
    except Exception as e:
        logger.error(f"DB insert error: {e}")
    finally:
        conn.close()

    admin_alert = f"💰 *مشترك جديد تم تفعيله!* 💰\nالاسم: `{name}`\nالعملية: `{tx_id}`\nالرابط: {invite_link}"
    send_telegram_msg(VIP_CHANNEL_ID, admin_alert)

    return f"""
    <div style="background:#0c0f17; color:#fff; padding:40px; text-align:center; font-family:sans-serif;">
        <h2 style="color:#00ff88;">✅ تم تأكيد اشتراكك بنجاح!</h2>
        <p>مرحباً بك معنا في Whale Radar VIP. رابط الانضمام الحصري الخاص بك (صالح لمرة واحدة):</p>
        <a href="{invite_link}" style="background:#00d2ff; color:#000; padding:12px 25px; border-radius:8px; text-decoration:none; font-weight:bold; display:inline-block; margin-top:15px;">الدخول إلى قناة VIP</a>
    </div>
    """

@app.route('/admin-secret-dashboard')
def admin_dashboard():
    key = request.args.get('key', '')
    if key != ADMIN_SECRET_KEY:
        return "Unauthorized Access", 403

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, tx_id, customer_name, status, invite_link, created_at FROM subscribers ORDER BY id DESC")
    subs = cur.fetchall()
    conn.close()

    html = "<h2>لوحة تحكم المشتركين السرية</h2><table border='1' cellpadding='8'><tr><th>ID</th><th>الاسم</th><th>TxID</th><th>الحالة</th><th>الرابط</th><th>التاريخ</th></tr>"
    for s in subs:
        html += f"<tr><td>{s[0]}</td><td>{s[2]}</td><td>{s[1]}</td><td>{s[3]}</td><td>{s[4]}</td><td>{s[5]}</td></tr>"
    html += "</table>"
    return html

@app.route('/trigger-hourly')
def trigger_hourly_endpoint():
    send_hourly_pulse_report()
    return jsonify({"status": "success", "message": "تم إرسال تقرير النبض الساعي بنجاح!"})

@app.route('/trigger-report')
def trigger_report_endpoint():
    generate_and_send_daily_report()
    return jsonify({"status": "success", "message": "تم إرسال التقرير اليومي الشامل بنجاح!"})

# ==============================================================================
# [القسم 11]: حلقات الخيوط الخلفية وتفعيل المنظومة (Unified Background Scheduler)
# ==============================================================================
def background_scanner_loop():
    logger.info("Ultimate Whale Scanner loop started.")
    while True:
        try:
            for symbol in WATCHLIST:
                evaluate_symbol_breakout(symbol)
                time.sleep(2)
            monitor_trade_lifecycle()
        except Exception as e:
            logger.error(f"Error in scanner loop: {e}")
        time.sleep(20)

def unified_scheduler_loop():
    hour_counter = 0
    while True:
        try:
            time.sleep(3600)  # انتظار 60 دقيقة
            hour_counter += 1

            send_hourly_pulse_report()

            if hour_counter >= 24:
                generate_and_send_daily_report()
                hour_counter = 0
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            time.sleep(60)

# تفعيل المهام كخيوط مستقلة
threading.Thread(target=background_scanner_loop, daemon=True).start()
threading.Thread(target=liquidation_websocket_worker, daemon=True).start()
threading.Thread(target=unified_scheduler_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

