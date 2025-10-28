#!/usr/bin/env python3
# main.py — Tapify Main Bot for Telegram (management 3 patched)
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
#
# Start:
#   python main.py

import logging
import psycopg
import re
import time
import datetime
import os
import secrets
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from flask import Flask
from threading import Thread

# Flask setup for Render keep-alive
app = Flask('')


@app.route('/')
def home():
    return "Tapify is alive!"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.start()


# Bot credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
GROUP_LINK = os.getenv("GROUP_LINK", "")
SITE_LINK = os.getenv("SITE_LINK", "")
AI_BOOST_LINK = os.getenv("AI_BOOST_LINK", "")
DAILY_TASK_LINK = os.getenv("DAILY_TASK_LINK", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://tapify.onrender.com/app")

# Validate environment variables
if not BOT_TOKEN:
    logging.error("BOT_TOKEN is required in environment (.env)")
    raise ValueError("BOT_TOKEN is required")
if not ADMIN_ID:
    logging.error("ADMIN_ID is required in environment (.env)")
    raise ValueError("ADMIN_ID is required")

# Predefined payment accounts
PAYMENT_ACCOUNTS = {
    "Nigeria (Opay)": "󰐕 Account: 6110749592\nBank: Opay\nName: Chike Eluem Olanrewaju",
    "Nigeria (Zenith)": "󰐕 Account: 2267515466\nBank: Zenith Bank\nName: Chike Eluem Olanrewaju",
    "Nigeria (Kuda)": "󰐕 Account: 2036035854\nBank: Kuda Bank\nName: Eluem, Chike Olanrewaju",
}

# Predefined coupon payment accounts
COUPON_PAYMENT_ACCOUNTS = {
    "Coupon Acct 1 (Opay)": "󰐕 Account: 6110749592\nBank: Opay\nName: Chike Eluem Olanrewaju",
    "Coupon Acct 2 (Zenith)": "󰐕 Account: 2267515466\nBank: Zenith Bank\nName: Chike Eluem Olanrewaju",
    "Coupon Acct 3 (Kuda)": "󰐕 Account: 2036035854\nBank: Kuda Bank\nName: Eluem, Chike Olanrewaju"
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

# Database setup with PostgreSQL
try:
    import urllib.parse as urlparse

    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL must be set for PostgreSQL")
    if "sslmode=" not in url:
        if "?" in url:
            url += "&sslmode=require"
        else:
            url += "?sslmode=require"
    conn = psycopg.connect(url, row_factory=psycopg.rows.dict_row)
    conn.autocommit = True
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
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

    # Payments table (now includes is_upgrade)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            type TEXT,
            package TEXT,
            quantity INTEGER,
            total_amount INTEGER,
            payment_account TEXT,
            is_upgrade BOOLEAN DEFAULT FALSE,
            status TEXT DEFAULT 'pending_payment',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP
        )
    """)

    # Coupons table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id SERIAL PRIMARY KEY,
            payment_id INTEGER,
            code TEXT,
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
    """)

    # Interactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            action TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tasks table
    cursor.execute("""
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id BIGINT,
            task_id INTEGER,
            completed_at TIMESTAMP,
            PRIMARY KEY (user_id, task_id),
            FOREIGN KEY (user_id) REFERENCES users(chat_id),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
except psycopg.Error as e:
    logging.error(f"Database error: {e}")
    raise

# In-memory storage
user_state = {}
start_time = time.time()

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
logger = logging.getLogger(__name__)


# Helper functions
def get_status(chat_id):
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = cursor.fetchone()
        return row["payment_status"] if row else None
    except psycopg.Error as e:
        logger.error(f"Database error in get_status: {e}")
        return None


def is_registered(chat_id):
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = cursor.fetchone()
        return row and row["payment_status"] == 'registered'
    except psycopg.Error as e:
        logger.error(f"Database error in is_registered {chat_id}: {e}")
        return False


def log_interaction(chat_id, action):
    try:
        cursor.execute("INSERT INTO interactions (chat_id, action) VALUES (%s, %s)", (chat_id, action))
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
    log_interaction(chat_id, "start")
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (chat_id, username, referral_code, referred_by) VALUES (%s, %s, %s, %s)",
                (chat_id, update.effective_user.username or "Unknown", referral_code, referred_by)
            )
            if referred_by:
                cursor.execute("UPDATE users SET invites = invites + 1, balance = balance + 0.1 WHERE chat_id=%s", (referred_by,))
            conn.commit()
        keyboard = [[InlineKeyboardButton("🚀 Get Started", callback_data="menu")]]
        await update.message.reply_text(
            "Welcome to Tapify!\n\n"
            "Social Media is the new Oil Money and Tapify will help you get started mining form it.\n"
            "Get paid for using your phone and doing what you love most.\n"
            "• Read posts ➜ earn $2.5/10 words\n• Take a Walk ➜ earn $5\n"
            "• Connect with friends with streaks ➜ earn up to $20\n"
            "• Invite friends and more!\n\n"
            "Choose your package and start earning today.\nClick the button below to get started.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        reply_keyboard = [["/menu(🔙)"]]
        if is_registered(chat_id):
            reply_keyboard.append([KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?chat_id={chat_id}"))])
    except psycopg.Error as e:
        logger.error(f"Database error in start: {e}")
        await update.message.reply_text("An error occurred while accessing the database. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error in start: {e}")
        await update.message.reply_text("An unexpected error occurred. Please try again or contact @bigscottmedia.")


async def cmd_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if not is_registered(chat_id):
        await update.message.reply_text("Please complete registration to get login's to Tapify.")
        return
    kb = [[KeyboardButton(
        text="Play Tapify",
        web_app=WebAppInfo(
            url=f"{WEBAPP_URL}/?chat_id={chat_id}&username={update.effective_user.username or 'guest'}"
        )
    )]]
    await update.message.reply_text(
        "Tap to earn coins!",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {'expecting': 'support_message'}
    await update.message.reply_text("Please describe your issue or question:")
    log_interaction(chat_id, "support_initiated")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    log_interaction(chat_id, "stats")
    try:
        cursor.execute("SELECT payment_status, streaks, invites, package, balance FROM users WHERE chat_id=%s", (chat_id,))
        user = cursor.fetchone()
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
    log_interaction(chat_id, "reset_state")


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
        cursor.execute(
            "INSERT INTO tasks (type, link, reward, created_at, expires_at) VALUES (%s, %s, %s, %s, %s)",
            (task_type, link, reward, created_at, expires_at)
        )
        conn.commit()
        await update.message.reply_text("Task added successfully.")
        log_interaction(chat_id, "add_task")
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
    log_interaction(chat_id, "broadcast_initiated")


# Callback handlers
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = query.from_user.id
    logger.info(f"Received callback data: {data} from chat_id: {chat_id}")
    await query.answer()
    log_interaction(chat_id, f"button_{data}")

    try:
        if data == "menu":
            if chat_id in user_state:
                del user_state[chat_id]
            await show_main_menu(update, context)

        elif data == "stats":
            await stats(update, context)

        elif data == "refer_friend":
            cursor.execute("SELECT referral_code FROM users WHERE chat_id=%s", (chat_id,))
            row = cursor.fetchone()
            referral_code = row["referral_code"] if row else ""
            referral_link = f"https://t.me/{context.bot.username}?start=ref_{chat_id}"
            text = (
                "👥 Refer a Friend and Earn Rewards!\n\n"
                "Share your referral link with friends. For each friend who joins using your link, you earn $0.1. "
                "If they register, you earn an additional $0.4 for Lite Package or $0.9 for Pro package.\n\n"
                f"Your referral link: {referral_link}"
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))

        elif data == "withdraw":
            cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            balance = cursor.fetchone()["balance"]
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
                [InlineKeyboardButton("💎CLICK TO PROCEED!", callback_data="package_selector")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
            ]
            await query.edit_message_text(
                "🍊 HOW TAPIFY WORKS 💥\n\n"
                "Tapify rewards you for your everyday online actions — walking, gaming, sending snaps, talking to foreigners, joining forums, mining Tap coins, and engaging socially.\n"
                "Tapify also helps its users to get online or offline jobs.\n"
                "— — —\n\n"
                "📍 TAPIFY REGISTRATION PACKAGES\n"
                "• Tapify Pro: ₦15,000\n"
                "• Tapify Standard: ₦10,000\n"
                "— — —\n\n"
                "🚀 TAPIFY PRO PACKAGE\n"
                "Earning Structure:\n"
                "• 🪷 Newbie Bonus: ₦14,000\n"
                "• 🛜 Freebie: 20GB Preferred Network Data or ₦8,000 Airtime\n"
                "• 🏦 Tapify Loan: ₦50,000 – ₦1,500,000 with easy payback from your earnings and flexible payment.\n"
                "• 🏠 Tapify Homes: Verified agents for home hunts provided with 10% cost coverage by Tapify.\n"
                "• 📺 Ads Earnings: Watch ads and get paid up to $30 daily.\n"
                "• 🚀 Tapify Boost: 10× faster earning than the Standard Package.\n"
                "— — —\n\n"
                "🔥 TAPIFY STANDARD PACKAGE\n"
                "Earning Structure:\n"
                "• 🎊 Newbie Bonus: ₦8,000\n"
                "• 🛜 Freebie: 10GB Preferred Network Data or ₦5,000 Airtime\n"
                "• 📩 Engage on Forum Topics: ₦200 per engagement\n"
                "— — —\n\n"
                "📨🧡 MORE EARNING FEATURES\n"
                "• 🎥 TikTok or Snapchat Streak: ₦10,000 per streak kept\n"
                "• 🏍 Rider Earnings: ₦8,000 per delivery\n"
                "• 🚶‍♂ Step Earnings: ₦10,000 per 100 steps\n"
                "• 💬 Chat with Foreigners: Earn up to $100 in tips\n"
                "• 📤 Story Upload: ₦5,000 per approved topic\n"
                "• 🎙 Recording Earnings: ₦200 per record upload\n"
                "• 🌐 Daily Social Media Earnings: ₦5,000\n"
                "— — —\n\n"
                "💫 ADDITIONAL BENEFITS\n"
                "• 🏦 Student Loan: No collateral required\n"
                "• 🪙 Tapify Coin: Free mining for all users\n"
                "• 📄 Tap Jobs: Tapify helps users find jobs online and offline\n"
                "— — —\n\n"
                "💖 ADDITIONAL EARNINGS\n"
                "• 💰 Revenue Share: ₦13,000 – ₦9,000\n"
                "• 🔄 Indirect Bonus: ₦500 – ₦250\n"
                "• 🌀 2nd Indirect Bonus: ₦200 – ₦100\n"
                "— — —\n\n"
                "🏦 PAYMENT INFO\n"
                "• 📆 MONDAYS, WEDNESDAYS, AND FRIDAYS\n\n"
                "🎓 You’ll also be added to a mentorship class to learn how to make up to ₦300,000 weekly with the opportunities on Tapify after registration.\n"
                " Ensure to listen to the Voice Note below to understand more about our features...",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            voice_keyboard = [
                [InlineKeyboardButton("✅ I'm done listening...", callback_data="close_voice")]
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

        # Coupon package selection: now supports Standard and X
        elif data in ["coupon_standard", "coupon_x"]:
            package = "Standard" if data == "coupon_standard" else "X"
            # Price mapping: Standard = 10000, X = 15000 (per your instruction)
            price = 10000 if package == "Standard" else 15000
            quantity = user_state.get(chat_id, {}).get('coupon_quantity')
            if not quantity:
                await query.edit_message_text("Quantity not found. Please start coupon purchase again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
                return
            total = quantity * price
            user_state[chat_id].update({'coupon_package': package, 'coupon_total': total})

            await context.bot.send_message(
                ADMIN_ID,
                f"User @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}) wants to purchase {quantity} {package} coupons for ₦{total}."
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
            user_state.setdefault(chat_id, {})
            user_state[chat_id]['selected_account'] = account
            user_state[chat_id]['expecting'] = 'coupon_screenshot'
            package = user_state[chat_id].get('coupon_package')
            quantity = user_state[chat_id].get('coupon_quantity')
            total = user_state[chat_id].get('coupon_total')
            # Insert a payment row for coupon purchase (is_upgrade False)
            try:
                cursor.execute(
                    "INSERT INTO payments (chat_id, type, package, quantity, total_amount, payment_account, is_upgrade, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (chat_id, 'coupon', package, quantity, total, account, False, 'pending_payment')
                )
                payment_id = cursor.fetchone()["id"]
                conn.commit()
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
            except psycopg.Error as e:
                logger.error(f"Database error creating coupon payment: {e}")
                await query.edit_message_text("An error occurred creating payment. Please try again.")

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
            status = get_status(chat_id)
            if status == 'registered':
                await context.bot.send_message(chat_id, "You are already registered.")
                return
            # Added reg_x option (Upgrade) here
            keyboard = [
                [InlineKeyboardButton("✈Tapify Lite Package (₦10,000)", callback_data="reg_standard")],
                [InlineKeyboardButton("🚀Tapify Pro Package (₦15,000)", callback_data="reg_x")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
            ]
            await query.edit_message_text("Choose your package:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif data in ["reg_standard", "reg_x"]:
            package = "Standard" if data == "reg_standard" else "X"
            # Mark upgrade True for X
            user_state[chat_id] = {'package': package, 'upgrade': True if package == "X" else False}
            try:
                cursor.execute("UPDATE users SET package=%s, payment_status='pending_payment' WHERE chat_id=%s", (package, chat_id))
                if cursor.rowcount == 0:
                    cursor.execute("INSERT INTO users (chat_id, package, payment_status, username) VALUES (%s, %s, 'pending_payment', %s)", (chat_id, package, update.effective_user.username or "Unknown"))
                conn.commit()
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
            # set selected account and expecting screenshot
            user_state.setdefault(chat_id, {})
            user_state[chat_id]['selected_account'] = account
            user_state[chat_id]['expecting'] = 'reg_screenshot'
            # include package + upgrade marker in waiting_approval for clarity
            user_state[chat_id]['waiting_approval'] = {'type': 'registration', 'package': user_state[chat_id].get('package'), 'is_upgrade': user_state[chat_id].get('upgrade', False)}
            keyboard = [
                [InlineKeyboardButton("Change Account", callback_data="show_account_selection")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
            ]
            await context.bot.send_message(
                chat_id,
                f"Payment details:\n\n{payment_details}\n\nPlease make the payment and send the screenshot.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            # Optional: alert admin that a registration payment flow started (with upgrade tag)
            try:
                upgrade_tag = " --Upgrade" if user_state[chat_id].get('upgrade') else ""
                await context.bot.send_message(ADMIN_ID, f"User @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}) started registration for {user_state[chat_id].get('package')}{upgrade_tag}. Waiting for screenshot.")
            except Exception:
                pass

        elif data == "show_account_selection":
            package = user_state.get(chat_id, {}).get('package', '')
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

        # Approve handlers
        elif data.startswith("approve_"):
            parts = data.split("_")
            if parts[1] == "reg":
                user_chat_id = int(parts[2])
                try:
                    cursor.execute("UPDATE users SET payment_status='pending_details', approved_at=%s WHERE chat_id=%s", (datetime.datetime.now(), user_chat_id))
                    conn.commit()
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
                    cursor.execute("UPDATE payments SET status='approved', approved_at=%s WHERE id=%s", (datetime.datetime.now(), payment_id))
                    conn.commit()
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
                    cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, %s)", (user_chat_id, task_id, datetime.datetime.now()))
                    cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                    reward = cursor.fetchone()["reward"]
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, user_chat_id))
                    conn.commit()
                    await context.bot.send_message(user_chat_id, f"Task approved! You earned ${reward}.")
                    await query.edit_message_text("Task approved and reward awarded.")
                except psycopg.Error as e:
                    logger.error(f"Database error in approve_task: {e}")
                    await query.edit_message_text("An error occurred. Please try again.")

        # Reject handlers (new)
        elif data.startswith("reject_reg_"):
            user_chat_id = int(data.split("_")[2])
            try:
                cursor.execute("UPDATE users SET payment_status='rejected' WHERE chat_id=%s", (user_chat_id,))
                conn.commit()
                await context.bot.send_message(user_chat_id, "❌ Your payment was rejected by the admin. Please re-check your payment and resend a proper screenshot of your payment made to any of the provided account or contact @bigscottmedia to rectify your issues.")
                await query.edit_message_text("Payment rejected and user notified.")
            except psycopg.Error as e:
                logger.error(f"Database error in reject_reg: {e}")
                await query.edit_message_text("An error occurred while rejecting. Please try again.")

        elif data.startswith("reject_coupon_"):
            payment_id = int(data.split("_")[2])
            try:
                cursor.execute("UPDATE payments SET status='rejected' WHERE id=%s", (payment_id,))
                conn.commit()
                cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                row = cursor.fetchone()
                if row:
                    user_chat_id = row["chat_id"]
                    await context.bot.send_message(user_chat_id, "❌ Your coupon payment was rejected by the admin. Please check your payment and resend a clear screenshot or contact @bigscottmedia.")
                await query.edit_message_text("Coupon payment rejected and user notified.")
            except psycopg.Error as e:
                logger.error(f"Database error in reject_coupon: {e}")
                await query.edit_message_text("An error occurred while rejecting. Please try again.")

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
                cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (user_chat_id,))
                balance = cursor.fetchone()["balance"]
                cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                reward = cursor.fetchone()["reward"]
                if balance >= reward:
                    cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s", (reward, user_chat_id))
                    cursor.execute("DELETE FROM user_tasks WHERE user_id=%s AND task_id=%s", (user_chat_id, task_id))
                    conn.commit()
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
                    cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                    user_chat_id = cursor.fetchone()["chat_id"]
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
                status = get_status(chat_id)
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
                    cursor.execute("SELECT status FROM payments WHERE id=%s", (payment_id,))
                    status = cursor.fetchone()["status"]
                    if status == 'approved':
                        await context.bot.send_message(chat_id, "Coupon payment approved. Check your coupons above.")
                    else:
                        await context.bot.send_message(chat_id, "Your coupon payment is being reviewed.")
                except psycopg.Error as e:
                    logger.error(f"Database error in check_approval: {e}")
                    await context.bot.send_message(chat_id, "An error occurred. Please try again.")

        elif data == "toggle_reminder":
            try:
                cursor.execute("SELECT alarm_setting FROM users WHERE chat_id=%s", (chat_id,))
                current_setting = cursor.fetchone()["alarm_setting"]
                new_setting = 1 if current_setting == 0 else 0
                cursor.execute("UPDATE users SET alarm_setting=%s WHERE chat_id=%s", (new_setting, chat_id))
                conn.commit()
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
                cursor.execute("SELECT username, email, password, package FROM users WHERE chat_id=%s", (chat_id,))
                user = cursor.fetchone()
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
                cursor.execute("SELECT package FROM users WHERE chat_id=%s", (chat_id,))
                package = cursor.fetchone()["package"]
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
                cursor.execute("""
                    SELECT t.id, t.type, t.link, t.reward
                    FROM tasks t
                    WHERE t.expires_at > %s
                    AND t.id NOT IN (SELECT ut.task_id FROM user_tasks ut WHERE ut.user_id = %s)
                """, (now, chat_id))
                tasks = cursor.fetchall()
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
                cursor.execute("SELECT type, link FROM tasks WHERE id=%s", (task_id,))
                task = cursor.fetchone()
                if not task:
                    await query.answer("Task not found.")
                    return
                task_type, link = task.values()
                regel = re.compile(r'(@[A-Za-z0-9_]+)|(?:https?://)?(?:www\.)?(?:t\.me|telegram\.(?:me|dog))/([A-Za-z0-9_+]+)')
                m = regel.search(link)
                chat_username = m.group() if m else None
                if chat_username and chat_username.startswith("http"):
                    chat_username = chat_username.split("/")[-1]
                if task_type in ["join_group", "join_channel"]:
                    try:
                        member = await context.bot.get_chat_member(chat_username, chat_id)
                        if member.status in ["member", "administrator", "creator"]:
                            cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, %s)", (chat_id, task_id, datetime.datetime.now()))
                            cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                            reward = cursor.fetchone()["reward"]
                            cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, chat_id))
                            conn.commit()
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
                user_state.setdefault(chat_id, {})['expecting'] = 'faq'
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
                user_state.setdefault(chat_id, {})['expecting'] = data
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
            try:
                cursor.execute("UPDATE users SET alarm_setting=1 WHERE chat_id=%s", (chat_id,))
                conn.commit()
                await query.edit_message_text(
                    "✅ Daily reminders enabled!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]])
                )
            except psycopg.Error as e:
                logger.error(f"Database error in enable_reminders: {e}")
                await query.edit_message_text("An error occurred. Please try again.")

        elif data == "disable_reminders":
            try:
                cursor.execute("UPDATE users SET alarm_setting=0 WHERE chat_id=%s", (chat_id,))
                conn.commit()
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
        try:
            await query.edit_message_text("An error occurred. Please try again or contact @bigscottmedia.")
        except Exception:
            pass


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
            cursor.execute("UPDATE users SET screenshot_uploaded_at=%s WHERE chat_id=%s", (datetime.datetime.now(), chat_id))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_reg_{chat_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_reg_{chat_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_reg_{chat_id}")]
            ]
            # upgrade tag if present
            is_upgrade = user_state.get(chat_id, {}).get('upgrade', False) or (user_state.get(chat_id, {}).get('package') == 'X')
            upgrade_tag = " --Upgrade" if is_upgrade else ""
            await context.bot.send_photo(
                ADMIN_ID,
                file_id,
                caption=f"📸 Registration Payment from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}){upgrade_tag}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text("✅ Screenshot received! Awaiting admin approval.")
            user_state[chat_id]['waiting_approval'] = {'type': 'registration', 'is_upgrade': is_upgrade}
            context.job_queue.run_once(check_registration_payment, 3600, data={'chat_id': chat_id})
        elif expecting == 'coupon_screenshot':
            payment_id = user_state[chat_id]['waiting_approval']['payment_id']
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_coupon_{payment_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_coupon_{payment_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_coupon_{payment_id}")]
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
        # cleanup expecting key
        if 'expecting' in user_state.get(chat_id, {}):
            user_state[chat_id].pop('expecting', None)
        log_interaction(chat_id, "photo_upload")
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
            cursor.execute("UPDATE users SET screenshot_uploaded_at=%s WHERE chat_id=%s", (datetime.datetime.now(), chat_id))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_reg_{chat_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_reg_{chat_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_reg_{chat_id}")]
            ]
            is_upgrade = user_state.get(chat_id, {}).get('upgrade', False) or (user_state.get(chat_id, {}).get('package') == 'X')
            upgrade_tag = " --Upgrade" if is_upgrade else ""
            await context.bot.send_document(
                ADMIN_ID,
                file_id,
                caption=f"📸 Registration Payment from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}){upgrade_tag}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text("✅ Screenshot received! Awaiting admin approval.")
            user_state[chat_id]['waiting_approval'] = {'type': 'registration', 'is_upgrade': is_upgrade}
            context.job_queue.run_once(check_registration_payment, 3600, data={'chat_id': chat_id})
        elif expecting == 'coupon_screenshot':
            payment_id = user_state[chat_id]['waiting_approval']['payment_id']
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_coupon_{payment_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_coupon_{payment_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_coupon_{payment_id}")]
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
        if 'expecting' in user_state.get(chat_id, {}):
            user_state[chat_id].pop('expecting', None)
        log_interaction(chat_id, "document_upload")
    except Exception as e:
        logger.error(f"Error in handle_document: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text.strip()
    log_interaction(chat_id, "text_message")
    logger.info(f"user_state[{chat_id}] = {user_state.get(chat_id, 'None')}")
    if 'expecting' not in user_state.get(chat_id, {}):
        status = get_status(chat_id)
        if status == 'pending_details':
            await update.message.reply_text("Please provide your full name:")
            user_state[chat_id] = {'expecting': 'name'}
            return
    expecting = user_state.get(chat_id, {}).get('expecting')
    try:
        # Name flow
        if expecting == 'name':
            name = text
            if not name or len(name) < 2:
                await update.message.reply_text("Please provide a valid full name.")
                return
            user_state[chat_id]['name'] = name
            user_state[chat_id]['expecting'] = 'email'
            await update.message.reply_text("Please provide your email address:")

        # Email flow
        elif expecting == 'email':
            email = text
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                await update.message.reply_text("Please provide a valid email address.")
                return
            user_state[chat_id]['email'] = email
            user_state[chat_id]['expecting'] = 'phone'
            await update.message.reply_text("Please provide your phone number (with country code, e.g., +2341234567890):")

        # Phone flow
        elif expecting == 'phone':
            phone = text
            if not re.match(r"\+?\d{10,15}", phone):
                await update.message.reply_text("Please provide a valid phone number.")
                return
            user_state[chat_id]['phone'] = phone
            user_state[chat_id]['expecting'] = 'telegram_username'
            await update.message.reply_text("Please provide your Telegram username (e.g., @bigscott):")

        # Telegram handle and finalize details
        elif expecting == 'telegram_username':
            telegram_username = text
            if not re.match(r"^@[A-Za-z0-9_]{5,}$", telegram_username):
                await update.message.reply_text("Please provide a valid Telegram username starting with @ (e.g., @bigscott).")
                return
            try:
                cursor.execute(
                    "UPDATE users SET name=%s, email=%s, phone=%s, username=%s WHERE chat_id=%s",
                    (user_state[chat_id]['name'], user_state[chat_id]['email'], user_state[chat_id]['phone'], telegram_username, chat_id)
                )
                conn.commit()

                cursor.execute("SELECT package FROM users WHERE chat_id=%s", (chat_id,))
                pkg = cursor.fetchone()["package"]
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
            except psycopg.Error as e:
                logger.error(f"Database error in pending_details: {e}")
                await update.message.reply_text("An error occurred. Please try again.")

        # Coupon quantity: now shows Standard and X options
        elif expecting == 'coupon_quantity':
            try:
                quantity = int(text)
                if quantity <= 0:
                    raise ValueError
                user_state[chat_id]['coupon_quantity'] = quantity
                keyboard = [
                    [InlineKeyboardButton("Lite Package Coupons (₦10,000)", callback_data="coupon_standard")],
                    [InlineKeyboardButton("Pro Package Coupons (₦15,000)", callback_data="coupon_x")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")],
                ]
                await update.message.reply_text("Select the package for your coupons:", reply_markup=InlineKeyboardMarkup(keyboard))
                # do not keep expecting after showing options
                user_state[chat_id].pop('expecting', None)
            except ValueError:
                await update.message.reply_text("Please enter a valid positive integer.")

        # FAQ custom submission
        elif expecting == 'faq':
            await context.bot.send_message(ADMIN_ID, f"FAQ from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}): {text}")
            await update.message.reply_text("Thank you! We’ll get back to you soon.")
            del user_state[chat_id]['expecting']

        # Password recovery
        elif expecting == 'password_recovery':
            cursor.execute("SELECT username, email, password FROM users WHERE email=%s AND chat_id=%s AND payment_status='registered'", (text, chat_id))
            user = cursor.fetchone()
            if user:
                username, email, _ = user.values()
                new_password = secrets.token_urlsafe(8)
                cursor.execute("UPDATE users SET password=%s WHERE chat_id=%s", (new_password, chat_id))
                conn.commit()
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

        # Support message forwarding
        elif expecting == 'support_message':
            await context.bot.send_message(
                ADMIN_ID,
                f"Support request from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}): {text}"
            )
            await update.message.reply_text("Thank you! Our support team will get back to you soon.")
            del user_state[chat_id]['expecting']

        # Admin sending coupon codes after approval
        elif isinstance(expecting, dict) and expecting.get('type') == 'coupon_codes' and chat_id == ADMIN_ID:
            payment_id = expecting['payment_id']
            codes = text.splitlines()
            sent_codes = []
            for code in codes:
                code = code.strip()
                if code:
                    cursor.execute("INSERT INTO coupons (payment_id, code) VALUES (%s, %s)", (payment_id, code))
                    sent_codes.append(code)
            conn.commit()
            cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
            user_chat_row = cursor.fetchone()
            user_chat_id = user_chat_row["chat_id"] if user_chat_row else None
            if user_chat_id:
                await context.bot.send_message(
                    user_chat_id,
                    "🎉 Your coupon purchase is approved!\n\nHere are your coupons:\n" + "\n".join(sent_codes)
                )
            await update.message.reply_text("Coupons sent to the user successfully.")
            del user_state[chat_id]['expecting']

        # Admin sets credentials for a user
        elif expecting == 'user_credentials' and chat_id == ADMIN_ID:
            lines = text.splitlines()
            if len(lines) != 2:
                await update.message.reply_text("Please send username and password in two lines.")
                return
            username, password = lines
            for_user = user_state[chat_id]['for_user']
            cursor.execute(
                "UPDATE users SET username=%s, password=%s, payment_status='registered', registration_date=%s WHERE chat_id=%s",
                (username, password, datetime.datetime.now(), for_user)
            )
            conn.commit()
            cursor.execute("SELECT package, referred_by FROM users WHERE chat_id=%s", (for_user,))
            row = cursor.fetchone()
            if row:
                package, referred_by = row.values()
                if referred_by:
                    additional_reward = 0.4 if package == "Standard" else 0.9
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (additional_reward, referred_by))
                    conn.commit()
            await context.bot.send_message(
                for_user,
                f"🎉 Registration successful! Your username is\n {username}\n and password is\n {password}\n\n Join the group using the link below to access your Mentorship forum:\n {GROUP_LINK}"
            )
            cursor.execute("SELECT package, email, name, phone FROM users WHERE chat_id=%s", (for_user,))
            user_details = cursor.fetchone()
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
            reply_keyboard = [["/menu(🔙)"], [KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?chat_id={for_user}"))],
                              [KeyboardButton(text="Play Aviator", web_app=WebAppInfo(url=f"{WEBAPP_URL}/aviator?chat_id={chat_id}"))]]
            await context.bot.send_message(
                for_user,
                "Use the button below to engage in other processes",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )
            del user_state[chat_id]

        # Admin sending broadcast message
        elif expecting == 'broadcast_message' and chat_id == ADMIN_ID:
            message_to_send = text
            cursor.execute("SELECT chat_id FROM users WHERE payment_status IS NOT NULL")
            rows = cursor.fetchall()
            sent = 0
            for r in rows:
                try:
                    await context.bot.send_message(r["chat_id"], message_to_send)
                    sent += 1
                except Exception:
                    continue
            await update.message.reply_text(f"Broadcast sent to {sent} users.")
            del user_state[chat_id]['expecting']

    except Exception as e:
        logger.error(f"Error in handle_text: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")


# Job functions
async def check_registration_payment(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    status = get_status(chat_id)
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
        cursor.execute("SELECT status, chat_id FROM payments WHERE id=%s", (payment_id,))
        row = cursor.fetchone()
        if row and row["status"] == 'pending_payment':
            chat_id = row["chat_id"]
            keyboard = [[InlineKeyboardButton("Payment Approval Stats", callback_data="check_approval")]]
            await context.bot.send_message(chat_id, "Your coupon payment is still being reviewed. Click below to check status:", reply_markup=InlineKeyboardMarkup(keyboard))
    except psycopg.Error as e:
        logger.error(f"Database error in check_coupon_payment: {e}")


async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    try:
        cursor.execute("SELECT chat_id FROM users WHERE alarm_setting=1")
        user_ids = [row["chat_id"] for row in cursor.fetchall()]
        for user_id in user_ids:
            try:
                await context.bot.send_message(user_id, "🌟 Daily Reminder: Complete your Tapify tasks to maximize your earnings!")
                log_interaction(user_id, "daily_reminder")
            except Exception as e:
                logger.error(f"Failed to send reminder to {user_id}: {e}")
    except psycopg.Error as e:
        logger.error(f"Database error in daily_reminder: {e}")


async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now()
    start_time = now - datetime.timedelta(days=1)
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE registration_date >= %s", (start_time,))
        new_users = cursor.fetchone()["count"]
        cursor.execute("""
            SELECT SUM(CASE package WHEN 'Standard' THEN 10000 WHEN 'X' THEN 15000 ELSE 0 END)
            FROM users
            WHERE approved_at >= %s AND payment_status = 'registered'
        """, (start_time,))
        reg_payments = cursor.fetchone()["sum"] or 0
        cursor.execute("SELECT SUM(total_amount) FROM payments WHERE approved_at >= %s AND status = 'approved'", (start_time,))
        coupon_payments = cursor.fetchone()["sum"] or 0
        total_payments = reg_payments + coupon_payments
        cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE completed_at >= %s", (start_time,))
        tasks_completed = cursor.fetchone()["count"]
        cursor.execute("""
            SELECT SUM(t.reward)
            FROM user_tasks ut
            JOIN tasks t ON ut.task_id = t.id
            WHERE ut.completed_at >= %s
        """, (start_time,))
        total_distributed = cursor.fetchone()["sum"] or 0
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
    # Handles both callback_query and message commands
    if update.callback_query:
        chat_id = update.callback_query.from_user.id
    else:
        chat_id = update.effective_chat.id
    try:
        cursor.execute("SELECT payment_status, package FROM users WHERE chat_id=%s", (chat_id,))
        user = cursor.fetchone()
        # default keyboard for non-registered users
        keyboard = [
            [InlineKeyboardButton("How It Works", callback_data="how_it_works")],
            [InlineKeyboardButton("Purchase Coupon Code", callback_data="coupon")],
            [InlineKeyboardButton("💸 Get Registered Now", callback_data="package_selector")],
            [InlineKeyboardButton("🚀 Upgrade To Tapify Pro", callback_data="package_selector")],  # upgrade quick button
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
            reply_keyboard.append([KeyboardButton(text="Start Earning On Tapify", web_app=WebAppInfo(url=f"{WEBAPP_URL}?chat_id={chat_id}"))])
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            await context.bot.send_message(
                chat_id,
                "Use the buttons below to access Main Menu and Start Earning on Tapify too",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            await context.bot.send_message(
                chat_id,
                "Use the buttons below to access the Menu button or Login to your Tapify Account(Available if you're registered):",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )
        log_interaction(chat_id, "show_main_menu")
    except psycopg.Error as e:
        logger.error(f"Database error in show_main_menu: {e}")
        if update.callback_query:
            await update.callback_query.message.reply_text("An error occurred. Please try again.")
        else:
            await update.message.reply_text("An error occurred. Please try again.")


async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.callback_query.from_user.id
    status = get_status(chat_id)
    keyboard = [[InlineKeyboardButton(topic["label"], callback_data=key)] for key, topic in HELP_TOPICS.items()]
    if status == 'registered':
        keyboard.append([InlineKeyboardButton("👥 Refer a Friend", callback_data="refer_friend")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu")])
    await update.callback_query.edit_message_text("Help topics:", reply_markup=InlineKeyboardMarkup(keyboard))


# Bot startup and handler registration
def main():
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", cmd_game))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("reset_state", reset_state))
    application.add_handler(CommandHandler("add_task", add_task))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # Callback queries
    application.add_handler(CallbackQueryHandler(button_handler))

    # Message handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Jobs: simple repeating schedule; adjust times as necessary
    # run reminders every 24 hours (first run after 10 seconds), summary every 24 hours (first after 20 seconds)
    application.job_queue.run_repeating(daily_reminder, interval=86400, first=10)
    application.job_queue.run_repeating(daily_summary, interval=86400, first=20)

    # Start the bot (polling)
    application.run_polling()


if __name__ == "__main__":
    main()
