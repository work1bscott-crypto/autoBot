#!/usr/bin/env python3
# main.py — Tapify Main Bot for Telegram
# Requirements:
#   pip install python-telegram-bot==20.7 psycopg[binary] python-dotenv flask pydub
#
# Environment (.env):
#   BOT_TOKEN=your_bot_token
#   ADMIN_ID=your_admin_id
#   GROUP_LINK=your_group_link
#   SITE_LINK=your_site_link
#   AI_BOOST_LINK=your_ai_boost_link
#   DAILY_TASK_LINK=your_daily_task_link
#   DATABASE_URL=postgres://user:pass@host:port/dbname
#   WEBHOOK_URL=your_webhook_url
#   WEBAPP_BASE=your_webapp_base
#   PORT=your_port (e.g., 8080)
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
from threading import Thread

# Flask setup for Render keep-alive and APIs
app = Flask(__name__)

# Get bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")

# Create PTB Application
application = Application.builder().token(BOT_TOKEN).build()

# Webhook route
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok", 200
    
@app.route('/')
def home():
    return "Tapify is alive!"

#@app.post(f"/{os.getenv('BOT_TOKEN')}")
#def webhook():
#   update = Update.de_json(request.get_json(), application.bot)
#    loop.run_until_complete(application.process_update(update))
#    return "ok"

# Bot credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
GROUP_LINK = os.getenv("GROUP_LINK", "")
SITE_LINK = os.getenv("SITE_LINK", "")
AI_BOOST_LINK = os.getenv("AI_BOOST_LINK", "")
DAILY_TASK_LINK = os.getenv("DAILY_TASK_LINK", "")
WEBAPP_BASE = os.getenv("WEBAPP_BASE", "https://tapify.onrender.com")
WEBAPP_URL = f"{WEBAPP_BASE}/tap"
AVIATOR_URL = f"{WEBAPP_BASE}/aviator"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

# Validate environment variables
if not BOT_TOKEN:
    logging.error("BOT_TOKEN is required in environment (.env)")
    raise ValueError("BOT_TOKEN is required")
if not ADMIN_ID:
    logging.error("ADMIN_ID is required in environment (.env)")
    raise ValueError("ADMIN_ID is required")
if not WEBHOOK_URL:
    logging.error("WEBHOOK_URL is required in environment (.env)")
    raise ValueError("WEBHOOK_URL is required")
if not WEBAPP_BASE:
    logging.error("WEBAPP_BASE is required in environment (.env)")
    raise ValueError("WEBAPP_BASE is required")

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
try:
    sound = AudioSegment.from_mp3("voice.mp3")
    sound.export("voice.ogg", format="ogg", codec="libopus")
except FileNotFoundError:
    logging.warning("voice.mp3 not found; voice note feature may fail")

# Database setup
conn = None
cursor = None

async def setup_db():
    global conn, cursor
    import urllib.parse as urlparse

    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL must be set for PostgreSQL")
    if "sslmode=" not in url:
        if "?" in url:
            url += "&sslmode=require"
        else:
            url += "?sslmode=require"
    conn = await psycopg.AsyncConnection.connect(url, row_factory=psycopg.rows.dict_row)
    cursor = await conn.cursor()

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
        );
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
        );
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
    try:
        await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = await cursor.fetchone()
        return row["payment_status"] if row else None
    except psycopg.Error as e:
        logger.error(f"Database error in get_status: {e}")
        return None

async def is_registered(chat_id):
    try:
        await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = await cursor.fetchone()
        return row and row["payment_status"] == 'registered'
    except psycopg.Error as e:
        logger.error(f"Database error in is_registered {chat_id}: {e}")
        return False

async def log_interaction(chat_id, action):
    try:
        await cursor.execute("INSERT INTO interactions (chat_id, action) VALUES (%s, %s)", (chat_id, action))
        await conn.commit()
    except psycopg.Error as e:
        logger.error(f"Database error in log_interaction: {e}")

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
    try:
        await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        if not await cursor.fetchone():
            await cursor.execute(
                "INSERT INTO users (chat_id, username, referral_code, referred_by) VALUES (%s, %s, %s, %s)",
                (chat_id, update.effective_user.username or "Unknown", referral_code, referred_by)
            )
            if referred_by:
                await cursor.execute("UPDATE users SET invites = invites + 1, balance = balance + 0.1 WHERE chat_id=%s", (referred_by,))
            await conn.commit()
    except psycopg.Error as e:
        logger.error(f"Database error in start: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
        return
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
    user_state[chat_id] = {'expecting': 'support_message'}
    await update.message.reply_text("Please describe your issue or question:")
    await log_interaction(chat_id, "support_initiated")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await log_interaction(chat_id, "stats")
    try:
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
    except psycopg.Error as e:
        logger.error(f"Database error in stats: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

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
    try:
        await cursor.execute(
            "INSERT INTO tasks (type, link, reward, created_at, expires_at) VALUES (%s, %s, %s, %s, %s)",
            (task_type, link, reward, created_at, expires_at)
        )
        await conn.commit()
        await update.message.reply_text("Task added successfully.")
        await log_interaction(chat_id, "add_task")
    except psycopg.Error as e:
        logger.error(f"Database error in add_task: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("This command is restricted to the admin.")
        return
    user_state[chat_id] = {'expecting': 'broadcast_message'}
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

    try:
        if data == "menu":
            if chat_id in user_state:
                del user_state[chat_id]
            await show_main_menu(update, context)
        elif data == "stats":
            await stats(update, context)
        elif data == "refer_friend":
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
                    text="Error: Voice note file not found. Please contact support.",
                    reply_markup=voice_markup
                )
            except Exception as e:
                logger.error(f"Error sending voice note: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="An error occurred while sending the voice note. Please try again.",
                    reply_markup=voice_markup
                )
        elif data == "close_voice":
            await query.message.delete()
        elif data == "coupon":
            user_state[chat_id] = {'expecting': 'coupon_quantity'}
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
            user_state[chat_id] = {'package': package}
            try:
                await cursor.execute("UPDATE users SET package=%s, payment_status='pending_payment' WHERE chat_id=%s", (package, chat_id))
                if cursor.rowcount == 0:
                    await cursor.execute("INSERT INTO users (chat_id, package, payment_status, username) VALUES (%s, %s, 'pending_payment', %s)", (chat_id, package, update.effective_user.username or "Unknown"))
                await conn.commit()
                keyboard = [[InlineKeyboardButton(a, callback_data=f"reg_account_{a}")] for a in PAYMENT_ACCOUNTS.keys()]
                keyboard.append([InlineKeyboardButton("Other country option", callback_data="reg_other")])
                keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
                await query.edit_message_text("Select an account to pay to:", reply_markup=InlineKeyboardMarkup(keyboard))
            except psycopg.Error as e:
                logger.error(f"Database error in package_selector: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
                return
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
                try:
                    await cursor.execute("UPDATE users SET payment_status='pending_details', approved_at=%s WHERE chat_id=%s", (datetime.datetime.now(), user_chat_id))
                    await conn.commit()
                    user_state[user_chat_id] = {'expecting': 'name'}
                    await context.bot.send_message(
                        user_chat_id,
                        "✅ Your payment is approved!\n\nPlease provide your full name:"
                    )
                    await query.edit_message_text("Payment approved. Waiting for user details.")
                except psycopg.Error as e:
                    logger.error(f"Database error in approve_reg: {e}")
                    await query.edit_message_text("An error occurred. Please try again.")
            elif parts[1] == "coupon":
                payment_id = int(parts[2])
                try:
                    await cursor.execute("UPDATE payments SET status='approved', approved_at=%s WHERE id=%s", (datetime.datetime.now(), payment_id))
                    await conn.commit()
                    user_state[ADMIN_ID] = {'expecting': {'type': 'coupon_codes', 'payment_id': payment_id}}
                    await context.bot.send_message(ADMIN_ID, f"Payment {payment_id} approved. Please send the coupon codes (one per line).")
                    await query.edit_message_text("Payment approved. Waiting for coupon codes.")
                except psycopg.Error as e:
                    logger.error(f"Database error in approve_coupon: {e}")
                    await query.edit_message_text("An error occurred. Please try again.")
            elif parts[1] == "task":
                task_id = int(parts[2])
                user_chat_id = int(parts[3])
                try:
                    await cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, %s)", (user_chat_id, task_id, datetime.datetime.now()))
                    await cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                    reward = (await cursor.fetchone())["reward"]
                    await cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, user_chat_id))
                    await conn.commit()
                    await context.bot.send_message(user_chat_id, f"Task approved! You earned ${reward}.")
                    await query.edit_message_text("Task approved and reward awarded.")
                except psycopg.Error as e:
                    logger.error(f"Database error in approve_task: {e}")
                    await query.edit_message_text("An error occurred. Please try again.")
        elif data.startswith("finalize_reg_"):
            user_chat_id = int(data.split("_")[2])
            user_state[ADMIN_ID] = {'expecting': 'user_credentials', 'for_user': user_chat_id}
            await context.bot.send_message(
                ADMIN_ID,
                f"Please send the username and password for user {user_chat_id} in the format:\nusername\npassword"
            )
            await query.edit_message_text("Waiting for user credentials.")
        elif data.startswith("reject_task_"):
            parts = data.split("_")
            task_id = int(parts[2])
            user_chat_id = int(parts[3])
            try:
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
            except psycopg.Error as e:
                logger.error(f"Database error in reject_task: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif data.startswith("pending_"):
            parts = data.split("_")
            if parts[1] == "reg":
                await context.bot.send_message(int(parts[2]), "Your payment is still being reviewed. Please check back later.")
            elif parts[1] == "coupon":
                payment_id = int(parts[2])
                try:
                    await cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                    user_chat_id = (await cursor.fetchone())["chat_id"]
                    await context.bot.send_message(user_chat_id, "Your coupon payment is still being reviewed.")
                except psycopg.Error as e:
                    logger.error(f"Database error in pending_coupon: {e}")
                    await query.edit_message_text("An error occurred. Please try again.")
        elif data == "check_approval":
            if 'waiting_approval' not in user_state.get(chat_id, {}):
                await context.bot.send_message(chat_id, "You have no pending payments.")
                return
            approval = user_state[chat_id]['waiting_approval']
            if approval['type'] == 'registration':
                status = await get_status(chat_id)
                if status == 'pending_details':
                    user_state[chat_id] = {'expecting': 'name'}
                    await context.bot.send_message(chat_id, "Payment approved. Please provide your full name:")
                elif status == 'registered':
                    await context.bot.send_message(chat_id, "Your registration is complete.")
                else:
                    await context.bot.send_message(chat_id, "Your payment is being reviewed.")
            elif approval['type'] == 'coupon':
                payment_id = approval['payment_id']
                try:
                    await cursor.execute("SELECT status FROM payments WHERE id=%s", (payment_id,))
                    status = (await cursor.fetchone())["status"]
                    if status == 'approved':
                        await context.bot.send_message(chat_id, "Coupon payment approved. Check your coupons above.")
                    else:
                        await context.bot.send_message(chat_id, "Your coupon payment is being reviewed.")
                except psycopg.Error as e:
                    logger.error(f"Database error in check_approval: {e}")
                    await context.bot.send_message(chat_id, "An error occurred. Please try again.")
        elif data == "toggle_reminder":
            try:
                await cursor.execute("SELECT alarm_setting FROM users WHERE chat_id=%s", (chat_id,))
                current_setting = (await cursor.fetchone())["alarm_setting"]
                new_setting = 1 if current_setting == 0 else 0
                await cursor.execute("UPDATE users SET alarm_setting=%s WHERE chat_id=%s", (new_setting, chat_id))
                await conn.commit()
                status = "enabled" if new_setting == 1 else "disabled"
                await query.edit_message_text(f"Daily reminder {status}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))
            except psycopg.Error as e:
                logger.error(f"Database error in toggle_reminder: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif data == "boost_ai":
            await query.edit_message_text(
                f"🚀 Boost with AI\n\nAccess Advanced AI-powered features to maximize your earnings: {AI_BOOST_LINK}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
            )
        elif data == "user_registered":
            try:
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
            except psycopg.Error as e:
                logger.error(f"Database error in user_registered: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif data == "daily_tasks":
            try:
                await cursor.execute("SELECT package FROM users WHERE chat_id=%s", (chat_id,))
                package = (await cursor.fetchone())["package"]
                msg = f"Follow this link to perform your daily tasks and earn: {DAILY_TASK_LINK}"
                if package == "X":
                    msg = f"🌟 X Users: Maximize your earnings with this special daily task link: {DAILY_TASK_LINK}"
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
            except psycopg.Error as e:
                logger.error(f"Database error in daily_tasks: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif data == "earn_extra":
            now = datetime.datetime.now()
            try:
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
            except psycopg.Error as e:
                logger.error(f"Database error in earn_extra: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif data.startswith("verify_task_"):
            task_id = int(data[len("verify_task_"):])
            try:
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
                    user_state[chat_id] = {'expecting': 'task_screenshot', 'task_id': task_id}
                    await context.bot.send_message(chat_id, f"Please send the screenshot for task #{task_id} verification.")
            except psycopg.Error as e:
                logger.error(f"Database error in verify_task: {e}")
                await query.answer("An error occurred. Please try again.")
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
        elif data == "toggle_reminder":
            # Already handled above, but kept for consistency
            pass
        elif data == "enable_reminders":
            try:
                await cursor.execute("UPDATE users SET alarm_setting=1 WHERE chat_id=%s", (chat_id,))
                await conn.commit()
                await query.edit_message_text(
                    "✅ Daily reminders enabled!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
                )
            except psycopg.Error as e:
                logger.error(f"Database error in enable_reminders: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif data == "disable_reminders":
            try:
                await cursor.execute("UPDATE users SET alarm_setting=0 WHERE chat_id=%s", (chat_id,))
                await conn.commit()
                await query.edit_message_text(
                    "❌ Okay, daily reminders not set.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
                )
            except psycopg.Error as e:
                logger.error(f"Database error in disable_reminders: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        else:
            logger.warning(f"Unknown callback data: {data}")
            await query.edit_message_text("Unknown action. Please try again or contact @bigscottmedia.")
    except Exception as e:
        logger.error(f"Error in button_handler: {e}")
        await query.edit_message_text("An error occurred. Please try again or contact @bigscottmedia.")

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
            await update.message.reply_text("Please provide your full name:")
            user_state[chat_id] = {'expecting': 'name'}
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
            for code in codes:
                code = code.strip()
                if code:
                    await cursor.execute("INSERT INTO coupons (payment_id, code) VALUES (%s, %s)", (payment_id, code))
            await conn.commit()
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
        elif expecting == 'broadcast_message' and chat_id == ADMIN_ID:
            await cursor.execute("SELECT chat_id FROM users WHERE payment_status='registered'")
            users = await cursor.fetchall()
            for user in users:
                try:
                    await context.bot.send_message(user['chat_id'], text)
                except Exception as e:
                    logger.error(f"Failed to send broadcast to {user['chat_id']}: {e}")
            await update.message.reply_text("Broadcast sent.")
            del user_state[chat_id]
    except psycopg.Error as e:
        logger.error(f"Database error in handle_text: {e}")
        await update.message.reply_text("An error occurred. Please try again.")
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
            user_state[chat_id] = {'expecting': 'name'}
            await context.bot.send_message(chat_id, "Please provide your full name:")

async def check_coupon_payment(context: ContextTypes.DEFAULT_TYPE):
    payment_id = context.job.data['payment_id']
    try:
        await cursor.execute("SELECT status, chat_id FROM payments WHERE id=%s", (payment_id,))
        row = await cursor.fetchone()
        if row and row["status"] == 'pending_payment':
            chat_id = row["chat_id"]
            keyboard = [[InlineKeyboardButton("Payment Approval Stats", callback_data="check_approval")]]
            await context.bot.send_message(chat_id, "Your coupon payment is still being reviewed. Click below to check status:", reply_markup=InlineKeyboardMarkup(keyboard))
    except psycopg.Error as e:
        logger.error(f"Database error in check_coupon_payment: {e}")

async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    try:
        await cursor.execute("SELECT chat_id FROM users WHERE alarm_setting=1")
        user_ids = [row["chat_id"] for row in await cursor.fetchall()]
        for user_id in user_ids:
            try:
                await context.bot.send_message(user_id, "🌟 Daily Reminder: Complete your Tapify tasks to maximize your earnings!")
                await log_interaction(user_id, "daily_reminder")
            except Exception as e:
                logger.error(f"Failed to send reminder to {user_id}: {e}")
    except psycopg.Error as e:
        logger.error(f"Database error in daily_reminder: {e}")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now()
    start_time = now - datetime.timedelta(days=1)
    try:
        await cursor.execute("SELECT COUNT(*) FROM users WHERE registration_date >= %s", (start_time,))
        new_users = (await cursor.fetchone())["count"]
        await cursor.execute("""
            SELECT SUM(CASE package WHEN 'Standard' THEN 10000 WHEN 'X' THEN 14000 ELSE 0 END)
            FROM users
            WHERE approved_at >= %s AND payment_status = 'registered'
        """, (start_time,))
        reg_payments = (await cursor.fetchone())["sum"] or 0
        await cursor.execute("SELECT SUM(total_amount) FROM payments WHERE approved_at >= %s AND status = 'approved'", (start_time,))
        coupon_payments = (await cursor.fetchone())["sum"] or 0
        total_payments = reg_payments + coupon_payments
        await cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE completed_at >= %s", (start_time,))
        tasks_completed = (await cursor.fetchone())["count"]
        await cursor.execute("""
            SELECT SUM(t.reward)
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
    except psycopg.Error as e:
        logger.error(f"Database error in daily_summary: {e}")
        await context.bot.send_message(ADMIN_ID, "Error generating daily summary.")

# Menus
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
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
    except psycopg.Error as e:
        logger.error(f"Database error in show_main_menu: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

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

# ============================== START: TAP + AVIATOR ADDON ==============================
# This block adds:
#  - DB tables for Aviator
#  - API: /api/tap (Notcoin-style tapper)
#  - API: /api/aviator/* (start, cashout, close, recent)
#  - WebApp pages: /tap and /aviator (with top nav)
#  - No changes to your existing code are required beyond adding 2 keyboard buttons (see above).

# ---- Optional: constant for Aviator multiplier growth (front-end uses same k=0.00012) ----
K = 0.00012  # growth per millisecond

def _multiplier_at_ms(ms: int) -> float:
    return (1 + K) ** ms

def _sample_crash_point() -> float:
    # Exponential-like tail; min around 1.02; typical 1.1-3.0+ with rare higher spikes.
    u = random.random() or 1e-9
    lam = 1.1
    extra = -math.log(u) / lam
    crash = 1.02 + extra * 2.2
    return max(1.02, round(crash, 2))

# ================== API ENDPOINTS ==================

# --- Notcoin-style tapper: adds +0.01 per tap (adjust if you like) ---
@app.post("/api/tap")
def api_tap():
    data = request.get_json(force=True)
    chat_id = int(data.get("chat_id", 0) or 0)
    if not chat_id:
        return jsonify({"ok": False, "error": "chat_id required"}), 400
    # credit only registered users
    loop.run_until_complete(cursor.execute("UPDATE users SET balance = COALESCE(balance,0) + 0.01 WHERE chat_id=%s AND payment_status='registered'", (chat_id,)))
    loop.run_until_complete(conn.commit())
    loop.run_until_complete(cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,)))
    row = loop.run_until_complete(cursor.fetchone())
    if not row:
        return jsonify({"ok": False, "error": "user not found"}), 404
    return jsonify({"ok": True, "balance": float(row["balance"])})

# --- Aviator: start round (debits bet) ---
@app.post("/api/aviator/start")
def api_aviator_start():
    d = request.get_json(force=True)
    chat_id = int(d.get("chat_id", 0) or 0)
    bet = float(d.get("bet_amount", 0) or 0)
    if chat_id <= 0 or bet <= 0:
        return jsonify({"ok": False, "error": "invalid chat_id/bet"}), 400
    loop.run_until_complete(cursor.execute("SELECT balance, payment_status FROM users WHERE chat_id=%s", (chat_id,)))
    u = loop.run_until_complete(cursor.fetchone())
    if not u or u["payment_status"] != "registered":
        return jsonify({"ok": False, "error": "Not registered"}), 403
    if float(u["balance"] or 0) < bet:
        return jsonify({"ok": False, "error": "Insufficient balance"}), 400

    # take bet
    loop.run_until_complete(cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s", (bet, chat_id)))
    loop.run_until_complete(conn.commit())
    seed = secrets.token_hex(8)
    crash = _sample_crash_point()
    now = datetime.datetime.utcnow()
    loop.run_until_complete(cursor.execute(
        "INSERT INTO aviator_rounds(chat_id, seed, crash_point, start_time) "
        "VALUES(%s,%s,%s,%s) RETURNING id, crash_point",
        (chat_id, seed, crash, now)
    ))
    rd = loop.run_until_complete(cursor.fetchone())
    loop.run_until_complete(cursor.execute(
        "INSERT INTO aviator_plays(round_id, chat_id, bet_amount, outcome) VALUES(%s,%s,%s,'none')",
        (rd["id"], chat_id, bet)
    ))
    loop.run_until_complete(conn.commit())
    return jsonify({"ok": True, "round": {"id": rd["id"], "crash_point": float(rd["crash_point"])}})

# --- Aviator: cash out (credits payout if before crash) ---
@app.post("/api/aviator/cashout")
def api_aviator_cashout():
    d = request.get_json(force=True)
    round_id = int(d.get("round_id", 0) or 0)
    client_m = float(d.get("client_multiplier", 1.0) or 1.0)  # informative only
    if round_id <= 0:
        return jsonify({"ok": False, "error": "round_id required"}), 400

    loop.run_until_complete(cursor.execute("""
        SELECT r.id, r.chat_id, r.crash_point, r.start_time, r.status, p.bet_amount
        FROM aviator_rounds r
        JOIN aviator_plays p ON p.round_id = r.id
        WHERE r.id = %s
    """, (round_id,)))
    row = loop.run_until_complete(cursor.fetchone())
    if not row:
        return jsonify({"ok": False, "error": "Round not found"}), 404
    if row["status"] != "active":
        return jsonify({"ok": False, "error": "Round closed"}), 400

    # authoritative multiplier from server clock
    start_ms = int((datetime.datetime.utcnow() - row["start_time"]).total_seconds() * 1000)
    server_m = _multiplier_at_ms(start_ms)
    current_m = min(server_m, float(row["crash_point"]))

    if current_m >= float(row["crash_point"]) - 1e-12:
        # too late; crashed
        loop.run_until_complete(cursor.execute("UPDATE aviator_rounds SET status='crashed', end_time=NOW() WHERE id=%s", (round_id,)))
        loop.run_until_complete(cursor.execute("UPDATE aviator_plays SET outcome='lose' WHERE round_id=%s", (round_id,)))
        loop.run_until_complete(conn.commit())
        return jsonify({"ok": False, "error": f"Crashed at x{row['crash_point']:.2f}"}), 409

    payout = float(row["bet_amount"]) * current_m
    loop.run_until_complete(cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (payout, row["chat_id"])))
    loop.run_until_complete(cursor.execute(
        "UPDATE aviator_plays SET outcome='win', cashout_multiplier=%s, payout=%s WHERE round_id=%s",
        (current_m, payout, round_id)
    ))
    loop.run_until_complete(cursor.execute("UPDATE aviator_rounds SET status='cashed', end_time=NOW() WHERE id=%s", (round_id,)))
    loop.run_until_complete(conn.commit())
    return jsonify({"ok": True, "cashout_multiplier": float(current_m), "payout": float(payout)})

# --- Aviator: close (server marks crash; used when client detects crash) ---
@app.post("/api/aviator/close")
def api_aviator_close():
    d = request.get_json(force=True)
    round_id = int(d.get("round_id", 0) or 0)
    if round_id <= 0:
        return jsonify({"ok": True})
    loop.run_until_complete(cursor.execute("SELECT status FROM aviator_rounds WHERE id=%s", (round_id,)))
    r = loop.run_until_complete(cursor.fetchone())
    if r and r["status"] == "active":
        loop.run_until_complete(cursor.execute("UPDATE aviator_rounds SET status='crashed', end_time=NOW() WHERE id=%s", (round_id,)))
        loop.run_until_complete(cursor.execute("UPDATE aviator_plays SET outcome='lose' WHERE round_id=%s", (round_id,)))
        loop.run_until_complete(conn.commit())
    return jsonify({"ok": True})

# --- Aviator: last 12 crash points for chips display (per user) ---
@app.get("/api/aviator/recent/<int:chat_id>")
def api_aviator_recent(chat_id: int):
    loop.run_until_complete(cursor.execute("SELECT crash_point FROM aviator_rounds WHERE chat_id=%s ORDER BY id DESC LIMIT 12", (chat_id,)))
    return jsonify([float(r["crash_point"]) for r in loop.run_until_complete(cursor.fetchall())])

# ================== WEBAPP PAGES (TAP & AVIATOR with top nav) ==================
TAPIFY_HTML = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>Tapify — Tap Game</title>
  <style>
    body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto;background:#0b0f19;color:#fff;text-align:center}
    nav{background:#121726;padding:12px;display:flex;justify-content:center;gap:10px;position:sticky;top:0}
    nav a{color:#9fb2d0;text-decoration:none;padding:8px 14px;border-radius:10px}
    nav a.active{background:#1f263b;color:#fff}
    .card{margin:40px auto;max-width:420px;background:#121726;border-radius:20px;padding:24px;box-shadow:0 10px 30px rgba(0,0,0,.4)}
    button{margin-top:20px;background:#7c5cff;color:#fff;border:0;padding:16px 24px;font-size:20px;border-radius:16px;cursor:pointer;width:100%}
    .balance{margin-top:12px;font-size:18px}
  </style>
</head>
<body>
  <nav>
    <a href='/tap' class='active'>Tapify</a>
    <a href='/aviator'>Aviator ✈️</a>
  </nav>
  <div class='card'>
    <h2>Notcoin Tap Game</h2>
    <div id='greet'>Loading…</div>
    <div class='balance'>Balance: <span id='bal'>0.00</span></div>
    <button id='tap'>💰 Tap to Earn</button>
  </div>
<script>
const url=new URL(location.href), chat_id=url.searchParams.get('chat_id');
const balEl=document.getElementById('bal'), greet=document.getElementById('greet');
async function fetchUser(){
  const r=await fetch(`/api/tap/user/${chat_id}`);
  if(!r.ok){greet.textContent='⚠️ Registration required.';return}
  const j=await r.json();
  greet.textContent=`Welcome, @${j.username||'player'}`;
balEl.textContent=Number(j.balance||0).toFixed(2);
}
async function tap(){
  const r=await fetch('/api/tap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id})});
  const j=await r.json(); if(j.ok) balEl.textContent=Number(j.balance||0).toFixed(2);
}
document.getElementById('tap').addEventListener('click',tap);
fetchUser();
</script>
</body>
</html>"""

AVIATOR_HTML = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>Aviator ✈️</title>
  <style>
    body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto;background:#070a13;color:#e9f0ff}
    nav{background:#0f1422;padding:12px;display:flex;justify-content:center;gap:10px;position:sticky;top:0}
    nav a{color:#99a6c6;text-decoration:none;padding:8px 14px;border-radius:10px}
    nav a.active{background:#1c253a;color:#fff}
    .wrap{max-width:960px;margin:16px auto;padding:12px}
    .panel{background:#0f1422;border-radius:16px;padding:16px;margin-bottom:16px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
    button{cursor:pointer;padding:12px 18px;border-radius:12px;font-weight:bold;border:0}
    .primary{background:#ffcd4d;color:#000}
    .good{background:#00d68f;color:#021}
    .bad{background:#ff5c7a;color:#021}
    canvas{width:100%;height:340px;background:linear-gradient(180deg,#0c1224,#0a0f1d);border-radius:12px}
    .pill{display:inline-block;background:#17203a;padding:6px 10px;border-radius:999px;color:#c9d6ff;margin-right:6px}
  </style>
</head>
<body>
  <nav>
    <a href='/tap'>Tapify</a>
    <a href='/aviator' class='active'>Aviator ✈️</a>
  </nav>
  <div class='wrap'>
    <div class='panel'>
      <canvas id='stage' width='900' height='340'></canvas>
      <div style='display:flex;justify-content:space-between;margin-top:8px'>
        <div class='pill'>x<span id='mult'>1.00</span></div>
        <div class='pill'>Round: <span id='rid'>—</span></div>
        <div class='pill'>Crash: <span id='cr'>?</span></div>
        <div class='pill'>Balance: $<span id='bal'>0.00</span></div>
      </div>
    </div>
    <div class='panel'>
      <input id='bet' type='number' value='1' min='0.1' step='0.1' style='padding:10px;border-radius:10px;border:0;background:#0c1224;color:#fff'>
      <button id='start' class='primary'>Place Bet</button>
      <button id='cash' class='good' disabled>Cash Out</button>
      <button id='cancel' class='bad' disabled>Cancel</button>
      <div id='msg' style='margin-top:10px;color:#9fb2d0'></div>
      <div id='recent' style='margin-top:10px'></div>
    </div>
  </div>
<script>
const url=new URL(location.href), chat_id=url.searchParams.get('chat_id');
const balEl=document.getElementById('bal'), multEl=document.getElementById('mult'), ridEl=document.getElementById('rid'),
      crEl=document.getElementById('cr'), msg=document.getElementById('msg'), recent=document.getElementById('recent');
const canvas=document.getElementById('stage'), ctx=canvas.getContext('2d');
let round=null, startedAt=0, crashed=false, cashed=false, anim;
const k=0.00012;

function multiplierAt(ms){ return Math.pow(1+k, ms); }

function draw(ms){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  // grid
  ctx.globalAlpha=.15; ctx.strokeStyle='#3b4b7d';
  for(let i=0;i<12;i++){ ctx.beginPath(); ctx.moveTo(0,i*canvas.height/12); ctx.lineTo(canvas.width,i*canvas.height/12); ctx.stroke(); }
  ctx.globalAlpha=1;
  // path approximation
  ctx.beginPath(); ctx.strokeStyle='#ffcd4d'; ctx.lineWidth=3;
  const steps=260;
  for(let i=0;i<=steps;i++){
    const tt=ms*(i/steps), m=multiplierAt(tt);
    const x=(i/steps)*canvas.width;
    const y=canvas.height - Math.min(canvas.height-20, (m-1)*85);
    if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  }
  ctx.stroke();
  // plane marker
  const planeY=canvas.height - Math.min(canvas.height-40, (multiplierAt(ms)-1)*85);
  const planeX=Math.min(canvas.width-20, Math.max(20, (ms/20000)*canvas.width));
  ctx.fillStyle='#e9f0ff'; ctx.beginPath(); ctx.arc(planeX, planeY, 6, 0, Math.PI*2); ctx.fill();
}

function loop(){
  if(!round) return;
  const ms=performance.now()-startedAt;
  let m=multiplierAt(ms);
  multEl.textContent=m.toFixed(2);
  draw(ms);
  if(!crashed && round.crash_point && m>=round.crash_point){
    crashed=true; m=round.crash_point; msg.textContent='💥 Crashed at x'+round.crash_point.toFixed(2);
    document.getElementById('cash').disabled=true;
    document.getElementById('cancel').disabled=true;
    fetch('/api/aviator/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({round_id:round.id})});
  } else { anim=requestAnimationFrame(loop); }
}

function pill(v){ const d=document.createElement('span'); d.className='pill';
d.textContent='x'+v.toFixed(2); if(v>=2) d.style.background='#0e2c24'; return d; }

async function syncBalance(){ 
  const r=await fetch(`/api/tap/user/${chat_id}`); if(r.ok){const j=await r.json();
balEl.textContent=Number(j.balance||0).toFixed(2);} 
}

async function loadRecent(){
  const r=await fetch(`/api/aviator/recent/${chat_id}`); if(r.ok){ const a=await r.json();
recent.innerHTML=''; a.forEach(x=>recent.appendChild(pill(x))); } 
}

document.getElementById('start').onclick=async()=>{
  const bet=parseFloat(document.getElementById('bet').value||'0');
  document.getElementById('start').disabled=true;
  document.getElementById('cash').disabled=true;
  document.getElementById('cancel').disabled=true;
  const r=await fetch('/api/aviator/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id,bet_amount:bet})});
  const j=await r.json();
  if(!j.ok){ msg.textContent=j.error||'Cannot start round';
document.getElementById('start').disabled=false; return; }
  round=j.round; ridEl.textContent=round.id; startedAt=performance.now(); crashed=false;
cashed=false; crEl.textContent='?';
  msg.textContent='✈️ Flying… Tap CASH OUT anytime.';
document.getElementById('cash').disabled=false;
document.getElementById('cancel').disabled=false; syncBalance();
  document.getElementById('cancel').onclick=async()=>{ if(!round) return;
document.getElementById('cancel').disabled=true;
    const rr=await fetch('/api/aviator/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({round_id:round.id})});
    msg.textContent='Cancelled (treated as crash).'; await syncBalance();
  };
  document.getElementById('cash').onclick=async()=>{
    if(!round||crashed||cashed) return; cashed=true;
document.getElementById('cash').disabled=true;
    const ms=performance.now()-startedAt, m=multiplierAt(ms);
    const rr=await fetch('/api/aviator/cashout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({round_id:round.id,client_multiplier:m})});
    const jj=await rr.json();
    if(jj.ok){ msg.textContent='✅ Cashed at x'+jj.cashout_multiplier.toFixed(2)+' — payout $'+jj.payout.toFixed(2); crEl.textContent=round.crash_point.toFixed(2); }
    else { msg.textContent=jj.error||'Cashout failed'; }
    await syncBalance();
  };
  cancelAnimationFrame(anim); loop();
};
(async()=>{ await syncBalance(); await loadRecent(); })();
</script>
</body>
</html>"""

# ---- Routes to serve those pages ----
@app.get("/tap")
def app_tap():
    resp = app.make_response(TAPIFY_HTML)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

@app.get("/aviator")
def app_aviator():
    resp = app.make_response(AVIATOR_HTML)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

# ================================= END: TAP + AVIATOR ADDON =================================

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

async def main_async():
    global application, loop
    loop = asyncio.get_running_loop()
    await setup_db()
    application = Application.builder().token(BOT_TOKEN).build()
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("game", cmd_game))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("reset", reset_state))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("add_task", add_task))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # Add job queue tasks
    application.job_queue.run_daily(daily_reminder, time=datetime.time(hour=8, minute=0))
    application.job_queue.run_daily(daily_summary, time=datetime.time(hour=20, minute=0))
    # Log that the bot is running
    logger.info("Bot is up and running...")
    await application.initialize()
    await application.bot.set_webhook(url=WEBHOOK_URL + BOT_TOKEN)

if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.start()
    asyncio.run(main_async())
