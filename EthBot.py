#!/usr/bin/env python3
# main.py — Tapify Main Bot for Telegram
# Requirements:
#   pip install python-telegram-bot==20.7 psycopg[binary] python-dotenv flask pydub uvicorn psycopg_pool
#
# Environment (.env):
#   BOT_TOKEN=your_bot_token
#   ADMIN_ID=your_admin_id
#   GROUP_LINK=your_group_link
#   SITE_LINK=your_site_link
#   AI_BOOST_LINK=your_ai_boost_link
#   DAILY_TASK_LINK=your_daily_task_link
#   DATABASE_URL=postgres://user:pass@host:port/dbname
#   WEBHOOK_URL=https://ethbot-czhg.onrender.com/
#   WEBAPP_BASE=https://ethbot-czhg.onrender.com
#   PORT=8080
#
# Start:
#   python main.py

import asyncio
import logging
import psycopg
import re
import time
import datetime
import os
import secrets
import math
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from pydub import AudioSegment
from flask import Flask, request, jsonify
from psycopg_pool import AsyncConnectionPool

# Flask setup for Render keep-alive and APIs
app = Flask(__name__)

# Bot credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
GROUP_LINK = os.getenv("GROUP_LINK", "")
SITE_LINK = os.getenv("SITE_LINK", "")
AI_BOOST_LINK = os.getenv("AI_BOOST_LINK", "")
DAILY_TASK_LINK = os.getenv("DAILY_TASK_LINK", "")
WEBAPP_BASE = os.getenv("WEBAPP_BASE", "https://ethbot-czhg.onrender.com")
WEBAPP_URL = f"{WEBAPP_BASE}/tap"
AVIATOR_URL = f"{WEBAPP_BASE}/aviator"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

# Validate environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required in environment (.env)")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID is required in environment (.env)")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is required in environment (.env)")
if not WEBAPP_BASE:
    raise ValueError("WEBAPP_BASE is required in environment (.env)")

# Predefined payment accounts
PAYMENT_ACCOUNTS = {
    "Nigeria (Opay)": "🇳🇬 Account: 6110749592\nBank: Kuda Bank\nName: Chike Eluem Olanrewaju",
    "Nigeria (Zenith)": "🇳🇬 Account: 2267515466\nBank: Zenith Bank\nName: Chike Eluem Olanrewaju",
    "Nigeria (Kuda)": "🇳🇬 Account: 2036035854\nBank: OPay\nName: Eluem, Chike Olanrewaju",
}

# Predefined coupon payment accounts
COUPON_PAYMENT_ACCOUNTS = {
    "Coupon Acct 1 (Opay)": "🇳🇬 Account: 6110749592\nBank: Kuda Bank\nName: Chike Eluem Olanrewaju",
    "Coupon Acct 2 (Zenith)": "🇳🇬 Account: 2267515466\nBank: Zenith Bank\nName: Chike Eluem Olanrewaju",
    "Coupon Acct 3 (Kuda)": "🇳🇬 Account: 2036035854\nBank: OPay\nName: Eluem, Chike Olanrewaju"
}

# Predefined FAQs
FAQS = {
    "what_is_ethereal": {
        "question": "What is Tapify?",
        "answer": "Tapify is a platform where you earn money by completing tasks like taking a walk, reading posts, playing games, sending Snapchat streaks, and inviting friends."
    },
    "payment_methods": {
        "question": "What payment methods are available?",
        "answer": "Payments can be made via bank transfer, mobile money, PayPal or Zelle for foreign accounts. Check the 'How to Pay' guide in the Help menu."
    },
    "task_rewards": {
        "question": "How are task rewards calculated?",
        "answer": "Rewards vary by task type. For example, reading posts earns $2.5 per 10 words, Candy Crush tasks earn $5 daily, and Snapchat streaks can earn up to $20."
    }
}

# Help topics
HELP_TOPICS = {
    "how_to_pay": {"label": "How to Pay", "type": "video", "url": "https://youtu.be/ (will be available soon)"},
    "register": {"label": "Registration Process", "type": "text", "text": (
        "1. /start → choose package\n"
        "2. Pay via your selected account → upload screenshot\n"
        "3. Provide your details (name, email, phone, Telegram username)\n"
        "4. Wait for admin approval\n"
        "5. Join the group and start earning! 🎉"
    )},
    "daily_tasks": {"label": "Daily Tasks", "type": "video", "url": "https://youtu.be/ (will be available soon)"},
    "reminder": {"label": "Toggle Reminder", "type": "toggle"},
    "faq": {"label": "FAQs", "type": "faq"},
    "apply_coach": {"label": "Apply to become Coach", "type": "text", "text": (
        "Please contact the Admin @bigscottmedia to discuss your application process"
    )},
    "password_recovery": {"label": "Password Recovery", "type": "input", "text": "Please provide your registered email to request password recovery:"},
}

# Convert mp3 to ogg (Opus)
#try:
#    sound = AudioSegment.from_mp3("voice.mp3")
#    sound.export("voice.ogg", format="ogg", codec="libopus")
#except FileNotFoundError:
#    logging.warning("voice.mp3 not found; voice note feature may fail")#

# Database setup
conn_pool = None

async def setup_db():
    global conn_pool
    import urllib.parse as urlparse

    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL must be set for PostgreSQL")
    if "sslmode=" not in url:
        if "?" in url:
            url += "&sslmode=require"
        else:
            url += "?sslmode=require"
    conn_pool = AsyncConnectionPool(url, open=False)
    await conn_pool.open()
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            # Users table
            await cursor.execute("""
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
            # Payments table
            await cursor.execute("""
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
            # Coupons table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS coupons (
                    id SERIAL PRIMARY KEY,
                    payment_id INTEGER,
                    code TEXT,
                    FOREIGN KEY (payment_id) REFERENCES payments(id)
                )
            """)
            # Interactions table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT,
                    action TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Tasks table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    type TEXT,
                    link TEXT,
                    reward REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            # User_tasks table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_tasks (
                    user_id BIGINT,
                    task_id INTEGER,
                    completed_at TIMESTAMP,
                    PRIMARY KEY (user_id, task_id),
                    FOREIGN KEY (user_id) REFERENCES users(chat_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            # Aviator tables
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS aviator_rounds (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    seed TEXT NOT NULL,
                    crash_point DOUBLE PRECISION NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'active' -- active|crashed|cashed
                )
            """)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS aviator_plays (
                    id BIGSERIAL PRIMARY KEY,
                    round_id BIGINT REFERENCES aviator_rounds(id),
                    chat_id BIGINT NOT NULL,
                    bet_amount DOUBLE PRECISION NOT NULL,
                    cashout_multiplier DOUBLE PRECISION,
                    payout DOUBLE PRECISION,
                    outcome TEXT, -- win|lose|none
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_aviator_rounds_chat ON aviator_rounds(chat_id);")
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_aviator_plays_round ON aviator_plays(round_id);")
            await conn.commit()

# In-memory storage
user_state = {}
start_time = time.time()

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper functions
async def get_status(chat_id):
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
            row = await cursor.fetchone()
            return row["payment_status"] if row else None

async def is_registered(chat_id):
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
            row = await cursor.fetchone()
            return row and row["payment_status"] == 'registered'

async def log_interaction(chat_id, action):
    async with conn_pool.connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("INSERT INTO interactions (chat_id, action) VALUES (%s, %s)", (chat_id, action))
            await conn.commit()

def generate_referral_code():
    return secrets.token_urlsafe(6)

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    referral_code = generate_referral_code()
    args = context.args
    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0].split("_")[1])
        except (IndexError, ValueError):
            pass
    await log_interaction(chat_id, "start")
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
            if not await cursor.fetchone():
                await cursor.execute(
                    "INSERT INTO users (chat_id, username, referral_code, referred_by) VALUES (%s, %s, %s, %s)",
                    (chat_id, update.effective_user.username or "Unknown", referral_code, referred_by)
                )
                if referred_by:
                    await cursor.execute("UPDATE users SET invites = invites + 1, balance = balance + 0.1 WHERE chat_id=%s", (referred_by,))
                await conn.commit()
    keyboard = [[InlineKeyboardButton("🚀 Get Started", callback_data="menu")]]
    await update.message.reply_text(
        "Welcome to Tapify!\n\nGet paid for using your phone and doing what you love most.\n"
        "• Read posts ➜ earn $2.5/10 words\n• Take a Walk ➜ earn $5\n"
        "• Send Snapchat streaks ➜ earn up to $20\n• Invite friends and more!\n\n"
        "Choose your package and start earning today.\nClick below to get started.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    reply_keyboard = [["/menu(🔙)"]]
    if await is_registered(chat_id):
        reply_keyboard.append([KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=f"{WEBAPP_URL}?chat_id={chat_id}"))])
        reply_keyboard.append([KeyboardButton(text="Play Aviator", web_app=WebAppInfo(url=f"{AVIATOR_URL}?chat_id={chat_id}"))])
    await update.message.reply_text(
        "Use the button's below to access the main menu and Tapify Games:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )

async def cmd_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if not await is_registered(chat_id):
        await update.message.reply_text("Please complete registration to play the game.")
        return
    kb = [[KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "Tap to earn coins!",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {'expecting': 'support_message', 'timestamp': time.time()}
    await update.message.reply_text("Please describe your issue or question:")
    await log_interaction(chat_id, "support_initiated")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await log_interaction(chat_id, "stats")
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT payment_status, streaks, invites, package, balance FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            if not user:
                if update.callback_query:
                    await update.callback_query.answer("No user data found. Please start with /start.")
                else:
                    await update.message.reply_text("No user data found. Please start with /start.")
                return
            payment_status, streaks, invites, package, balance = user.values()
            text = (
                "📊 Your Platform Stats:\n\n"
                f"• Package: {package or 'Not selected'}\n"
                f"• Payment Status: {payment_status.capitalize()}\n"
                f"• Streaks: {streaks}\n"
                f"• Invites: {invites}\n"
                f"• Balance: ${balance:.2f}"
            )
            if balance >= 30:
                keyboard = [[InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]]
            else:
                keyboard = []
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_state:
        del user_state[chat_id]
    await update.message.reply_text("State reset. Try the flow again.")
    await log_interaction(chat_id, "reset_state")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("This command is restricted to the admin.")
        return
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Usage: /add_task <type> <link> <reward>")
        return
    task_type, link, reward = args
    try:
        reward = float(reward)
    except ValueError:
        await update.message.reply_text("Reward must be a number.")
        return
    created_at = datetime.datetime.now()
    expires_at = created_at + datetime.timedelta(days=1)
    async with conn_pool.connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO tasks (type, link, reward, created_at, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (task_type, link, reward, created_at, expires_at)
            )
            await conn.commit()
    await update.message.reply_text("Task added successfully.")
    await log_interaction(chat_id, "add_task")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("This command is restricted to the admin.")
        return
    user_state[chat_id] = {'expecting': 'broadcast_message', 'timestamp': time.time()}
    await update.message.reply_text("Please enter the broadcast message to send to all registered users:")
    await log_interaction(chat_id, "broadcast_initiated")

# Callback handlers
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = query.from_user.id
    logger.info(f"Received callback data: {data} from chat_id: {chat_id}")
    await query.answer()
    await log_interaction(chat_id, f"button_{data}")

    if data == "menu":
        if chat_id in user_state:
            del user_state[chat_id]
        await show_main_menu(update, context)
    elif data == "stats":
        await stats(update, context)
    elif data == "refer_friend":
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT referral_code FROM users WHERE chat_id=%s", (chat_id,))
                referral_code = (await cursor.fetchone())["referral_code"]
        referral_link = f"https://t.me/{context.bot.username}?start=ref_{chat_id}"
        text = (
            "👥 Refer a Friend and Earn Rewards!\n\n"
            "Share your referral link with friends. For each friend who joins using your link, you earn $0.1. "
            "If they register, you earn an additional $0.4 for Standard or $0.9 for X package.\n\n"
            f"Your referral link: {referral_link}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))
    elif data == "withdraw":
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
                balance = (await cursor.fetchone())["balance"]
        if balance < 30:
            await query.answer("Your balance is less than $30.")
            return
        await context.bot.send_message(
            ADMIN_ID,
            f"Withdrawal request from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})\n"
            f"Amount: ${balance}"
        )
        await query.edit_message_text(
            "Your withdrawal request has been sent to the admin. Please wait for processing.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
        )
    elif data == "how_it_works":
        keyboard = [
            [InlineKeyboardButton("💎TAP MEEE!!!!", callback_data="package_selector")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
        ]
        await query.edit_message_text(
            "🟡 HOW TAPIFY💥 WORKS\n"
            "Tapify rewards you for your everyday online actions — walking, gaming, sending snaps, joining forums, and social engagement.\n"
            "— — —\n"
            "📍 TAPIFY STANDARD PACKAGE — ₦10,000\n"
            "• 🎉 Starter Reward: ₦8,000 Newbie Bonus\n"
            "• 🛜 Free Data: 5GB on your preferred network\n"
            "• 🪙 Tap Coins: Instant $10 reward\n"
            "• 💰 Revenue Share: ₦9,000 per direct recruit\n"
            "• 🔁 Indirect Earnings: ₦250 (1st level) – ₦100 (2nd level)\n"
            "• 🧾 Forum Earnings: ₦200 per 10 words\n"
            "• 🎥 Snapchat/TikTok Streaks: $10 per streak\n"
            "• 🚶‍♂ Steps: ₦10 per 100 steps\n"
            "• 🏍 Rider Earnings: ₦20 per delivery\n"
            "• 📖 Reading Tasks: ₦0.2 per novel read\n\n"
            "• 🎙 Recording Tasks: ₦0.2 per audio\n"
            "• 📤 Approved Topics & Social Links: ₦5 each\n"
            "• 🎮 Tapify Games: ₦20 per session\n"
            "• 🧑‍🤝‍🧑 Unlimited Team Earnings: Passive income from your team\n"
            "• 🏦 Student Loans: No collateral required\n"
            "• 💳 Automated Withdrawals: Weekly payouts\n"
            "• Up to ₦5,000 daily from Candy Crush\n"
            "• Earn up to $50 sending Snapchat streaks\n"
            "• Daily passive income from your team + your earnings (₦10,000 daily)\n"
            "• 📺 Subscription Bonuses: Free access to GOtv, DStv & Netflix\n"
            "— — —\n\n"
            " Ensure to listen to the Voice Note below to understand more about our features...",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        voice_keyboard = [
            [InlineKeyboardButton("✅ I've listened...", callback_data="close_voice")]
        ]
        voice_markup = InlineKeyboardMarkup(voice_keyboard)
        try:
            with open("voice.ogg", "rb") as voice:
                await context.bot.send_voice(
                    chat_id=query.message.chat_id,
                    voice=voice,
                    caption="Tapify Explained 🎧",
                    reply_markup=voice_markup
                )
        except FileNotFoundError:
            logger.error("Voice file 'voice.ogg' not found")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Voice note not available. Please check the text explanation above.",
                reply_markup=voice_markup
            )
    elif data == "close_voice":
        await query.message.delete()
    elif data == "coupon":
        user_state[chat_id] = {'expecting': 'coupon_quantity', 'timestamp': time.time()}
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
        await query.edit_message_text(
            "How many coupons do you want to purchase?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "coupon_standard":
        package = "Standard"
        price = 10000
        quantity = user_state[chat_id]['coupon_quantity']
        total = quantity * price
        user_state[chat_id].update({'coupon_package': package, 'coupon_total': total})

        await context.bot.send_message(
            ADMIN_ID,
            f"User @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}) "
            f"wants to purchase {quantity} {package} coupons for ₦{total}."
        )

        keyboard = [[InlineKeyboardButton(a, callback_data=f"coupon_account_{a}")] for a in COUPON_PAYMENT_ACCOUNTS.keys()]
        keyboard.append([InlineKeyboardButton("Other country option", callback_data="coupon_other")])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])

        await query.edit_message_text(
            f"You are purchasing {quantity} {package} coupons.\nTotal amount: ₦{total}\n\nSelect the account to pay to:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("coupon_account_"):
        account = data[len("coupon_account_"):]
        payment_details = COUPON_PAYMENT_ACCOUNTS.get(account)
        if not payment_details:
            await context.bot.send_message(chat_id, "Error: Invalid account. Contact @bigscottmedia.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
            return
        user_state[chat_id]['selected_account'] = account
        user_state[chat_id]['expecting'] = 'coupon_screenshot'
        package = user_state[chat_id]['coupon_package']
        quantity = user_state[chat_id]['coupon_quantity']
        total = user_state[chat_id]['coupon_total']
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute(
                    "INSERT INTO payments (chat_id, type, package, quantity, total_amount, payment_account, status) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (chat_id, 'coupon', package, quantity, total, account, 'pending_payment')
                )
                payment_id = (await cursor.fetchone())["id"]
                await conn.commit()
        user_state[chat_id]['waiting_approval'] = {'type': 'coupon', 'payment_id': payment_id}
        keyboard = [
            [InlineKeyboardButton("Change Account", callback_data="show_coupon_account_selection")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
        ]
        await context.bot.send_message(
            chat_id,
            f"Payment details:\n\n{payment_details}\n\nPlease make the payment and send the screenshot.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "show_coupon_account_selection":
        keyboard = [[InlineKeyboardButton(a, callback_data=f"coupon_account_{a}")] for a in COUPON_PAYMENT_ACCOUNTS.keys()]
        keyboard.append([InlineKeyboardButton("Other country option", callback_data="coupon_other")])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
        await query.edit_message_text("Select an account to pay to:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "coupon_other":
        await context.bot.send_message(
            chat_id,
            "Please contact @bigscottmedia to complete your payment for other region coupon purchase.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
        )
    elif data == "package_selector":
        status = await get_status(chat_id)
        if status == 'registered':
            await context.bot.send_message(chat_id, "You are already registered.")
            return
        keyboard = [
            [InlineKeyboardButton("✈️Standard (₦10,000)", callback_data="reg_standard")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
        ]
        await query.edit_message_text("Choose your package:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data in ["reg_standard", "reg_x"]:
        package = "Standard" if data == "reg_standard" else "X"
        user_state[chat_id] = {'package': package, 'timestamp': time.time()}
        async with conn_pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("UPDATE users SET package=%s, payment_status='pending_payment' WHERE chat_id=%s", (package, chat_id))
                if cursor.rowcount == 0:
                    await cursor.execute("INSERT INTO users (chat_id, package, payment_status, username) VALUES (%s, %s, 'pending_payment', %s)", (chat_id, package, update.effective_user.username or "Unknown"))
                await conn.commit()
        keyboard = [[InlineKeyboardButton(a, callback_data=f"reg_account_{a}")] for a in PAYMENT_ACCOUNTS.keys()]
        keyboard.append([InlineKeyboardButton("Other country option", callback_data="reg_other")])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
        await query.edit_message_text("Select an account to pay to:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("reg_account_"):
        account = data[len("reg_account_"):]
        payment_details = PAYMENT_ACCOUNTS.get(account)
        if not payment_details:
            await context.bot.send_message(chat_id, "Error: Invalid account. Contact @bigscottmedia.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
            return
        user_state[chat_id]['selected_account'] = account
        user_state[chat_id]['expecting'] = 'reg_screenshot'
        keyboard = [
            [InlineKeyboardButton("Change Account", callback_data="show_account_selection")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
        ]
        await context.bot.send_message(
            chat_id,
            f"Payment details:\n\n{payment_details}\n\nPlease make the payment and send the screenshot.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "show_account_selection":
        package = user_state[chat_id].get('package', '')
        if not package:
            await query.edit_message_text("Please select a package first.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
            return
        keyboard = [[InlineKeyboardButton(a, callback_data=f"reg_account_{a}")] for a in PAYMENT_ACCOUNTS.keys()]
        keyboard.append([InlineKeyboardButton("Other country option", callback_data="reg_other")])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
        await query.edit_message_text("Select an account to pay to:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "reg_other":
        await context.bot.send_message(
            chat_id,
            "Please contact @bigscottmedia to complete your payment for other region registration.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
        )
    elif data.startswith("approve_"):
        parts = data.split("_")
        if parts[1] == "reg":
            user_chat_id = int(parts[2])
            async with conn_pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("UPDATE users SET payment_status='pending_details', approved_at=%s WHERE chat_id=%s", (datetime.datetime.now(), user_chat_id))
                    await conn.commit()
            user_state[user_chat_id] = {'expecting': 'name', 'timestamp': time.time()}
            await context.bot.send_message(
                user_chat_id,
                "✅ Your payment is approved!\n\nPlease provide your full name:"
            )
            await query.edit_message_text("Payment approved. Waiting for user details.")
        elif parts[1] == "coupon":
            payment_id = int(parts[2])
            async with conn_pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("UPDATE payments SET status='approved', approved_at=%s WHERE id=%s", (datetime.datetime.now(), payment_id))
                    await conn.commit()
            user_state[ADMIN_ID] = {'expecting': {'type': 'coupon_codes', 'payment_id': payment_id}, 'timestamp': time.time()}
            await context.bot.send_message(ADMIN_ID, f"Payment {payment_id} approved. Please send the coupon codes (one per line).")
            await query.edit_message_text("Payment approved. Waiting for coupon codes.")
        elif parts[1] == "task":
            task_id = int(parts[2])
            user_chat_id = int(parts[3])
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, %s)", (user_chat_id, task_id, datetime.datetime.now()))
                    await cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                    reward = (await cursor.fetchone())["reward"]
                    await cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, user_chat_id))
                    await conn.commit()
            await context.bot.send_message(user_chat_id, f"Task approved! You earned ${reward}.")
            await query.edit_message_text("Task approved and reward awarded.")
    elif data.startswith("finalize_reg_"):
        user_chat_id = int(data.split("_")[2])
        user_state[ADMIN_ID] = {'expecting': 'user_credentials', 'for_user': user_chat_id, 'timestamp': time.time()}
        await context.bot.send_message(
            ADMIN_ID,
            f"Please send the username and password for user {user_chat_id} in the format:\nusername\npassword"
        )
        await query.edit_message_text("Waiting for user credentials.")
    elif data.startswith("reject_task_"):
        parts = data.split("_")
        task_id = int(parts[2])
        user_chat_id = int(parts[3])
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (user_chat_id,))
                balance = (await cursor.fetchone())["balance"]
                await cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                reward = (await cursor.fetchone())["reward"]
                if balance >= reward:
                    await cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s", (reward, user_chat_id))
                    await cursor.execute("DELETE FROM user_tasks WHERE user_id=%s AND task_id=%s", (user_chat_id, task_id))
                    await conn.commit()
                    await context.bot.send_message(user_chat_id, "Task verification rejected. Reward revoked.")
                    await query.edit_message_text("Task rejected and reward removed.")
                else:
                    await query.edit_message_text("Task rejected, but balance insufficient to revoke reward.")
    elif data.startswith("pending_"):
        parts = data.split("_")
        if parts[1] == "reg":
            await context.bot.send_message(int(parts[2]), "Your payment is still being reviewed. Please check back later.")
        elif parts[1] == "coupon":
            payment_id = int(parts[2])
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                    user_chat_id = (await cursor.fetchone())["chat_id"]
                    await context.bot.send_message(user_chat_id, "Your coupon payment is still being reviewed.")
    elif data == "check_approval":
        if 'waiting_approval' not in user_state.get(chat_id, {}):
            await context.bot.send_message(chat_id, "You have no pending payments.")
            return
        approval = user_state[chat_id]['waiting_approval']
        if approval['type'] == 'registration':
            status = await get_status(chat_id)
            if status == 'pending_details':
                user_state[chat_id] = {'expecting': 'name', 'timestamp': time.time()}
                await context.bot.send_message(chat_id, "Payment approved. Please provide your full name:")
            elif status == 'registered':
                await context.bot.send_message(chat_id, "Your registration is complete.")
            else:
                await context.bot.send_message(chat_id, "Your payment is being reviewed.")
        elif approval['type'] == 'coupon':
            payment_id = approval['payment_id']
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("SELECT status FROM payments WHERE id=%s", (payment_id,))
                    status = (await cursor.fetchone())["status"]
                    if status == 'approved':
                        await context.bot.send_message(chat_id, "Coupon payment approved. Check your coupons above.")
                    else:
                        await context.bot.send_message(chat_id, "Your coupon payment is being reviewed.")
    elif data == "toggle_reminder":
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT alarm_setting FROM users WHERE chat_id=%s", (chat_id,))
                current_setting = (await cursor.fetchone())["alarm_setting"]
                new_setting = 1 if current_setting == 0 else 0
                await cursor.execute("UPDATE users SET alarm_setting=%s WHERE chat_id=%s", (new_setting, chat_id))
                await conn.commit()
        status = "enabled" if new_setting == 1 else "disabled"
        await query.edit_message_text(f"Daily reminder {status}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))
    elif data == "boost_ai":
        await query.edit_message_text(
            f"🚀 Boost with AI\n\nAccess Advanced AI-powered features to maximize your earnings: {AI_BOOST_LINK}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
        )
    elif data == "user_registered":
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT username, email, password, package FROM users WHERE chat_id=%s", (chat_id,))
                user = await cursor.fetchone()
                if user:
                    username, email, password, package = user.values()
                    await query.edit_message_text(
                        f"🎉 Registration Complete!\n\n"
                        f"• Site: {SITE_LINK}\n"
                        f"• Username: {username}\n"
                        f"• Email: {email}\n"
                        f"• Password: {password}\n\n"
                        "Keep your credentials safe. Use 'Password Recovery' in the Help menu if needed.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
                    )
                else:
                    await query.edit_message_text("No registration data found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
    elif data == "daily_tasks":
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT package FROM users WHERE chat_id=%s", (chat_id,))
                package = (await cursor.fetchone())["package"]
        msg = f"Follow this link to perform your daily tasks and earn: {DAILY_TASK_LINK}"
        if package == "X":
            msg = f"🌟 X Users: Maximize your earnings with this special daily task link: {DAILY_TASK_LINK}"
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
    elif data == "earn_extra":
        now = datetime.datetime.now()
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("""
                    SELECT t.id, t.type, t.link, t.reward
                    FROM tasks t
                    WHERE t.expires_at > %s
                    AND t.id NOT IN (SELECT ut.task_id FROM user_tasks ut WHERE ut.user_id = %s)
                """, (now, chat_id))
                tasks = await cursor.fetchall()
                if not tasks:
                    await query.edit_message_text(
                        "No extra tasks available right now. Please check back later.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
                    )
                    return
                keyboard = []
                for task in tasks:
                    task_id, task_type, link, reward = task.values()
                    join_button = InlineKeyboardButton(f"Join {task_type} (${reward})", url=link)
                    verify_button = InlineKeyboardButton("Verify", callback_data=f"verify_task_{task_id}")
                    keyboard.append([join_button, verify_button])
                keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
                await query.edit_message_text("Available extra tasks for today:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("verify_task_"):
        task_id = int(data[len("verify_task_"):])
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                await cursor.execute("SELECT type, link FROM tasks WHERE id=%s", (task_id,))
                task = await cursor.fetchone()
                if not task:
                    await query.answer("Task not found.")
                    return
                task_type, link = task.values()
                regel = re.compile(r'(@[A-Za-z0-9_]+)|(?:https?://)?(?:www\.)?(?:t\.me|telegram\.(?:me|dog))/([A-Za-z0-9_\\+]+)')
                match = regel.search(link)
                if not match:
                    await query.answer("Invalid link format.")
                    return
                chat_username = match.group()
                if chat_username.startswith("http"):
                    chat_username = chat_username.split("/")[-1]
                if task_type in ["join_group", "join_channel"]:
                    try:
                        member = await context.bot.get_chat_member(chat_username, chat_id)
                        if member.status in ["member", "administrator", "creator"]:
                            await cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, %s)", (chat_id, task_id, datetime.datetime.now()))
                            await cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                            reward = (await cursor.fetchone())["reward"]
                            await cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, chat_id))
                            await conn.commit()
                            await query.answer(f"Task completed! You earned ${reward}.")
                        else:
                            await query.answer("You are not in the group/channel yet.")
                    except Exception as e:
                        logger.error(f"Error verifying task: {e}")
                        await query.answer("Error verifying task. Try again later.")
                elif task_type == "external_task":
                    user_state[chat_id] = {'expecting': 'task_screenshot', 'task_id': task_id, 'timestamp': time.time()}
                    await context.bot.send_message(chat_id, f"Please send the screenshot for task #{task_id} verification.")
    elif data == "faq":
        keyboard = [[InlineKeyboardButton(faq["question"], callback_data=f"faq_{key}")] for key, faq in FAQS.items()]
        keyboard.append([InlineKeyboardButton("Ask Another Question", callback_data="faq_custom")])
        keyboard.append([InlineKeyboardButton("🔙 Help Menu", callback_data="help")])
        await query.edit_message_text("Select a question or ask your own:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("faq_"):
        faq_key = data[len("faq_"):]
        if faq_key == "custom":
            user_state[chat_id]['expecting'] = 'faq'
            await query.edit_message_text("Please type your question:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))
        else:
            faq = FAQS.get(faq_key)
            if faq:
                await query.edit_message_text(
                    f"❓ {faq['question']}\n\n{faq['answer']}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 FAQ Menu", callback_data="faq"), InlineKeyboardButton("🔙 Help Menu", callback_data="help")]])
                )
            else:
                await query.edit_message_text("FAQ not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))
    elif data in HELP_TOPICS:
        topic = HELP_TOPICS[data]
        keyboard = [[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]
        if topic["type"] == "input":
            user_state[chat_id]['expecting'] = data
            await query.edit_message_text(topic["text"], reply_markup=InlineKeyboardMarkup(keyboard))
        elif topic["type"] == "toggle":
            keyboard = [
                [InlineKeyboardButton("Toggle Reminder On/Off", callback_data="toggle_reminder")],
                [InlineKeyboardButton("🔙 Help Menu", callback_data="help")]
            ]
            await query.edit_message_text("Toggle your daily reminder:", reply_markup=InlineKeyboardMarkup(keyboard))
        elif topic["type"] == "faq":
            await button_handler(update, context)  # Redirect to FAQ handler
        else:
            content = topic["text"] if topic["type"] == "text" else f"Watch here: {topic['url']}"
            await query.edit_message_text(content, reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "help":
        await help_menu(update, context)
    elif data == "enable_reminders":
        async with conn_pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("UPDATE users SET alarm_setting=1 WHERE chat_id=%s", (chat_id,))
                await conn.commit()
        await query.edit_message_text(
            "✅ Daily reminders enabled!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
        )
    elif data == "disable_reminders":
        async with conn_pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("UPDATE users SET alarm_setting=0 WHERE chat_id=%s", (chat_id,))
                await conn.commit()
        await query.edit_message_text(
            "❌ Okay, daily reminders not set.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
        )
    else:
        logger.warning(f"Unknown callback data: {data}")
        await query.edit_message_text("Unknown action. Please try again or contact @bigscottmedia.")

# Message handlers
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if 'expecting' not in user_state.get(chat_id, {}):
        return
    expecting = user_state[chat_id]['expecting']
    file_id = update.message.photo[-1].file_id
    logger.info(f"Processing photo for {expecting}")
    try:
        if expecting == 'reg_screenshot':
            async with conn_pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("UPDATE users SET screenshot_uploaded_at=%s WHERE chat_id=%s", (datetime.datetime.now(), chat_id))
                    await conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_reg_{chat_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_reg_{chat_id}")],
            ]
            await context.bot.send_photo(
                ADMIN_ID,
                file_id,
                caption=f"📸 Registration Payment from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text("✅ Screenshot received! Awaiting admin approval.")
            user_state[chat_id]['waiting_approval'] = {'type': 'registration'}
            context.job_queue.run_once(check_registration_payment, 3600, data={'chat_id': chat_id})
        elif expecting == 'coupon_screenshot':
            payment_id = user_state[chat_id]['waiting_approval']['payment_id']
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_coupon_{payment_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_coupon_{payment_id}")],
            ]
            await context.bot.send_photo(
                ADMIN_ID,
                file_id,
                caption=f"📸 Coupon Payment from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text("✅ Screenshot received! Awaiting admin approval.")
            context.job_queue.run_once(check_coupon_payment, 3600, data={'payment_id': payment_id})
        elif expecting == 'task_screenshot':
            task_id = user_state[chat_id]['task_id']
            await context.bot.send_photo(
                ADMIN_ID,
                file_id,
                caption=f"Task #{task_id} verification from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Approve", callback_data=f"approve_task_{task_id}_{chat_id}")],
                    [InlineKeyboardButton("Reject", callback_data=f"reject_task_{task_id}_{chat_id}")]
                ])
            )
            await update.message.reply_text("Screenshot received. Awaiting admin approval.")
        del user_state[chat_id]['expecting']
        await log_interaction(chat_id, "photo_upload")
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if 'expecting' not in user_state.get(chat_id, {}):
        return
    expecting = user_state[chat_id]['expecting']
    file_id = update.message.document.file_id
    mime_type = update.message.document.mime_type
    if not mime_type.startswith('image/'):
        await update.message.reply_text("Please send an image file (e.g., PNG, JPG).")
        return
    logger.info(f"Processing document for {expecting}")
    try:
        if expecting == 'reg_screenshot':
            async with conn_pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("UPDATE users SET screenshot_uploaded_at=%s WHERE chat_id=%s", (datetime.datetime.now(), chat_id))
                    await conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_reg_{chat_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_reg_{chat_id}")],
            ]
            await context.bot.send_document(
                ADMIN_ID,
                file_id,
                caption=f"📸 Registration Payment from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text("✅ Screenshot received! Awaiting admin approval.")
            user_state[chat_id]['waiting_approval'] = {'type': 'registration'}
            context.job_queue.run_once(check_registration_payment, 3600, data={'chat_id': chat_id})
        elif expecting == 'coupon_screenshot':
            payment_id = user_state[chat_id]['waiting_approval']['payment_id']
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_coupon_{payment_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_coupon_{payment_id}")],
            ]
            await context.bot.send_document(
                ADMIN_ID,
                file_id,
                caption=f"📸 Coupon Payment from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text("✅ Screenshot received! Awaiting admin approval.")
            context.job_queue.run_once(check_coupon_payment, 3600, data={'payment_id': payment_id})
        elif expecting == 'task_screenshot':
            task_id = user_state[chat_id]['task_id']
            await context.bot.send_document(
                ADMIN_ID,
                file_id,
                caption=f"Task #{task_id} verification from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id})",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Approve", callback_data=f"approve_task_{task_id}_{chat_id}")],
                    [InlineKeyboardButton("Reject", callback_data=f"reject_task_{task_id}_{chat_id}")]
                ])
            )
            await update.message.reply_text("Screenshot received. Awaiting admin approval.")
        del user_state[chat_id]['expecting']
        await log_interaction(chat_id, "document_upload")
    except Exception as e:
        logger.error(f"Error in handle_document: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text.strip()
    await log_interaction(chat_id, "text_message")
    logger.info(f"user_state[{chat_id}] = {user_state.get(chat_id, 'None')}")
    if 'expecting' not in user_state.get(chat_id, {}):
        status = await get_status(chat_id)
        if status == 'pending_details':
            user_state[chat_id] = {'expecting': 'name', 'timestamp': time.time()}
            await update.message.reply_text("Please provide your full name:")
            return
    expecting = user_state[chat_id]['expecting']
    try:
        if expecting == 'name':
            name = text
            if not name or len(name) < 2:
                await update.message.reply_text("Please provide a valid full name.")
                return
            user_state[chat_id]['name'] = name
            user_state[chat_id]['expecting'] = 'email'
            await update.message.reply_text("Please provide your email address:")
        elif expecting == 'email':
            email = text
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                await update.message.reply_text("Please provide a valid email address.")
                return
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("SELECT chat_id FROM users WHERE email=%s", (email,))
                    existing = await cursor.fetchone()
                    if existing and existing['chat_id'] != chat_id:
                        await update.message.reply_text("Email already registered.")
                        return
            user_state[chat_id]['email'] = email
            user_state[chat_id]['expecting'] = 'phone'
            await update.message.reply_text("Please provide your phone number (with country code, e.g., +2341234567890):")
        elif expecting == 'phone':
            phone = text
            if not re.match(r"\+?\d{10,15}", phone):
                await update.message.reply_text("Please provide a valid phone number.")
                return
            user_state[chat_id]['phone'] = phone
            user_state[chat_id]['expecting'] = 'telegram_username'
            await update.message.reply_text("Please provide your Telegram username (e.g., @bigscott):")
        elif expecting == 'telegram_username':
            telegram_username = text
            if not re.match(r"^@[A-Za-z0-9_]{5,}$", telegram_username):
                await update.message.reply_text("Please provide a valid Telegram username starting with @ (e.g., @bigscott).")
                return
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("SELECT chat_id FROM users WHERE username=%s", (telegram_username,))
                    existing = await cursor.fetchone()
                    if existing and existing['chat_id'] != chat_id:
                        await update.message.reply_text("Username already registered.")
                        return
                    await cursor.execute(
                        "UPDATE users SET name=%s, email=%s, phone=%s, username=%s WHERE chat_id=%s",
                        (user_state[chat_id]['name'], user_state[chat_id]['email'], user_state[chat_id]['phone'], telegram_username, chat_id)
                    )
                    await conn.commit()
                    await cursor.execute("SELECT package FROM users WHERE chat_id=%s", (chat_id,))
                    pkg = (await cursor.fetchone())["package"]
            keyboard = [[InlineKeyboardButton("Finalize Registration", callback_data=f"finalize_reg_{chat_id}")]]
            await context.bot.send_message(
                ADMIN_ID,
                f"🆕 User Details Received:\nUser ID: {chat_id}\nUsername: {telegram_username}\nPackage: {pkg}\nEmail: {user_state[chat_id]['email']}\nName: {user_state[chat_id]['name']}\nPhone: {user_state[chat_id]['phone']}\n\nPlease finalize registration by providing credentials.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text(
                "✅ Details received! Awaiting admin finalization.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
            )
            del user_state[chat_id]
        elif expecting == 'coupon_quantity':
            try:
                quantity = int(text)
                if quantity <= 0:
                    raise ValueError
                user_state[chat_id]['coupon_quantity'] = quantity
                keyboard = [
                    [InlineKeyboardButton("Standard (₦10,000)", callback_data="coupon_standard")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
                ]
                await update.message.reply_text("Select the package for your coupons:", reply_markup=InlineKeyboardMarkup(keyboard))
                del user_state[chat_id]['expecting']
            except ValueError:
                await update.message.reply_text("Please enter a valid positive integer.")
        elif expecting == 'faq':
            await context.bot.send_message(ADMIN_ID, f"FAQ from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}): {text}")
            await update.message.reply_text("Thank you! We’ll get back to you soon.")
            del user_state[chat_id]['expecting']
        elif expecting == 'password_recovery':
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("SELECT username, email, password FROM users WHERE email=%s AND chat_id=%s AND payment_status='registered'", (text, chat_id))
                    user = await cursor.fetchone()
                    if user:
                        username, email, _ = user.values()
                        new_password = secrets.token_urlsafe(8)
                        await cursor.execute("UPDATE users SET password=%s WHERE chat_id=%s", (new_password, chat_id))
                        await conn.commit()
                        await context.bot.send_message(
                            chat_id,
                            f"Your password has been reset.\nNew Password: {new_password}\nKeep it safe and use 'Password Recovery' if needed again."
                        )
                        await context.bot.send_message(
                            ADMIN_ID,
                            f"Password reset for @{username or 'Unknown'} (chat_id: {chat_id}, email: {email})"
                        )
                    else:
                        await update.message.reply_text("No account found with that email or you are not fully registered. Please try again or contact @bigscottmedia.")
            del user_state[chat_id]['expecting']
        elif expecting == 'support_message':
            await context.bot.send_message(
                ADMIN_ID,
                f"Support request from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}): {text}"
            )
            await update.message.reply_text("Thank you! Our support team will get back to you soon.")
            del user_state[chat_id]['expecting']
        elif isinstance(expecting, dict) and expecting.get('type') == 'coupon_codes' and chat_id == ADMIN_ID:
            payment_id = expecting['payment_id']
            codes = text.splitlines()
            async with conn_pool.connection() as conn:
                async with conn.cursor() as cursor:
                    for code in codes:
                        code = code.strip()
                        if code:
                            await cursor.execute("INSERT INTO coupons (payment_id, code) VALUES (%s, %s)", (payment_id, code))
                    await conn.commit()
                    async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                        await cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                        user_chat_id = (await cursor.fetchone())["chat_id"]
            await context.bot.send_message(
                user_chat_id,
                "🎉 Your coupon purchase is approved!\n\nHere are your coupons:\n" + "\n".join(codes)
            )
            await update.message.reply_text("Coupons sent to the user successfully.")
            del user_state[chat_id]['expecting']
        elif expecting == 'user_credentials' and chat_id == ADMIN_ID:
            lines = text.splitlines()
            if len(lines) != 2:
                await update.message.reply_text("Please send username and password in two lines.")
                return
            username, password = lines
            for_user = user_state[chat_id]['for_user']
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute(
                        "UPDATE users SET username=%s, password=%s, payment_status='registered', registration_date=%s WHERE chat_id=%s",
                        (username, password, datetime.datetime.now(), for_user)
                    )
                    await conn.commit()
                    await cursor.execute("SELECT package, referred_by FROM users WHERE chat_id=%s", (for_user,))
                    row = await cursor.fetchone()
                    if row:
                        package, referred_by = row.values()
                        if referred_by:
                            additional_reward = 0.4 if package == "Standard" else 0.9
                            await cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (additional_reward, referred_by))
                            await conn.commit()
            await context.bot.send_message(
                for_user,
                f"🎉 Registration successful! Your username is\n {username}\n and password is\n {password}\n\n Join the group using the link below to access your Mentorship forum:\n {GROUP_LINK}"
            )
            async with conn_pool.connection() as conn:
                async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                    await cursor.execute("SELECT package, email, name, phone FROM users WHERE chat_id=%s", (for_user,))
                    user_details = await cursor.fetchone()
                    if user_details:
                        pkg, email, full_name, phone = user_details.values()
                        await context.bot.send_message(
                            ADMIN_ID,
                            f"New registration:\nUser ID: {for_user}\nUsername: {username}\nPackage: {pkg}\nEmail: {email}\nName: {full_name}\nPhone: {phone}"
                        )
            await update.message.reply_text("Credentials set and sent to the user.")
            keyboard = [
                [InlineKeyboardButton("Yes, enable reminders", callback_data="enable_reminders")],
                [InlineKeyboardButton("No, disable reminders", callback_data="disable_reminders")],
            ]
            await context.bot.send_message(for_user, "Would you like to receive daily reminders to complete your tasks?", reply_markup=InlineKeyboardMarkup(keyboard))
            reply_keyboard = [["/menu(🔙)"], [KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=f"{WEBAPP_URL}?chat_id={for_user}"))], [KeyboardButton(text="Play Aviator", web_app=WebAppInfo(url=f"{AVIATOR_URL}?chat_id={for_user}"))]]
            await context.bot.send_message(
                for_user,
                "Use the button below to engage in other processes",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )
            del user_state[chat_id]
    except Exception as e:
        logger.error(f"Error in handle_text: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")

# Job functions
async def check_registration_payment(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    status = await get_status(chat_id)
    if status == 'pending_payment':
        keyboard = [[InlineKeyboardButton("Payment Approval Stats", callback_data="check_approval")]]
        await context.bot.send_message(chat_id, "Your payment is still being reviewed. Click below to check status:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif status == 'pending_details':
        if 'expecting' not in user_state.get(chat_id, {}):
            user_state[chat_id] = {'expecting': 'name', 'timestamp': time.time()}
            await context.bot.send_message(chat_id, "Please provide your full name:")

async def check_coupon_payment(context: ContextTypes.DEFAULT_TYPE):
    payment_id = context.job.data['payment_id']
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT status, chat_id FROM payments WHERE id=%s", (payment_id,))
            row = await cursor.fetchone()
            if row and row["status"] == 'pending_payment':
                chat_id = row["chat_id"]
                keyboard = [[InlineKeyboardButton("Payment Approval Stats", callback_data="check_approval")]]
                await context.bot.send_message(chat_id, "Your coupon payment is still being reviewed. Click below to check status:", reply_markup=InlineKeyboardMarkup(keyboard))

async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT chat_id FROM users WHERE alarm_setting=1")
            user_ids = [row["chat_id"] for row in await cursor.fetchall()]
            for user_id in user_ids:
                try:
                    await context.bot.send_message(user_id, "🌟 Daily Reminder: Complete your Tapify tasks to maximize your earnings!")
                    await log_interaction(user_id, "daily_reminder")
                except Exception as e:
                    logger.error(f"Failed to send reminder to {user_id}: {e}")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now()
    start_time = now - datetime.timedelta(days=1)
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT COUNT(*) AS count FROM users WHERE registration_date >= %s", (start_time,))
            new_users = (await cursor.fetchone())["count"]
            await cursor.execute("""
                SELECT SUM(CASE package WHEN 'Standard' THEN 10000 WHEN 'X' THEN 14000 ELSE 0 END) AS sum
                FROM users
                WHERE approved_at >= %s AND payment_status = 'registered'
            """, (start_time,))
            reg_payments = (await cursor.fetchone())["sum"] or 0
            await cursor.execute("SELECT SUM(total_amount) AS sum FROM payments WHERE approved_at >= %s AND status = 'approved'", (start_time,))
            coupon_payments = (await cursor.fetchone())["sum"] or 0
            total_payments = reg_payments + coupon_payments
            await cursor.execute("SELECT COUNT(*) AS count FROM user_tasks WHERE completed_at >= %s", (start_time,))
            tasks_completed = (await cursor.fetchone())["count"]
            await cursor.execute("""
                SELECT SUM(t.reward) AS sum
                FROM user_tasks ut
                JOIN tasks t ON ut.task_id = t.id
                WHERE ut.completed_at >= %s
            """, (start_time,))
            total_distributed = (await cursor.fetchone())["sum"] or 0
            text = (
                f"📊 Daily Summary ({now.strftime('%Y-%m-%d')}):\n\n"
                f"• New Users: {new_users}\n"
                f"• Total Payments Approved: ₦{total_payments}\n"
                f"• Tasks Completed: {tasks_completed}\n"
                f"• Total Balance Distributed: ${total_distributed}"
            )
            await context.bot.send_message(ADMIN_ID, text)

async def clear_stale_user_state(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(user_state.keys()):
        if 'timestamp' in user_state[chat_id] and (time.time() - user_state[chat_id]['timestamp'] > 3600):
            logger.info(f"Clearing stale user_state for {chat_id}")
            del user_state[chat_id]

# Menus
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("SELECT payment_status, package FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            keyboard = [
                [InlineKeyboardButton("How It Works", callback_data="how_it_works")],
                [InlineKeyboardButton("Purchase Coupon", callback_data="coupon")],
                [InlineKeyboardButton("💸 Get Registered", callback_data="package_selector")],
                [InlineKeyboardButton("❓ Help", callback_data="help")],
            ]
            if user and user["payment_status"] == 'registered':
                keyboard = [
                    [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                    [InlineKeyboardButton("Do Daily Tasks", callback_data="daily_tasks")],
                    [InlineKeyboardButton("💰 Earn Extra for the Day", callback_data="earn_extra")],
                    [InlineKeyboardButton("Purchase Coupon", callback_data="coupon")],
                    [InlineKeyboardButton("❓ Help", callback_data="help")],
                ]
                if user["package"] == "X":
                    keyboard.insert(1, [InlineKeyboardButton("🚀 Boost with AI", callback_data="boost_ai")])
            text = "Select an option below:"
            reply_keyboard = [["/menu(🔙)"]]
            if user and user["payment_status"] == 'registered':
                reply_keyboard.append([KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=f"{WEBAPP_URL}?chat_id={chat_id}"))])
                reply_keyboard.append([KeyboardButton(text="Play Aviator", web_app=WebAppInfo(url=f"{AVIATOR_URL}?chat_id={chat_id}"))])
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                await context.bot.send_message(
                    chat_id,
                    "Use the button below 'ONLY' if you get stuck on a process:",
                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
                )
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                await context.bot.send_message(
                    chat_id,
                    "Use the button below 'ONLY' if you get stuck on a process:",
                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
                )
            await log_interaction(chat_id, "show_main_menu")

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.callback_query.from_user.id
    status = await get_status(chat_id)
    keyboard = [[InlineKeyboardButton(topic["label"], callback_data=key)] for key, topic in HELP_TOPICS.items()]
    if status == 'registered':
        keyboard.append([InlineKeyboardButton("👥 Refer a Friend", callback_data="refer_friend")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
    query = update.callback_query
    await query.edit_message_text("What would you like help with?", reply_markup=InlineKeyboardMarkup(keyboard))
    await log_interaction(chat_id, "help_menu")

# Webhook route
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    update_data = request.get_json(force=True)
    logger.info(f"Received webhook update: {update_data}")
    update = Update.de_json(update_data, application.bot)
    if update:
        logger.info(f"Parsed update: {update}")
        application.update_queue.put_nowait(update)
    else:
        logger.error("Failed to parse update")
    return jsonify({"ok": True}), 200

@app.route('/')
async def home():
    return "Tapify is alive!"

# Tap + Aviator Addon
K = 0.00012  # growth per millisecond

def _multiplier_at_ms(ms: int) -> float:
    return (1 + K) ** ms

def _sample_crash_point() -> float:
    u = random.random() or 1e-9
    lam = 1.1
    extra = -math.log(u) / lam
    crash = 1.02 + extra * 2.2
    return max(1.02, round(crash, 2))

@app.post("/api/tap")
async def api_tap():
    data = request.get_json(force=True)
    logger.info(f"API /tap called with data: {data}")
    chat_id = int(data.get("chat_id", 0) or 0)
    if not chat_id:
        return jsonify({"ok": False, "error": "chat_id required"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute("UPDATE users SET balance = COALESCE(balance,0) + 0.01 WHERE chat_id=%s AND payment_status='registered'", (chat_id,))
            await conn.commit()
            await cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            row = await cursor.fetchone()
            if not row:
                return jsonify({"ok": False, "error": "user not found"}), 404
            return jsonify({"ok": True, "balance": float(row["balance"])})
            
# Aviator API Endpoints
@app.post("/api/aviator/start")
async def api_aviator_start():
    data = request.get_json(force=True)
    logger.info(f"API /aviator/start called with data: {data}")
    chat_id = int(data.get("chat_id", 0) or 0)
    bet_amount = float(data.get("bet_amount", 0) or 0)
    if not chat_id or bet_amount <= 0:
        return jsonify({"ok": False, "error": "Invalid chat_id or bet_amount"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            # Check if user is registered and has sufficient balance
            await cursor.execute("SELECT balance, payment_status FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            if not user or user["payment_status"] != "registered":
                return jsonify({"ok": False, "error": "User not registered"}), 403
            if user["balance"] < bet_amount:
                return jsonify({"ok": False, "error": "Insufficient balance"}), 403
            # Deduct bet amount
            await cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s", (bet_amount, chat_id))
            # Generate round details
            seed = secrets.token_hex(16)
            crash_point = _sample_crash_point()
            start_time = datetime.datetime.now()
            # Create new round
            await cursor.execute(
                """
                INSERT INTO aviator_rounds (chat_id, seed, crash_point, start_time, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id
                """,
                (chat_id, seed, crash_point, start_time)
            )
            round_id = (await cursor.fetchone())["id"]
            # Record play
            await cursor.execute(
                """
                INSERT INTO aviator_plays (round_id, chat_id, bet_amount, outcome)
                VALUES (%s, %s, %s, 'none')
                """,
                (round_id, chat_id, bet_amount)
            )
            await conn.commit()
    return jsonify({
        "ok": True,
        "round_id": round_id,
        "seed": seed,
        "start_time": start_time.isoformat()
    }), 200

@app.post("/api/aviator/cashout")
async def api_aviator_cashout():
    data = request.get_json(force=True)
    logger.info(f"API /aviator/cashout called with data: {data}")
    chat_id = int(data.get("chat_id", 0) or 0)
    round_id = int(data.get("round_id", 0) or 0)
    if not chat_id or not round_id:
        return jsonify({"ok": False, "error": "Invalid chat_id or round_id"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            # Verify round
            await cursor.execute(
                """
                SELECT id, crash_point, start_time, status
                FROM aviator_rounds
                WHERE id=%s AND chat_id=%s AND status='active'
                """,
                (round_id, chat_id)
            )
            round_data = await cursor.fetchone()
            if not round_data:
                return jsonify({"ok": False, "error": "Round not found or already ended"}), 404
            # Calculate current multiplier
            elapsed_ms = (datetime.datetime.now() - round_data["start_time"]).total_seconds() * 1000
            current_multiplier = _multiplier_at_ms(elapsed_ms)
            if current_multiplier >= round_data["crash_point"]:
                # Round has crashed
                await cursor.execute(
                    """
                    UPDATE aviator_rounds SET status='crashed', end_time=%s WHERE id=%s
                    """,
                    (datetime.datetime.now(), round_id)
                )
                await cursor.execute(
                    """
                    UPDATE aviator_plays SET outcome='lose' WHERE round_id=%s AND chat_id=%s
                    """,
                    (round_id, chat_id)
                )
                await conn.commit()
                return jsonify({
                    "ok": False,
                    "error": "Round crashed",
                    "crash_point": round_data["crash_point"]
                }), 400
            # Process cashout
            await cursor.execute(
                """
                SELECT bet_amount FROM aviator_plays WHERE round_id=%s AND chat_id=%s
                """,
                (round_id, chat_id)
            )
            bet_amount = (await cursor.fetchone())["bet_amount"]
            payout = bet_amount * current_multiplier
            await cursor.execute(
                """
                UPDATE aviator_plays
                SET cashout_multiplier=%s, payout=%s, outcome='win'
                WHERE round_id=%s AND chat_id=%s
                """,
                (current_multiplier, payout, round_id, chat_id)
            )
            await cursor.execute(
                """
                UPDATE aviator_rounds SET status='cashed', end_time=%s WHERE id=%s
                """,
                (datetime.datetime.now(), round_id)
            )
            await cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE chat_id=%s",
                (payout, chat_id)
            )
            await cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            balance = (await cursor.fetchone())["balance"]
            await conn.commit()
    return jsonify({
        "ok": True,
        "multiplier": round(current_multiplier, 2),
        "payout": round(payout, 2),
        "balance": balance
    }), 200

@app.get("/api/aviator/status")
async def api_aviator_status():
    data = request.args
    chat_id = int(data.get("chat_id", 0) or 0)
    round_id = int(data.get("round_id", 0) or 0)
    if not chat_id or not round_id:
        return jsonify({"ok": False, "error": "Invalid chat_id or round_id"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute(
                """
                SELECT id, seed, crash_point, start_time, status
                FROM aviator_rounds
                WHERE id=%s AND chat_id=%s
                """,
                (round_id, chat_id)
            )
            round_data = await cursor.fetchone()
            if not round_data:
                return jsonify({"ok": False, "error": "Round not found"}), 404
            status = round_data["status"]
            response = {
                "ok": True,
                "round_id": round_data["id"],
                "status": status,
                "seed": round_data["seed"]
            }
            if status == "active":
                elapsed_ms = (datetime.datetime.now() - round_data["start_time"]).total_seconds() * 1000
                current_multiplier = _multiplier_at_ms(elapsed_ms)
                response["current_multiplier"] = round(current_multiplier, 2)
                if current_multiplier >= round_data["crash_point"]:
                    await cursor.execute(
                        """
                        UPDATE aviator_rounds SET status='crashed', end_time=%s WHERE id=%s
                        """,
                        (datetime.datetime.now(), round_id)
                    )
                    await cursor.execute(
                        """
                        UPDATE aviator_plays SET outcome='lose' WHERE round_id=%s AND chat_id=%s
                        """,
                        (round_id, chat_id)
                    )
                    await conn.commit()
                    response["status"] = "crashed"
                    response["crash_point"] = round_data["crash_point"]
            elif status == "crashed":
                response["crash_point"] = round_data["crash_point"]
            elif status == "cashed":
                await cursor.execute(
                    """
                    SELECT cashout_multiplier, payout
                    FROM aviator_plays
                    WHERE round_id=%s AND chat_id=%s
                    """,
                    (round_id, chat_id)
                )
                play_data = await cursor.fetchone()
                response["cashout_multiplier"] = round(play_data["cashout_multiplier"], 2)
                response["payout"] = round(play_data["payout"], 2)
            return jsonify(response), 200

@app.route("/tap")
async def tap_webapp():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tapify Game</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
    </head>
    <body>
        <h1>Tapify Game</h1>
        <p>Balance: <span id="balance">0</span></p>
        <button id="tapButton" style="font-size: 24px; padding: 20px;">Tap Me!</button>
        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            const chat_id = new URLSearchParams(window.location.search).get('chat_id');
            let balance = 0;

            async function updateBalance() {
                const response = await fetch('/api/tap', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chat_id: chat_id})
                });
                const data = await response.json();
                if (data.ok) {
                    balance = data.balance;
                    document.getElementById('balance').innerText = balance.toFixed(2);
                } else {
                    alert(data.error);
                }
            }

            document.getElementById('tapButton').addEventListener('click', updateBalance);
            updateBalance(); // Initial balance fetch
        </script>
    </body>
    </html>
    """

@app.route("/aviator")
async def aviator_webapp():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aviator Game</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; }
            #plane { font-size: 50px; position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); }
            #multiplier { font-size: 24px; margin-top: 20px; }
            #status { font-size: 18px; color: red; }
            #betAmount { width: 100px; margin: 10px; }
            button { font-size: 18px; padding: 10px 20px; margin: 5px; }
        </style>
    </head>
    <body>
        <h1>Aviator Game</h1>
        <p>Balance: <span id="balance">0</span></p>
        <p id="multiplier">Multiplier: 1.00x</p>
        <p id="status"></p>
        <div id="plane">✈️</div>
        <input type="number" id="betAmount" placeholder="Bet Amount" step="0.01" min="0.01">
        <br>
        <button id="startButton">Start Round</button>
        <button id="cashoutButton" disabled>Cash Out</button>
        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            const chat_id = new URLSearchParams(window.location.search).get('chat_id');
            let balance = 0;
            let round_id = null;
            let animationFrame;

            async function fetchBalance() {
                const response = await fetch(`/api/tap?chat_id=${chat_id}`);
                const data = await response.json();
                if (data.ok) {
                    balance = data.balance;
                    document.getElementById('balance').innerText = balance.toFixed(2);
                }
            }

            async function startRound() {
                const betAmount = parseFloat(document.getElementById('betAmount').value);
                if (!betAmount || betAmount <= 0) {
                    alert('Please enter a valid bet amount');
                    return;
                }
                const response = await fetch('/api/aviator/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chat_id: chat_id, bet_amount: betAmount})
                });
                const data = await response.json();
                if (data.ok) {
                    round_id = data.round_id;
                    document.getElementById('startButton').disabled = true;
                    document.getElementById('cashoutButton').disabled = false;
                    document.getElementById('status').innerText = 'Round started!';
                    updateMultiplier();
                } else {
                    alert(data.error);
                }
            }

            async function cashOut() {
                if (!round_id) return;
                const response = await fetch('/api/aviator/cashout', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chat_id: chat_id, round_id: round_id})
                });
                const data = await response.json();
                if (data.ok) {
                    document.getElementById('status').innerText = `Cashed out at ${data.multiplier}x! Payout: $${data.payout.toFixed(2)}`;
                    balance = data.balance;
                    document.getElementById('balance').innerText = balance.toFixed(2);
                    resetGame();
                } else {
                    document.getElementById('status').innerText = `Crashed at ${data.crash_point}x!`;
                    resetGame();
                }
            }

            async function updateMultiplier() {
                if (!round_id) return;
                const response = await fetch(`/api/aviator/status?chat_id=${chat_id}&round_id=${round_id}`);
                const data = await response.json();
                if (data.ok) {
                    if (data.status === 'active') {
                        document.getElementById('multiplier').innerText = `Multiplier: ${data.current_multiplier.toFixed(2)}x`;
                        const plane = document.getElementById('plane');
                        const height = Math.min(data.current_multiplier * 20, window.innerHeight - 100);
                        plane.style.bottom = `${height}px`;
                        animationFrame = requestAnimationFrame(updateMultiplier);
                    } else if (data.status === 'crashed') {
                        document.getElementById('status').innerText = `Crashed at ${data.crash_point}x!`;
                        resetGame();
                    } else if (data.status === 'cashed') {
                        document.getElementById('status').innerText = `Cashed out at ${data.cashout_multiplier}x! Payout: $${data.payout.toFixed(2)}`;
                        resetGame();
                    }
                } else {
                    document.getElementById('status').innerText = data.error;
                    resetGame();
                }
            }

            function resetGame() {
                cancelAnimationFrame(animationFrame);
                document.getElementById('startButton').disabled = false;
                document.getElementById('cashoutButton').disabled = true;
                document.getElementById('plane').style.bottom = '20px';
                document.getElementById('multiplier').innerText = 'Multiplier: 1.00x';
                round_id = null;
                fetchBalance();
            }

            document.getElementById('startButton').addEventListener('click', startRound);
            document.getElementById('cashoutButton').addEventListener('click', cashOut);
            fetchBalance();
        </script>
    </body>
    </html>
    """

# Main bot setup
async def main():
    global application
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("game", cmd_game))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("reset", reset_state))
    application.add_handler(CommandHandler("add_task", add_task))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)

    # Jobs
    application.job_queue.run_daily(daily_reminder, time=datetime.time(hour=8, minute=0))
    application.job_queue.run_daily(daily_summary, time=datetime.time(hour=23, minute=59))
    application.job_queue.run_repeating(clear_stale_user_state, interval=3600, first=3600)

    # Database setup
    await setup_db()

    # Start webhook
    await application.bot.set_webhook(url=WEBHOOK_URL + BOT_TOKEN)
    logger.info(f"Webhook set to {WEBHOOK_URL + BOT_TOKEN}")

if __name__ == "__main__":
    import uvicorn
    asyncio.run(main())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
