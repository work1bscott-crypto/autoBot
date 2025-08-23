#!/usr/bin/env python3
# app.py — Full Tapify main app (Telegram bot + WebApp + Crash betting + Tap game)
# Copy-paste this file to replace your original main code.
#
# Requirements:
#   pip install python-telegram-bot[telegram]==20.7 psycopg[binary] Flask python-dotenv requests
# Optional (for audio handling or other commented features):
#   pip install pydub
#
# Environment variables (examples):
#   BOT_TOKEN=your_bot_token
#   ADMIN_ID=123456789
#   GROUP_LINK=https://t.me/yourgroup
#   SITE_LINK=https://your-site.com
#   WEBAPP_URL=https://your-app.onrender.com/game
#   DATABASE_URL=postgres://user:pass@host:port/dbname
#   WEBAPP_SECRET=optional_secret_for_hmac
#   TELEGRAM_BOT_TOKEN= same as BOT_TOKEN (used for sending messages from server)
#   HOUSE_EDGE, GROWTH_RATE, MIN_BET, MAX_BET, MAX_CRASH optional tuning

import os
import math
import hmac
import hashlib
import random
import secrets
import logging
import datetime
from datetime import datetime as dt, timezone
from decimal import Decimal, ROUND_DOWN
from threading import Thread
from typing import Optional, Tuple

import psycopg
from psycopg.rows import dict_row
from flask import Flask, request, jsonify, render_template, redirect, url_for

import requests

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update,
    KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)

# ============================
# Basic config & logging
# ============================
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("tapify-main")

# ============================
# Environment variables (required)
# ============================
BOT_TOKEN    = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID     = int(os.getenv("ADMIN_ID", "0") or "0")
GROUP_LINK   = os.getenv("GROUP_LINK", "").strip()
SITE_LINK    = os.getenv("SITE_LINK", "").strip()
AI_BOOST_LINK= os.getenv("AI_BOOST_LINK", "").strip()
DAILY_TASK_LINK=os.getenv("DAILY_TASK_LINK", "").strip()
WEBAPP_URL   = os.getenv("WEBAPP_URL", "http://localhost:5000/game").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
WEBAPP_SECRET = os.getenv("WEBAPP_SECRET", "").strip()  # optional HMAC secret
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN).strip()  # used by notify_telegram

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required in environment")
if not ADMIN_ID:
    logger.warning("ADMIN_ID not set; admin commands will be restricted by ID check but ADMIN_ID is 0")

# Game tuning envs
HOUSE_EDGE = float(os.getenv("HOUSE_EDGE", "0.02"))  # 2% default
GROWTH_RATE = float(os.getenv("GROWTH_RATE", "0.16"))
MIN_BET = float(os.getenv("MIN_BET", "0.10"))
MAX_BET = float(os.getenv("MAX_BET", "1000"))
MAX_CRASH = float(os.getenv("MAX_CRASH", "100"))

# ============================
# Flask keepalive (for Render)
# ============================
flask_app = Flask("tapify-keepalive")

@flask_app.get("/")
def _root():
    return "Tapify backend — bot + webapp alive."

def run_flask():
    # Note: Render will run via gunicorn; this keeps dev mode simple
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)

# Start Flask thread in same process for dev convenience (for Render use gunicorn)
def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# ============================
# Database connection (psycopg)
# ============================
def pg_connect():
    url = DATABASE_URL
    # Ensure sslmode require if not provided (some platforms require)
    if "sslmode=" not in url.lower():
        url += ("&" if "?" in url else "?") + "sslmode=require"
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.autocommit = True
    return conn

conn = pg_connect()
cur = conn.cursor()

# ============================
# DB initialization (safe idempotent)
# ============================
def db_init():
    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id BIGINT PRIMARY KEY,
        package TEXT,
        payment_status TEXT DEFAULT 'new',
        name TEXT,
        username TEXT,
        email TEXT,
        phone TEXT,
        password TEXT,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        alarm_setting INTEGER DEFAULT 0,
        streaks INTEGER DEFAULT 0,
        invites INTEGER DEFAULT 0,
        balance REAL DEFAULT 0,
        screenshot_uploaded_at TIMESTAMP,
        approved_at TIMESTAMP,
        registration_date TIMESTAMP,
        referral_code TEXT,
        referred_by BIGINT
    )
    """)
    # payments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT,
        type TEXT,
        package TEXT,
        quantity INTEGER,
        total_amount INTEGER,
        payment_account TEXT,
        status TEXT DEFAULT 'pending_payment',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_at TIMESTAMP
    )
    """)
    # coupons
    cur.execute("""
    CREATE TABLE IF NOT EXISTS coupons (
        id SERIAL PRIMARY KEY,
        payment_id INTEGER,
        code TEXT,
        FOREIGN KEY (payment_id) REFERENCES payments(id)
    )
    """)
    # interactions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS interactions (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT,
        action TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # tasks & user_tasks
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        type TEXT,
        link TEXT,
        reward REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_tasks (
        user_id BIGINT,
        task_id INTEGER,
        completed_at TIMESTAMP,
        PRIMARY KEY (user_id, task_id),
        FOREIGN KEY (user_id) REFERENCES users(chat_id),
        FOREIGN KEY (task_id) REFERENCES tasks(id)
    )
    """)
    # Game sessions (crash betting)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS game_sessions (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT REFERENCES users(chat_id) ON DELETE CASCADE,
        bet_amount NUMERIC(12,2) NOT NULL,
        start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP,
        crash_point FLOAT NOT NULL,
        cashout_multiplier FLOAT,
        reward_amount NUMERIC(12,2) DEFAULT 0,
        status TEXT DEFAULT 'running'  -- running|won|lost
    )
    """)
    # optional: other tables from your previous app kept
    logger.info("DB init completed.")

db_init()

# ============================
# Helpers (existing app behavior preserved)
# ============================
def log_interaction(chat_id: int, action: str):
    try:
        cur.execute("INSERT INTO interactions (chat_id, action) VALUES (%s, %s)", (chat_id, action))
    except Exception as e:
        logger.warning("log_interaction failed: %s", e)

def get_user(chat_id: int) -> Optional[dict]:
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    return cur.fetchone()

def ensure_user(chat_id: int, username: Optional[str], referred_by: Optional[int]=None) -> dict:
    row = get_user(chat_id)
    if row:
        return row
    referral_code = secrets.token_urlsafe(6)
    cur.execute("""
        INSERT INTO users (chat_id, username, referral_code, referred_by)
        VALUES (%s, %s, %s, %s) RETURNING *
    """, (chat_id, username or "Unknown", referral_code, referred_by))
    return cur.fetchone()

def is_registered(chat_id: int) -> bool:
    cur.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
    row = cur.fetchone()
    return bool(row and row["payment_status"] == "registered")

def update_balance(chat_id: int, delta: float) -> float:
    cur.execute("UPDATE users SET balance = COALESCE(balance,0) + %s WHERE chat_id=%s RETURNING balance", (delta, chat_id))
    row = cur.fetchone()
    return float(row["balance"]) if row else 0.0

def set_reminder(chat_id: int, enabled: bool):
    cur.execute("UPDATE users SET alarm_setting=%s WHERE chat_id=%s", (1 if enabled else 0, chat_id))

def complete_task(user_id: int, task_id: int) -> Tuple[bool, float]:
    cur.execute("SELECT 1 FROM user_tasks WHERE user_id=%s AND task_id=%s", (user_id, task_id))
    if cur.fetchone():
        return False, float(get_user(user_id)["balance"])
    cur.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
    t = cur.fetchone()
    reward = float(t["reward"]) if t else 0.0
    cur.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, NOW())", (user_id, task_id))
    bal = update_balance(user_id, reward)
    return True, bal

def referral_bonus_if_any(new_user: dict):
    ref = new_user.get("referred_by")
    if not ref:
        return
    try:
        update_balance(ref, 100.0)  # configurable
    except Exception:
        pass

# ============================
# Keyboards / UI helpers
# ============================
def main_menu_kb(registered: bool) -> ReplyKeyboardMarkup:
    row1 = [KeyboardButton("📋 Tasks & Rewards"), KeyboardButton("🎮 Open Tapify")]
    row2 = [KeyboardButton("🎰 Bet Zone"), KeyboardButton("💰 Balance")]
    row3 = [KeyboardButton("❓ Help"), KeyboardButton("🛟 Support")]
    kb = [row1, row2, row3]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def webapp_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Open Tapify", web_app=WebAppInfo(WEBAPP_URL)),
         InlineKeyboardButton("🎰 Bet Zone", web_app=WebAppInfo(f"{WEBAPP_URL}?tab=bet"))],
        [InlineKeyboardButton("🌐 Site", url=SITE_LINK or "https://t.me/"),
         InlineKeyboardButton("👥 Group", url=GROUP_LINK or "https://t.me/")]
    ])

def tasks_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 AI Boost", url=AI_BOOST_LINK or "https://t.me/")],
        [InlineKeyboardButton("📅 Daily Task", url=DAILY_TASK_LINK or "https://t.me/")],
        [InlineKeyboardButton("🎁 Open WebApp", web_app=WebAppInfo(WEBAPP_URL))]
    ])

# Help topics preserved as before
FAQS = {
    "what_is_ethereal": {"question": "What is Tapify?", "answer": "Tapify is a platform where you earn money by completing tasks and games."},
    # ... keep others as needed
}
HELP_TOPICS = {
    "how_to_pay": {"label": "How to Pay", "type": "video", "url": "https://youtu.be/"},
    "register": {"label": "Registration Process", "type": "text", "text": (
        "1. /start → choose package\n2. Pay → upload screenshot\n3. Provide details\n4. Wait admin approval\n5. Join group and earn!"
    )},
    "daily_tasks": {"label": "Daily Tasks", "type": "video", "url": "https://youtu.be/"},
    "reminder": {"label": "Toggle Reminder", "type": "toggle"},
    "faq": {"label": "FAQs", "type": "faq"},
    "apply_coach": {"label": "Apply to become Coach", "type": "text", "text": "Contact admin to apply."},
}

def help_menu_kb(registered: bool):
    keyboard = [[InlineKeyboardButton(v["label"], callback_data=k)] for k,v in HELP_TOPICS.items()]
    if registered:
        keyboard.append([InlineKeyboardButton("👥 Refer a Friend", callback_data="refer_friend")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)

# ============================
# Game helpers (crash betting)
# ============================
def quant2(x: float) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

def sample_crash_point() -> float:
    u = random.random()
    if u < 0.85:
        x = 1.0 + (-math.log(1 - random.random())) * 1.2
    else:
        x = min(MAX_CRASH, 1.5 + (-math.log(1 - random.random())) * 5.0)
    return max(1.0, x)

def current_multiplier(start_time: datetime) -> float:
    t = (dt.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds()
    m = math.exp(GROWTH_RATE * max(0.0, t))
    return float(Decimal(m).quantize(Decimal("0.01"), rounding=ROUND_DOWN))

def verify_hmac(chat_id: str, token: str) -> bool:
    if not WEBAPP_SECRET:
        return True
    if not token:
        return False
    mac = hmac.new(WEBAPP_SECRET.encode(), msg=str(chat_id).encode(), digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, token)

def notify_telegram(chat_id: int, text: str):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
    except Exception:
        logger.exception("notify_telegram failed")

# ============================
# Telegram Bot Handlers (preserve original flows)
# ============================
WELCOME_TEXT = (
    "👋 *Welcome to Tapify!*\n\n"
    "Earn by completing daily tasks, inviting friends, and playing Tapify games.\n"
    "Complete registration to access the Tapify WebApp (games + tasks hub)."
)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    args = context.args or []

    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0].split("_", 1)[1])
        except Exception:
            referred_by = None

    row = ensure_user(chat.id, user.username, referred_by)
    log_interaction(chat.id, "start")

    text = WELCOME_TEXT
    if is_registered(chat.id):
        text += "\n\n✅ *Registration status:* Registered — you can play the game!"
    else:
        text += "\n\n⚠️ *Registration status:* Not registered yet."

    await update.message.reply_text(text, reply_markup=main_menu_kb(is_registered(chat.id)), parse_mode="Markdown")
    await update.message.reply_text("Quick Access:", reply_markup=webapp_buttons())

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("Main Menu:", reply_markup=main_menu_kb(is_registered(chat_id)))

async def open_game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_registered(chat_id):
        await update.message.reply_text("🚫 You must be registered to open the Tapify WebApp.")
        return
    await update.message.reply_text("Open Tapify:", reply_markup=webapp_buttons())

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cur.execute("SELECT COUNT(*) AS c FROM users")
    total = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE payment_status='registered'")
    regs = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(balance),0) AS s FROM users")
    sumbal = float(cur.fetchone()["s"])
    await update.message.reply_text(f"👥 Users: {total}\n✅ Registered: {regs}\n💰 Total Balances: {sumbal:,.2f}")

async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🛟 Support: @bigscottmedia\nGroup: {GROUP_LINK or 'https://t.me/'}")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = " ".join(context.args).strip()
    if not msg:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    cur.execute("SELECT chat_id FROM users")
    sent = 0
    for row in cur.fetchall():
        try:
            await context.bot.send_message(chat_id=row["chat_id"], text=msg)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"Broadcast sent to {sent} users.")

async def add_task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        _type = context.args[0]; reward = float(context.args[1]); link = " ".join(context.args[2:])
    except Exception:
        await update.message.reply_text("Usage: /add_task <type> <reward> <link>")
        return
    cur.execute("INSERT INTO tasks (type, link, reward) VALUES (%s, %s, %s)", (_type, link, reward))
    await update.message.reply_text("Task added.")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_user(update.effective_chat.id)
    bal = float(row["balance"]) if row else 0.0
    await update.message.reply_text(f"💰 Your balance: *{bal:,.2f}* coins", parse_mode="Markdown")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = (update.callback_query.from_user.id if update.callback_query else update.effective_chat.id)
    text = "Choose an option below:"
    kb = main_menu_kb(is_registered(chat_id))
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=None)
        await context.bot.send_message(chat_id, text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)
    log_interaction(chat_id, "show_main_menu")

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.callback_query.from_user.id
    keyboard = help_menu_kb(is_registered(chat_id))
    await update.callback_query.edit_message_text("What would you like help with?", reply_markup=keyboard)
    log_interaction(chat_id, "help_menu")

# Callback handler for help/referral buttons etc.
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.from_user.id
    data = query.data
    log_interaction(chat_id, f"cb:{data}")

    if data == "menu":
        await show_main_menu(update, context)
        return

    if data == "refer_friend":
        row = get_user(chat_id)
        ref_code = row["referral_code"] if row else secrets.token_urlsafe(6)
        me = await context.bot.get_me()
        deep_link = f"https://t.me/{me.username}?start=ref_{chat_id}"
        await query.edit_message_text(f"👥 Your referral link:\n{deep_link}\nShare to earn bonuses!",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
        return

    if data in HELP_TOPICS:
        topic = HELP_TOPICS[data]
        if topic["type"] == "text":
            await query.edit_message_text(topic["text"], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
        elif topic["type"] == "faq":
            txt = "\n\n".join([f"*{f['question']}*\n{f['answer']}" for f in FAQS.values()])
            await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
        elif topic["type"] == "toggle":
            row = get_user(chat_id)
            now = 0 if (row and row["alarm_setting"]) else 1
            set_reminder(chat_id, bool(now))
            await query.edit_message_text(f"⏰ Reminder is now {'ON' if now else 'OFF'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
        elif topic["type"] == "video":
            await query.edit_message_text(f"🎬 Video guide: {topic['url']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
        return

# Text message handler (keyboard)
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id
    log_interaction(chat_id, f"text:{text}")

    if text == "📋 Tasks & Rewards":
        await update.message.reply_text("Open tasks and start earning 👇", reply_markup=tasks_buttons())
        return

    if text == "🎮 Open Tapify":
        if not is_registered(chat_id):
            await update.message.reply_text("🚫 You must complete registration to open the Tapify WebApp.")
            return
        await update.message.reply_text("Open Tapify…", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Open Tapify", web_app=WebAppInfo(WEBAPP_URL))]]))
        return

    if text == "🎰 Bet Zone":
        if not is_registered(chat_id):
            await update.message.reply_text("🚫 You must complete registration to access Bet Zone.")
            return
        await update.message.reply_text("Open Bet Zone…", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎰 Bet Zone", web_app=WebAppInfo(f'{WEBAPP_URL}?tab=bet'))]]))
        return

    if text == "💰 Balance":
        await balance_cmd(update, context)
        return

    if text == "❓ Help":
        await update.message.reply_text("What do you need help with?", reply_markup=help_menu_kb(is_registered(chat_id)))
        return

    if text == "🛟 Support":
        await support_cmd(update, context)
        return

    await update.message.reply_text("Use the menu below to navigate.", reply_markup=main_menu_kb(is_registered(chat_id)))

# Photo/document handlers for payment proofs
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    photos = update.message.photo
    if not photos:
        return
    cur.execute("UPDATE users SET screenshot_uploaded_at=NOW() WHERE chat_id=%s", (chat_id,))
    await update.message.reply_text("✅ Payment screenshot received. Admin will verify shortly.")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cur.execute("UPDATE users SET screenshot_uploaded_at=NOW() WHERE chat_id=%s", (chat_id,))
    await update.message.reply_text("✅ Document received. Admin will review.")

# Admin approve
async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target = int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: /approve <chat_id>")
        return
    cur.execute("UPDATE users SET payment_status='registered', approved_at=NOW(), registration_date=NOW() WHERE chat_id=%s RETURNING *", (target,))
    row = cur.fetchone()
    if row:
        referral_bonus_if_any(row)
        await update.message.reply_text(f"✅ User {target} approved.")
        try:
            await context.bot.send_message(target, "🎉 Your registration has been approved! You can now play Tapify.")
        except Exception:
            pass
    else:
        await update.message.reply_text("User not found.")

# Admin: reset interactions older than n days
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cur.execute("DELETE FROM interactions WHERE timestamp < NOW() - INTERVAL '90 days'")
    await update.message.reply_text("Old interactions trimmed.")

# Daily jobs
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    try:
        cur.execute("SELECT chat_id FROM users WHERE alarm_setting=1")
        for row in cur.fetchall():
            try:
                await context.bot.send_message(row["chat_id"], "⏰ Daily reminder: complete your tasks and claim rewards!")
            except Exception:
                pass
    except Exception as e:
        logger.exception("daily_reminder error")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    try:
        cur.execute("SELECT COUNT(*) AS c FROM interactions WHERE timestamp::date=NOW()::date")
        inter = cur.fetchone()["c"]
        await context.bot.send_message(ADMIN_ID, f"📊 Daily summary: {inter} interactions today.")
    except Exception:
        pass

# ============================
# WebApp routes (Flask) served by same app
# ============================
# Note: We run Flask separately (Render/gunicorn will handle in production).
# The routes below are rendered by Flask, but are included in this file for easy deploy.

@flask_app.route("/game")
def web_game():
    chat_id = request.args.get("chat_id", type=str)
    token = request.args.get("t", type=str, default="")
    # optional tab param to switch to bet tab
    tab = request.args.get("tab", default="")
    # Only allow registered users (server-side check for extra safety)
    if not chat_id or not chat_id.isdigit():
        return "Missing chat_id", 400
    if not verify_hmac(chat_id, token):
        return "Unauthorized", 401
    # Fetch user from DB
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (int(chat_id),))
    user = cur.fetchone()
    if not user:
        # auto-provision user row (but not registered)
        cur.execute("INSERT INTO users (chat_id, username, balance) VALUES (%s,%s,%s) RETURNING *",
                    (int(chat_id), None, 0.0))
        user = cur.fetchone()
    # enforce registration if you prefer to block access entirely:
    # if user["payment_status"] != "registered":
    #     return "You must be registered to access the webapp.", 403

    # Render the unified game UI (Tap + Bet) in templates/game.html
    # Provide balance and tuning params
    return render_template("game.html",
                           chat_id=str(chat_id),
                           token=token,
                           app_name=os.getenv("APP_NAME", "Tapify"),
                           min_bet=MIN_BET, max_bet=MAX_BET,
                           balance=float(user.get("balance", 0.0)),
                           tab=tab)

# API: tap reward endpoint (Tap game)
@flask_app.route("/api/tap", methods=["POST"])
def api_tap():
    data = request.get_json(force=True, silent=True) or {}
    chat_id = str(data.get("chat_id", ""))
    token = str(data.get("token", ""))
    # simple anti-cheat: require chat_id numeric + hmac
    if not chat_id.isdigit():
        return jsonify(ok=False, error="Invalid chat_id"), 400
    if not verify_hmac(chat_id, token):
        return jsonify(ok=False, error="Unauthorized"), 401
    # reward small amount for tapping every N taps (client triggers after N)
    reward = float(os.getenv("TAP_REWARD", "0.01"))
    new_bal = update_balance(int(chat_id), reward)
    return jsonify(ok=True, balance=f"{new_bal:.2f}")

# API: start betting session
@flask_app.route("/api/game/start", methods=["POST"])
def api_game_start():
    data = request.get_json(force=True, silent=True) or {}
    chat_id = str(data.get("chat_id", ""))
    token = str(data.get("token", ""))
    bet = float(data.get("bet", 0) or 0)
    if not chat_id.isdigit():
        return jsonify(ok=False, error="Invalid chat_id"), 400
    if not verify_hmac(chat_id, token):
        return jsonify(ok=False, error="Unauthorized"), 401
    # check user and balance
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (int(chat_id),))
    user = cur.fetchone()
    if not user:
        return jsonify(ok=False, error="User not found"), 404
    if bet < MIN_BET or bet > MAX_BET:
        return jsonify(ok=False, error=f"Bet must be between {MIN_BET} and {MAX_BET}"), 400
    if float(user["balance"]) < bet:
        return jsonify(ok=False, error="Insufficient balance"), 400
    # Deduct bet immediately (hold with house)
    cur.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s RETURNING balance", (bet, int(chat_id)))
    cur.fetchone()  # discard
    # create session
    crash_point = sample_crash_point()
    cur.execute("""
        INSERT INTO game_sessions (chat_id, bet_amount, crash_point, status, start_time)
        VALUES (%s, %s, %s, %s, NOW()) RETURNING id, start_time
    """, (int(chat_id), float(Decimal(str(bet)).quantize(Decimal("0.01"))), float(crash_point), 'running'))
    row = cur.fetchone()
    session_id = row["id"]
    started_at = row["start_time"].isoformat()
    return jsonify(ok=True, session_id=session_id, started_at=started_at)

# API: cashout (user attempts to cash out)
@flask_app.route("/api/game/cashout", methods=["POST"])
def api_game_cashout():
    data = request.get_json(force=True, silent=True) or {}
    chat_id = str(data.get("chat_id", ""))
    token = str(data.get("token", ""))
    session_id = int(data.get("session_id", 0) or 0)
    if not chat_id.isdigit():
        return jsonify(ok=False, error="Invalid chat_id"), 400
    if not verify_hmac(chat_id, token):
        return jsonify(ok=False, error="Unauthorized"), 401
    # fetch session
    cur.execute("SELECT * FROM game_sessions WHERE id=%s", (session_id,))
    session = cur.fetchone()
    if not session or session["chat_id"] != int(chat_id):
        return jsonify(ok=False, error="Session not found"), 404
    if session["status"] != "running":
        return jsonify(ok=False, error=f"Session already {session['status']}"), 400
    # compute current multiplier
    start_time = session["start_time"]
    m = current_multiplier(start_time)
    crash_m = float(session["crash_point"])
    # fetch latest user balance
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (int(chat_id),))
    user = cur.fetchone()
    if m < crash_m:
        # user wins
        bet_amount = float(session["bet_amount"])
        gross_return = bet_amount * m
        profit = max(0.0, gross_return - bet_amount)
        profit_after_edge = profit * (1.0 - HOUSE_EDGE)
        payout = bet_amount + profit_after_edge
        payout_q = float(Decimal(payout).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        # credit payout
        cur.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s RETURNING balance", (payout_q, int(chat_id)))
        balrow = cur.fetchone()
        new_bal = float(balrow["balance"]) if balrow else 0.0
        # update session
        cur.execute("UPDATE game_sessions SET cashout_multiplier=%s, reward_amount=%s, status='won', finished_at=NOW() WHERE id=%s",
                    (float(Decimal(m).quantize(Decimal("0.01"), rounding=ROUND_DOWN)), payout_q, session_id))
        notify_telegram(int(chat_id), f"🎉 Tapify: You cashed out at {m:.2f}x!\nPayout: {payout_q}\nBalance: {new_bal:.2f}")
        return jsonify(ok=True, result="won", multiplier=round(m,2), payout=f"{payout_q:.2f}", balance=f"{new_bal:.2f}")
    else:
        # crashed already; user loses (bet already deducted)
        cur.execute("UPDATE game_sessions SET status='lost', finished_at=NOW() WHERE id=%s", (session_id,))
        # fetch current balance
        cur.execute("SELECT balance FROM users WHERE chat_id=%s", (int(chat_id),))
        balrow = cur.fetchone()
        new_bal = float(balrow["balance"]) if balrow else 0.0
        notify_telegram(int(chat_id), f"💥 Tapify: Round crashed at {crash_m:.2f}x. You lost your bet.\nBalance: {new_bal:.2f}")
        return jsonify(ok=True, result="lost", crashed_at=round(crash_m,2), balance=f"{new_bal:.2f}")

# API: status (client polls)
@flask_app.route("/api/game/status", methods=["GET"])
def api_game_status():
    chat_id = request.args.get("chat_id", type=str, default="")
    token = request.args.get("t", type=str, default="")
    session_id = request.args.get("session_id", type=int, default=0)
    if not chat_id.isdigit():
        return jsonify(ok=False, error="Invalid chat_id"), 400
    if not verify_hmac(chat_id, token):
        return jsonify(ok=False, error="Unauthorized"), 401
    cur.execute("SELECT * FROM game_sessions WHERE id=%s", (session_id,))
    session = cur.fetchone()
    if not session:
        return jsonify(ok=False, error="No session"), 404
    m = current_multiplier(session["start_time"])
    crashed = (m >= float(session["crash_point"])) or session["status"] in ("won", "lost")
    # return crash_point in case client needs to show final
    return jsonify(ok=True, multiplier=round(m,2), crashed=crashed, status=session["status"], crash_point=round(float(session["crash_point"]),2))

# ============================
# Bot boot
# ============================
def main():
    keep_alive()  # start flask thread in dev mode; in production Render handles Flask/gunicorn
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers (commands)
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("menu", menu_cmd))
    application.add_handler(CommandHandler("game", open_game_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("support", support_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CommandHandler("add_task", add_task_cmd))
    application.add_handler(CommandHandler("balance", balance_cmd))
    application.add_handler(CommandHandler("approve", approve_cmd))
    application.add_handler(CommandHandler("reset", reset_cmd))

    # Callback & message handlers
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Jobs (daily)
    try:
        application.job_queue.run_daily(daily_reminder, time=datetime.time(hour=8, minute=0))
        application.job_queue.run_daily(daily_summary, time=datetime.time(hour=20, minute=0))
    except Exception:
        logger.warning("Could not schedule daily jobs (timezones?)")

    logger.info("Bot started.")
    application.run_polling()

if __name__ == "__main__":
    main()

# ============================
# End of file
# ============================
