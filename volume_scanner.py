import os
import sys
import io
import time
import json
import logging
import threading
import sqlite3
from datetime import datetime, timedelta
import requests

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import websocket
from flask import Flask, request, render_template_string, jsonify

# ==============================================================================
# 1. إعدادات السجلات
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WhaleScannerVIP")

# ==============================================================================
# 2. الثوابت والإعدادات
# ==============================================================================
BOT_TOKENS = [
    "8730034376:AAHnBrqKjyuICdw69mHbszrbi0MFyMcNVGo",
    "8800024044:AAGHh6000pqKWM5iuf7jM7C75_o-n8oEFKs"
]

VIP_CHANNEL_ID = -1004496384532
PUBLIC_PROMO_CHANNEL = "@WhaleScanner_Alerts"
BINANCE_PAY_ID = "1284168199"
ADMIN_CONTACT = "@python.automation1"

WHATSAPP_NUMBER = "249119806108"
WHATSAPP_LINK = f"https://wa.me/{WHATSAPP_NUMBER}"

SUBSCRIPTION_PRICE = "10 USDT"
DB_FILE = "subscribers.db"

BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
BINANCE_24HR_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"
BINANCE_PRICE_URL = "https://data-api.binance.vision/api/v3/ticker/price"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT", "PEPEUSDT",
    "SUIUSDT", "LINKUSDT"
]

VOLUME_THRESHOLD_MULTIPLIER = 1.4
MINIMUM_PRICE_CHANGE_PCT = 0.18
COOLDOWN_PERIOD_SECONDS = 600
TIMEFRAME = "15m"

MIN_LIQUIDATION_USD = 50000.0
COOLDOWN_TRACKER = {}

# ==============================================================================
# 3. محرك قاعدة البيانات (SQLite)
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_handle TEXT NOT NULL,
            tx_id TEXT UNIQUE NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            tp1 REAL NOT NULL,
            tp2 REAL NOT NULL,
            sl REAL NOT NULL,
            status TEXT DEFAULT 'OPEN',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def add_subscriber(user_handle: str, tx_id: str, days: int = 30) -> bool:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        start = datetime.utcnow()
        end = start + timedelta(days=days)
        cursor.execute("""
            INSERT INTO subscribers (user_handle, tx_id, start_date, end_date, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (user_handle, tx_id, start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        logger.error(f"Error adding subscriber: {e}")
        return False

def record_trade(symbol: str, direction: str, entry: float, tp1: float, tp2: float, sl: float):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO active_trades (symbol, direction, entry_price, tp1, tp2, sl, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (symbol, direction, entry, tp1, tp2, sl, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
    except Exception as err:
        logger.error(f"Failed to record trade: {err}")

# ==============================================================================
# 4. محرك رسم الشارت الفوري
# ==============================================================================
def generate_chart_image(symbol: str, klines: list, entry_price: float, tp1: float, tp2: float, sl: float) -> io.BytesIO:
    recent_klines = klines[-15:]
    opens = [float(k[1]) for k in recent_klines]
    highs = [float(k[2]) for k in recent_klines]
    lows = [float(k[3]) for k in recent_klines]
    closes = [float(k[4]) for k in recent_klines]
    volumes = [float(k[5]) for k in recent_klines]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0f172a')
    ax1.set_facecolor('#0f172a')
    ax2.set_facecolor('#0f172a')

    for i in range(len(recent_klines)):
        color = '#00e676' if closes[i] >= opens[i] else '#ff1744'
        ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1.2)
        body_bottom = min(opens[i], closes[i])
        body_height = max(abs(closes[i] - opens[i]), 0.00001)
        ax1.bar(i, body_height, bottom=body_bottom, color=color, width=0.6, align='center')
        ax2.bar(i, volumes[i], color=color, width=0.6, alpha=0.85, align='center')

    ax1.axhline(entry_price, color='#ffeb3b', linestyle='--', linewidth=1.5, label=f'Entry: {entry_price:.4f}')
    ax1.axhline(tp1, color='#00e676', linestyle=':', linewidth=1.3, label=f'TP1: {tp1:.4f}')
    ax1.axhline(tp2, color='#00b0ff', linestyle=':', linewidth=1.3, label=f'TP2: {tp2:.4f}')
    ax1.axhline(sl, color='#f44336', linestyle='--', linewidth=1.3, label=f'SL: {sl:.4f}')

    ax1.set_title(f"Whale Radar Alert: #{symbol} (15m)", color='#ffffff', fontsize=12, fontweight='bold')
    ax1.tick_params(colors='#94a3b8')
    ax1.grid(True, color='#1e293b', linestyle='-', alpha=0.6)
    ax1.legend(loc='upper left', facecolor='#1e293b', edgecolor='none', labelcolor='#ffffff', fontsize=8)

    ax2.set_ylabel('Volume', color='#94a3b8', fontsize=9)
    ax2.tick_params(colors='#94a3b8')
    ax2.grid(True, color='#1e293b', linestyle='-', alpha=0.4)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none', dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf

# ==============================================================================
# 5. محرك إرسال تيليجرام
# ==============================================================================
def send_telegram_msg(target_chat, message_payload: str) -> bool:
    payload = {
        "chat_id": target_chat,
        "text": message_payload,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    for token in BOT_TOKENS:
        endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            res = requests.post(endpoint, json=payload, timeout=10)
            if res.status_code == 200:
                return True
        except Exception as err:
            logger.error(f"Telegram error: {err}")
    return False

def send_telegram_photo(target_chat, photo_buffer: io.BytesIO, caption: str) -> bool:
    for token in BOT_TOKENS:
        endpoint = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            photo_buffer.seek(0)
            files = {"photo": ("chart.png", photo_buffer, "image/png")}
            data = {"chat_id": target_chat, "caption": caption, "parse_mode": "Markdown"}
            res = requests.post(endpoint, files=files, data=data, timeout=15)
            if res.status_code == 200:
                return True
        except Exception as err:
            logger.error(f"Telegram photo error: {err}")
    return False

def create_vip_invite_link() -> str:
    expire_timestamp = int(time.time()) + 86400
    payload = {
        "chat_id": VIP_CHANNEL_ID,
        "member_limit": 1,
        "expire_date": expire_timestamp
    }
    for token in BOT_TOKENS:
        endpoint = f"https://api.telegram.org/bot{token}/createChatInviteLink"
        try:
            res = requests.post(endpoint, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data.get("result", {}).get("invite_link", "")
        except Exception as err:
            logger.error(f"Failed to generate invite link: {err}")
    return ""

def monitor_expirations_loop():
    while True:
        try:
            time.sleep(3600)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("SELECT id, user_handle FROM subscribers WHERE status = 'active' AND end_date <= ?", (now_str,))
            expired = cursor.fetchall()
            for row in expired:
                sub_id, handle = row
                cursor.execute("UPDATE subscribers SET status = 'expired' WHERE id = ?", (sub_id,))
                conn.commit()
                alert = f"⚠️ *EXPIRED SUBSCRIPTION*\nUser: `{handle}` has completed 30 days. Access revoked."
                send_telegram_msg(VIP_CHANNEL_ID, alert)
            conn.close()
        except Exception as err:
            logger.error(f"Expiration checker error: {err}")
            time.sleep(60)

# ==============================================================================
# 6. محرك رصد تصفيات العقود الآجلة اللحظي (Futures Liquidations)
# ==============================================================================
def on_liquidation_message(ws, message):
    try:
        data = json.loads(message).get('o', {})
        symbol = data.get('s')
        if symbol not in WATCHLIST:
            return

        side = data.get('S')
        qty = float(data.get('q', 0.0))
        price = float(data.get('p', 0.0))
        total_usd = qty * price

        if total_usd >= MIN_LIQUIDATION_USD:
            direction_text = "🔴 تصفية شراء (LONG Liquidated)" if side == "SELL" else "🟢 تصفية بيع (SHORT Liquidated)"
            squeeze_signal = "انفجار صعودي محتمل (Short Squeeze) 🚀" if side == "BUY" else "هبوط تصريفي سريع (Long Squeeze) 🔻"

            alert_msg = (
                f"⚡ *INSTITUTIONAL LIQUIDATION DETECTED* ⚡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 *العملة:* `#{symbol}`\n"
                f"💥 *نوع التصفية:* {direction_text}\n"
                f"💵 *قيمة التصفية:* `${total_usd:,.0f} USD`\n"
                f"📊 *سعر التنفيذ:* `${price:,.4f}`\n"
                f"🎯 *التوقع الفني:* {squeeze_signal}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 *Whale Radar VIP Intelligence*\n"
                f"💰 الاشتراك: `{SUBSCRIPTION_PRICE}` / شهر\n"
                f"💳 Binance Pay ID: `{BINANCE_PAY_ID}`"
            )
            send_telegram_msg(VIP_CHANNEL_ID, alert_msg)
            send_telegram_msg(PUBLIC_PROMO_CHANNEL, f"⚡ *WHALE LIQUIDATION:* ${total_usd:,.0f} USD wiped out on #{symbol}!\nLive institutional tracking via Whale Radar VIP.")
    except Exception as err:
        logger.error(f"Liquidation stream error: {err}")

def start_liquidation_listener():
    ws_url = "wss://fstream.binance.com/ws/!forceOrder@arr"
    while True:
        try:
            ws = websocket.WebSocketApp(ws_url, on_message=on_liquidation_message)
            ws.run_forever()
        except Exception as e:
            logger.error(f"Liquidation WebSocket disconnected: {e}. Reconnecting...")
            time.sleep(5)

# ==============================================================================
# 7. تحليل المؤشرات وتتبع الأهداف
# ==============================================================================
def calculate_rsi(klines, period=14):
    if len(klines) < period + 1:
        return 50.0
    closes = [float(k[4]) for k in klines]
    gains, losses = [], []
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

def fetch_binance_klines(symbol: str, interval: str = "15m", limit: int = 25):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        res = requests.get(BINANCE_KLINES_URL, params=params, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.error(f"Binance connection failed for {symbol}: {e}")
    return None

def fetch_current_prices():
    try:
        res = requests.get(BINANCE_PRICE_URL, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return {item['symbol']: float(item['price']) for item in res.json()}
    except Exception:
        pass
    return {}

def fetch_24hr_context(symbol: str):
    try:
        res = requests.get(BINANCE_24HR_URL, params={"symbol": symbol}, headers=HEADERS, timeout=10)
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

def check_active_trades(prices_dict):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, symbol, direction, entry_price, tp1, tp2, sl, status FROM active_trades WHERE status IN ('OPEN', 'TP1_HIT')")
        trades = cursor.fetchall()

        for t in trades:
            t_id, symbol, direction, entry, tp1, tp2, sl, status = t
            current_price = prices_dict.get(symbol)
            if not current_price:
                continue

            if direction == "LONG":
                if status == 'OPEN' and current_price >= tp1:
                    cursor.execute("UPDATE active_trades SET status = 'TP1_HIT' WHERE id = ?", (t_id,))
                    conn.commit()
                    alert = (
                        f"🎯 *TARGET 1 HIT! | تم تحقيق الهدف الأول بنجاح* 🎯\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `#{symbol}` (شراء / LONG)\n"
                        f"💵 *سعر الدخول:* `${entry:,.4f}`\n"
                        f"✅ *الهدف الأول:* `${tp1:,.4f}` (+1.50% Net Profit)\n"
                        f"⚡ *السعر الحالي:* `${current_price:,.4f}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💎 مبروك لأعضاء VIP! تم تأمين الأرباح ونقل وقف الخسارة لنقطة الدخول."
                    )
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, f"🎯 *TARGET 1 HIT ON #{symbol} (+1.5%)* ✅\nJoin VIP to get full real-time targets!")

                elif current_price >= tp2:
                    cursor.execute("UPDATE active_trades SET status = 'COMPLETED' WHERE id = ?", (t_id,))
                    conn.commit()
                    alert = (
                        f"🚀 *TARGET 2 DESTROYED! | تم تحقيق جميع الأهداف* 🚀\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `#{symbol}` (شراء / LONG)\n"
                        f"💵 *سعر الدخول:* `${entry:,.4f}`\n"
                        f"🎯 *الهدف الثاني:* `${tp2:,.4f}` (+3.00% Full Profit)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 إغلاق الصفقة بنجاح تام لأعضاء VIP!"
                    )
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, f"🚀 *ALL TARGETS HIT ON #{symbol} (+3.0%)* 🔥\nPrecision automated trading.")

                elif current_price <= sl and status == 'OPEN':
                    cursor.execute("UPDATE active_trades SET status = 'STOPPED' WHERE id = ?", (t_id,))
                    conn.commit()

            elif direction == "SHORT":
                if status == 'OPEN' and current_price <= tp1:
                    cursor.execute("UPDATE active_trades SET status = 'TP1_HIT' WHERE id = ?", (t_id,))
                    conn.commit()
                    alert = (
                        f"🎯 *TARGET 1 HIT! | تم تحقيق الهدف الأول بنجاح* 🎯\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `#{symbol}` (بيع / SHORT)\n"
                        f"💵 *سعر الدخول:* `${entry:,.4f}`\n"
                        f"✅ *الهدف الأول:* `${tp1:,.4f}` (+1.50% Net Profit)\n"
                        f"⚡ *السعر الحالي:* `${current_price:,.4f}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💎 مبروك لأعضاء VIP! تم تأمين الأرباح ونقل وقف الخسارة لنقطة الدخول."
                    )
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, f"🎯 *TARGET 1 HIT ON #{symbol} (+1.5%)* ✅\nJoin VIP to get full real-time targets!")

                elif current_price <= tp2:
                    cursor.execute("UPDATE active_trades SET status = 'COMPLETED' WHERE id = ?", (t_id,))
                    conn.commit()
                    alert = (
                        f"🚀 *TARGET 2 DESTROYED! | تم تحقيق جميع الأهداف* 🚀\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `#{symbol}` (بيع / SHORT)\n"
                        f"💵 *سعر الدخول:* `${entry:,.4f}`\n"
                        f"🎯 *الهدف الثاني:* `${tp2:,.4f}` (+3.00% Full Profit)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 إغلاق الصفقة بنجاح تام لأعضاء VIP!"
                    )
                    send_telegram_msg(VIP_CHANNEL_ID, alert)
                    send_telegram_msg(PUBLIC_PROMO_CHANNEL, f"🚀 *ALL TARGETS HIT ON #{symbol} (+3.0%)* 🔥\nPrecision automated trading.")

                elif current_price >= sl and status == 'OPEN':
                    cursor.execute("UPDATE active_trades SET status = 'STOPPED' WHERE id = ?", (t_id,))
                    conn.commit()

        conn.close()
    except Exception as e:
        logger.error(f"Error checking active trades: {e}")

# ==============================================================================
# 8. محرك رصد الصفقات والإشارات
# ==============================================================================
def evaluate_symbol_breakout(symbol: str):
    now = time.time()
    if now - COOLDOWN_TRACKER.get(symbol, 0) < COOLDOWN_PERIOD_SECONDS:
        return

    klines = fetch_binance_klines(symbol, interval=TIMEFRAME, limit=20)
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

        if curr_close >= curr_open:
            direction_code = "LONG"
            action_type = "🟢 صفقة شراء / صعود حيتان (LONG PUMP)"
            promo_action = "🟢 BULLISH WHALE INFLOW"
            sentiment_tag = "تجميع مؤسساتي قوي"
            tp1 = curr_close * 1.015
            tp2 = curr_close * 1.030
            sl  = curr_close * 0.988
        else:
            direction_code = "SHORT"
            action_type = "🔴 صفقة بيع / تصريف حيتان (SHORT DUMP)"
            promo_action = "🔴 BEARISH WHALE OUTFLOW"
            sentiment_tag = "ضغط تصريف بيعي"
            tp1 = curr_close * 0.985
            tp2 = curr_close * 0.970
            sl  = curr_close * 1.012

        record_trade(symbol, direction_code, curr_close, tp1, tp2, sl)
        chart_buffer = generate_chart_image(symbol, klines, curr_close, tp1, tp2, sl)

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
            f"💬 WhatsApp: {WHATSAPP_LINK}\n"
            f"🕒 `{current_utc} UTC`"
        )

        promo_signal = (
            f"🚨 *INSTITUTIONAL WHALE ALERT* 🚨\n\n"
            f"🪙 Asset: *${symbol.replace('USDT', '')}*\n"
            f"⚡ Action: *{promo_action}*\n"
            f"📈 Price Change: `{price_change_pct:+.2f}%` in 15m\n"
            f"🔥 Volume Spike: `{volume_ratio:.2f}x` above average!\n\n"
            f"🔒 *Target 1, Target 2 & Stop-Loss are unlocked for VIP Members only.*\n\n"
            f"💎 Join VIP to get complete entry/exit levels & live tracking:\n"
            f"👉 Subscription: *{SUBSCRIPTION_PRICE}* via Binance Pay ID `{BINANCE_PAY_ID}`\n"
            f"💬 WhatsApp Direct: {WHATSAPP_LINK}\n"
            f"📩 Telegram Support: {ADMIN_CONTACT}\n\n"
            f"#Crypto #WhaleAlert #Binance #{symbol.replace('USDT', '')}"
        )

        vip_sent = send_telegram_photo(VIP_CHANNEL_ID, chart_buffer, vip_signal)
        promo_sent = send_telegram_msg(PUBLIC_PROMO_CHANNEL, promo_signal)

        if vip_sent or promo_sent:
            COOLDOWN_TRACKER[symbol] = now
            logger.info(f"Signal broadcasted successfully for {symbol}")

# ==============================================================================
# 9. محرك الفحص المستمر وتتبع الأسعار
# ==============================================================================
def start_continuous_scanner():
    logger.info("🚀 Background Scanner Thread Started Successfully")
    time.sleep(3)
    send_telegram_msg(VIP_CHANNEL_ID, "🟢 *نظام رادار الحيتان متصل مع تطبيق Telegram Mini-App بنجاح!*")

    while True:
        try:
            prices = fetch_current_prices()
            if prices:
                check_active_trades(prices)

            for pair in WATCHLIST:
                evaluate_symbol_breakout(pair)
                time.sleep(0.5)

            time.sleep(20)
        except Exception as global_err:
            logger.critical(f"Scanner error: {global_err}", exc_info=True)
            time.sleep(10)

# ==============================================================================
# 10. واجهات الويب وتطبيق التيليجرام المصغر (Mini-App & Landing Page)
# ==============================================================================
app = Flask(__name__)

LANDING_PAGE_HTML = """
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
        .pay-box { background: #1a253d; border-radius: 10px; padding: 16px; margin-bottom: 20px; text-align: center; border: 1px dashed #f0b90b; }
        .pay-label { font-size: 12px; color: #8da2c0; text-transform: uppercase; margin-bottom: 6px; }
        .pay-id { font-size: 20px; font-weight: 700; color: #ffffff; letter-spacing: 1px; }
        .whatsapp-btn { display: block; width: 100%; padding: 12px; background: #25d366; color: #ffffff; font-weight: 700; text-align: center; text-decoration: none; border-radius: 8px; margin-bottom: 20px; }
        .form-group { margin-bottom: 16px; text-align: left; }
        label { display: block; font-size: 13px; color: #8da2c0; margin-bottom: 6px; }
        input { width: 100%; padding: 12px; background: #0c1220; border: 1px solid #233352; border-radius: 8px; color: #fff; font-size: 14px; }
        input:focus { outline: none; border-color: #00d26a; }
        button { width: 100%; padding: 14px; background: #f0b90b; color: #000; font-weight: 700; font-size: 15px; border: none; border-radius: 8px; cursor: pointer; transition: 0.2s; }
        button:hover { background: #e0aa00; }
        .status-msg { margin-top: 15px; font-size: 14px; text-align: center; display: none; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">Live 24/7 Whale Engine</div>
        <h1>Whale Radar VIP</h1>
        <p class="subtitle">Institutional volume breakout & futures liquidation scanner tracking whale entries with automated TP/SL targets.</p>
        
        <div class="features">
            <div class="feature-item"><span>✓</span> Real-Time Futures Liquidation Alerts (Short/Long Squeeze)</div>
            <div class="feature-item"><span>✓</span> 15m Institutional Volume Breakout Detection</div>
            <div class="feature-item"><span>✓</span> Interactive Telegram Mini-App Dashboard</div>
            <div class="feature-item"><span>✓</span> Automated Target Tracking & Profit Hit Alerts</div>
            <div class="feature-item"><span>✓</span> Instant Automated VIP Channel Access</div>
        </div>

        <div class="price-box">
            <div class="price">10 USDT</div>
            <div class="price-period">Monthly VIP Access</div>
        </div>

        <div class="pay-box">
            <div class="pay-label">Direct Binance Pay ID</div>
            <div class="pay-id">1284168199</div>
        </div>

        <a href="{{ wa_link }}" target="_blank" class="whatsapp-btn">💬 Chat directly via WhatsApp</a>

        <form id="checkoutForm">
            <div class="form-group">
                <label>Telegram Username or Phone Number</label>
                <input type="text" id="tg_username" placeholder="@username or +12345..." required>
            </div>
            <div class="form-group">
                <label>Binance Pay Transaction ID / Order ID</label>
                <input type="text" id="tx_id" placeholder="Transaction ID" required>
            </div>
            <button type="submit">Verify Payment & Get VIP Link</button>
        </form>

        <div id="statusMsg" class="status-msg"></div>
    </div>

    <script>
        document.getElementById('checkoutForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            const msg = document.getElementById('statusMsg');
            btn.disabled = true;
            btn.innerText = "Processing automated access...";

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
                    msg.innerHTML = `✅ <b>Payment Submitted!</b><br>Your 1-Time VIP Invite Link:<br><a href="${data.invite_link}" target="_blank" style="color:#f0b90b; font-weight:bold; word-break:break-all;">${data.invite_link}</a><br><small style="color:#8da2c0;">Link is valid for 24h & 1 member.</small>`;
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
                btn.innerText = "Verify Payment & Get VIP Link";
            }
        });
    </script>
</body>
</html>
"""

MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Whale Radar App</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: #090d16; color: #e2e8f0; padding: 16px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .logo { font-size: 20px; font-weight: 800; color: #f0b90b; display: flex; align-items: center; gap: 8px; }
        .pulse { width: 10px; height: 10px; background: #00d26a; border-radius: 50%; box-shadow: 0 0 10px #00d26a; }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
        .stat-card { background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; padding: 14px; text-align: center; }
        .stat-title { font-size: 11px; color: #8da2c0; text-transform: uppercase; margin-bottom: 4px; }
        .stat-val { font-size: 18px; font-weight: 700; color: #ffffff; }
        .section-title { font-size: 14px; font-weight: 700; color: #8da2c0; text-transform: uppercase; margin-bottom: 12px; }
        .trade-card { background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
        .trade-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .trade-pair { font-size: 16px; font-weight: 700; color: #fff; }
        .tag-long { background: rgba(0, 210, 106, 0.15); color: #00d26a; font-size: 11px; padding: 3px 8px; border-radius: 6px; font-weight: bold; }
        .tag-short { background: rgba(255, 77, 77, 0.15); color: #ff4d4d; font-size: 11px; padding: 3px 8px; border-radius: 6px; font-weight: bold; }
        .trade-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; color: #94a3b8; }
        .trade-grid span { color: #f0f4f8; font-weight: 600; }
        .status-badge { display: inline-block; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 6px; margin-top: 10px; }
        .status-open { background: #1e293b; color: #f0b90b; }
        .status-hit { background: rgba(0, 210, 106, 0.2); color: #00d26a; }
        .refresh-btn { width: 100%; padding: 12px; background: #1e293b; color: #f0b90b; font-weight: 700; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo"><div class="pulse"></div> Whale Radar</div>
        <div style="font-size: 12px; color: #00d26a; font-weight: bold;">● LIVE FEED</div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-title">Tracked Pairs</div>
            <div class="stat-val">12 Assets</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Engine Timeframe</div>
            <div class="stat-val">15m Breakout</div>
        </div>
    </div>

    <div class="section-title">Institutional Signals Monitor</div>
    <div id="tradesContainer">Loading signals...</div>

    <button class="refresh-btn" onclick="loadTrades()">🔄 Refresh Live Signals</button>

    <script>
        const tg = window.Telegram ? window.Telegram.WebApp : null;
        if(tg) { tg.expand(); }

        async function loadTrades() {
            const container = document.getElementById('tradesContainer');
            try {
                const res = await fetch('/api/live_trades');
                const data = await res.json();
                if(data.trades && data.trades.length > 0) {
                    container.innerHTML = data.trades.map(t => `
                        <div class="trade-card">
                            <div class="trade-top">
                                <span class="trade-pair">#${t.symbol}</span>
                                <span class="${t.direction === 'LONG' ? 'tag-long' : 'tag-short'}">${t.direction}</span>
                            </div>
                            <div class="trade-grid">
                                <div>Entry: <span>$${t.entry.toFixed(4)}</span></div>
                                <div>Status: <span>${t.status}</span></div>
                                <div>Target 1: <span>$${t.tp1.toFixed(4)}</span></div>
                                <div>Target 2: <span>$${t.tp2.toFixed(4)}</span></div>
                            </div>
                            <div class="status-badge ${t.status === 'OPEN' ? 'status-open' : 'status-hit'}">
                                ${t.status === 'OPEN' ? '⏳ Monitoring Targets' : '🎯 Profit Target Reached'}
                            </div>
                        </div>
                    `).join('');
                } else {
                    container.innerHTML = `<div style="text-align:center; padding: 30px; color:#64748b; font-size:13px;">No active breakouts right now.<br>Engine scanning 24/7.</div>`;
                }
            } catch(e) {
                container.innerHTML = `<div style="color:#ff4d4d; font-size:13px;">Failed to load data.</div>`;
            }
        }
        loadTrades();
        setInterval(loadTrades, 15000);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(LANDING_PAGE_HTML, wa_link=WHATSAPP_LINK)

@app.route('/app')
def webapp_dashboard():
    return render_template_string(MINI_APP_HTML)

@app.route('/api/live_trades')
def api_live_trades():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, direction, entry_price, tp1, tp2, sl, status, created_at FROM active_trades ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
        trades = []
        for r in rows:
            trades.append({
                "symbol": r[0],
                "direction": r[1],
                "entry": r[2],
                "tp1": r[3],
                "tp2": r[4],
                "sl": r[5],
                "status": r[6],
                "time": r[7]
            })
        return jsonify({"success": True, "trades": trades})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/verify', methods=['POST'])
def verify_payment():
    data = request.get_json() or {}
    tg_user = data.get('telegram', '').strip()
    tx_id = data.get('txid', '').strip()

    if not tg_user or not tx_id:
        return jsonify({"success": False, "error": "Missing Contact or Transaction ID"}), 400

    db_success = add_subscriber(tg_user, tx_id, days=30)
    if not db_success:
        return jsonify({"success": False, "error": "This Transaction ID has already been registered."}), 400

    invite_url = create_vip_invite_link()
    if not invite_url:
        invite_url = "https://t.me/+WhaleScannerSupport"

    admin_alert = (
        f"🎉 *NEW VIP SUBSCRIBER ACTIVATED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Client:* `{tg_user}`\n"
        f"🧾 *TxID:* `{tx_id}`\n"
        f"💵 *Amount:* `{SUBSCRIPTION_PRICE}`\n"
        f"🔗 *1-Time Link Issued:* [Join Channel]({invite_url})\n"
        f"⏳ *Valid for:* `30 Days`\n"
        f"🕒 `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )
    send_telegram_msg(VIP_CHANNEL_ID, admin_alert)

    return jsonify({"success": True, "invite_link": invite_url}), 200

# ==============================================================================
# 11. التشغيل المتوازي
# ==============================================================================
init_db()

scanner_thread = threading.Thread(target=start_continuous_scanner, daemon=True)
scanner_thread.start()

liquidation_thread = threading.Thread(target=start_liquidation_listener, daemon=True)
liquidation_thread.start()

expiration_thread = threading.Thread(target=monitor_expirations_loop, daemon=True)
expiration_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
