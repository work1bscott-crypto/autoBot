#!/usr/bin/env python3
# main.py — Tapify bot (merged + coupon & admin enhancements)
# Built from your uploaded Raw code....pdf with requested features added.
# Citation: source file used as base: Raw code....pdf. 1

import os
import re
import time
import secrets
import logging
import datetime
import psycopg2
import psycopg2.extras
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------- Config & env ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
DATABASE_URL = os.getenv("DATABASE_URL")  # prefer a full DATABASE_URL if available

# Additional optional envs from your original file (kept for compatibility)
GROUP_LINK = os.getenv("GROUP_LINK", "")
SITE_LINK = os.getenv("SITE_LINK", "")
AI_BOOST_LINK = os.getenv("AI_BOOST_LINK", "")
DAILY_TASK_LINK = os.getenv("DAILY_TASK_LINK", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://tapifynetwork.com/signin")

if not BOT_TOKEN:
    logging.error("BOT_TOKEN is required in environment (.env)")
    raise ValueError("BOT_TOKEN is required")
if not ADMIN_ID:
    logging.error("ADMIN_ID is required in environment (.env)")
    raise ValueError("ADMIN_ID is required")

# ---------- Logging ----------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- DB connection ----------
def get_db_conn():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        # fallback to individual env vars (host, user, password, dbname)
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            dbname=os.getenv("DB_NAME", "tapify"),
        )
    # Use RealDictCursor for dict-like fetches (so code like row["count"] works)
    conn.autocommit = False
    return conn

conn = get_db_conn()
cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ---------- Ensure tables exist (keeps compatibility with your original schema) ----------
def create_tables():
    try:
        # Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id BIGINT PRIMARY KEY,
                username TEXT,
                payment_status TEXT DEFAULT 'pending_payment',
                package TEXT,
                screenshot_uploaded_at TIMESTAMP,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                balance REAL DEFAULT 0,
                streaks INTEGER DEFAULT 0,
                invites INTEGER DEFAULT 0,
                referral_code TEXT,
                referred_by BIGINT,
                alarm_setting INT DEFAULT 0
            );
        """)
        # Payments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                total_amount REAL,
                quantity INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending_payment',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP
            );
        """)
        # Coupons
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id SERIAL PRIMARY KEY,
                payment_id INTEGER,
                code TEXT,
                sold_at TIMESTAMP,
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            );
        """)
        # Interactions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Tasks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                type TEXT,
                link TEXT,
                reward REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            );
        """)
        # User tasks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id BIGINT,
                task_id INTEGER,
                completed_at TIMESTAMP,
                PRIMARY KEY (user_id, task_id),
                FOREIGN KEY (user_id) REFERENCES users(chat_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
        """)
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Database error creating tables: {e}")
        conn.rollback()
        raise

create_tables()

# ---------- In-memory state ----------
user_state = {}  # per-chat ephemeral state (expecting values etc.)
start_time = time.time()

# ---------- Helper functions ----------
def log_interaction(chat_id: int, action: str):
    try:
        cursor.execute("INSERT INTO interactions (chat_id, action) VALUES (%s, %s)", (chat_id, action))
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Database error in log_interaction: {e}")
        conn.rollback()

def get_status(chat_id: int) -> Optional[str]:
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = cursor.fetchone()
        return row["payment_status"] if row else None
    except psycopg2.Error as e:
        logger.error(f"Database error in get_status: {e}")
        return None

def is_registered(chat_id: int) -> bool:
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = cursor.fetchone()
        return bool(row and row["payment_status"] == 'registered')
    except psycopg2.Error as e:
        logger.error(f"Database error in is_registered {chat_id}: {e}")
        return False

def generate_referral_code() -> str:
    return secrets.token_urlsafe(6)

# ---------- Command handlers & menus ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0].split("_")[1])
        except Exception:
            referred_by = None
    log_interaction(chat_id, "start")
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        if not cursor.fetchone():
            referral_code = generate_referral_code()
            cursor.execute(
                "INSERT INTO users (chat_id, username, referral_code, referred_by) VALUES (%s, %s, %s, %s)",
                (chat_id, update.effective_user.username or "Unknown", referral_code, referred_by),
            )
            if referred_by:
                cursor.execute("UPDATE users SET invites = invites + 1, balance = balance + 0.1 WHERE chat_id=%s", (referred_by,))
            conn.commit()
        # Main welcome keyboard (keeps the original UX)
        keyboard = [[InlineKeyboardButton("🚀 Get Started", callback_data="menu")]]
        await update.message.reply_text(
            "Welcome to Tapify!\n\nGet paid for using your phone and doing what you love most.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except psycopg2.Error as e:
        logger.error(f"Database error in start: {e}")
        conn.rollback()
        await update.message.reply_text("An error occurred while accessing the database. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error in start: {e}")
        await update.message.reply_text("An unexpected error occurred. Please try again or contact @bigscottmedia.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Supports both callback_query and CommandHandler-style calls
    chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.from_user.id
    try:
        cursor.execute("SELECT payment_status, package FROM users WHERE chat_id=%s", (chat_id,))
        user = cursor.fetchone()
        keyboard = [
            [InlineKeyboardButton("How It Works", callback_data="how_it_works")],
            [InlineKeyboardButton("Purchase Code", callback_data="coupon")],
            [InlineKeyboardButton("❓ Help", callback_data="help")],
        ]
        if user and user["payment_status"] == 'registered':
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                [InlineKeyboardButton("Do Daily Tasks", callback_data="daily_tasks")],
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
            await context.bot.send_message(chat_id, "Use the buttons below to access Main Menu and Start Earning on Tapify too", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            await context.bot.send_message(chat_id, "Use the buttons below to access Main Menu and Start Earning on Tapify too", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        log_interaction(chat_id, "show_main_menu")
    except psycopg2.Error as e:
        logger.error(f"Database error in show_main_menu: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.from_user.id
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
        keyboard = [[InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]] if balance >= 30 else []
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except psycopg2.Error as e:
        logger.error(f"Database error in stats: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {'expecting': 'support_message'}
    await update.message.reply_text("Please describe your issue or question:")
    log_interaction(chat_id, "support_initiated")

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
    created_at = datetime.datetime.datetime.now() if False else datetime.datetime.datetime.now()  # safe no-op (compat)
    created_at = datetime.datetime.datetime.now()  # corrected
    try:
        expires_at = created_at + datetime.timedelta(days=1)
        cursor.execute("INSERT INTO tasks (type, link, reward, created_at, expires_at) VALUES (%s, %s, %s, %s, %s)", (task_type, link, reward, created_at, expires_at))
        conn.commit()
        await update.message.reply_text("Task added successfully.")
        log_interaction(chat_id, "add_task")
    except psycopg2.Error as e:
        logger.error(f"Database error in add_task: {e}")
        conn.rollback()
        await update.message.reply_text("An error occurred. Please try again.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("This command is restricted to the admin.")
        return
    user_state[chat_id] = {'expecting': 'broadcast_message'}
    await update.message.reply_text("Please enter the broadcast message to send to all registered users:")
    log_interaction(chat_id, "broadcast_initiated")

# ---------- Admin coupon commands ----------
async def add_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("This command is restricted to the admin.")
        return
    user_state[chat_id] = {'expecting': 'add_coupons'}
    await update.message.reply_text("Please send coupon codes, one per line. When done they will be added to the pool.")
    log_interaction(chat_id, "add_coupons_initiated")

async def remove_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("This command is restricted to the admin.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /remove_coupon <code>")
        return
    code = " ".join(args).strip()
    try:
        cursor.execute("DELETE FROM coupons WHERE code=%s RETURNING id", (code,))
        row = cursor.fetchone()
        if row:
            conn.commit()
            await update.message.reply_text(f"Coupon removed: {code}")
            log_interaction(chat_id, f"remove_coupon_{code}")
        else:
            await update.message.reply_text("Coupon not found.")
    except psycopg2.Error as e:
        logger.error(f"Database error in remove_coupon: {e}")
        conn.rollback()
        await update.message.reply_text("An error occurred. Please try again.")

async def preview_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("Restricted to admin.")
        return
    try:
        cursor.execute("SELECT COUNT(*) FROM coupons WHERE payment_id IS NULL")
        available = cursor.fetchone()["count"] or 0
        cursor.execute("SELECT code FROM coupons WHERE payment_id IS NULL LIMIT 50")
        rows = cursor.fetchall()
        codes = [r["code"] for r in rows]
        msg = f"Available coupons: {available}\n"
        if codes:
            msg += "\nFirst 50 codes:\n" + "\n".join(codes)
        else:
            msg += "No available coupons."
        await update.message.reply_text(msg)
    except psycopg2.Error as e:
        logger.error(f"Database error in preview_coupons: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def coupon_sold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("Restricted to admin.")
        return
    try:
        cursor.execute("SELECT COUNT(*) FROM coupons WHERE payment_id IS NOT NULL")
        sold = cursor.fetchone()["count"] or 0
        cursor.execute("SELECT COUNT(*) FROM coupons WHERE payment_id IS NULL")
        remaining = cursor.fetchone()["count"] or 0
        await update.message.reply_text(f"Coupons sold (history): {sold}\nRemaining (available): {remaining}")
    except psycopg2.Error as e:
        logger.error(f"Database error in coupon_sold: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

# ---------- Job functions ----------
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
    except psycopg2.Error as e:
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
    except psycopg2.Error as e:
        logger.error(f"Database error in daily_reminder: {e}")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.datetime.now()
    start_time = now - datetime.timedelta(days=1)
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE registration_date >= %s", (start_time,))
        new_users = cursor.fetchone()["count"] or 0

        # registration payments sum by package (keeps your original style)
        cursor.execute("""
            SELECT SUM(CASE package WHEN 'Standard' THEN 10000 WHEN 'X' THEN 14000 ELSE 0 END) as sum
            FROM users
            WHERE approved_at >= %s AND payment_status = 'registered'
        """, (start_time,))
        reg_payments = cursor.fetchone()["sum"] or 0

        cursor.execute("SELECT SUM(total_amount) as sum FROM payments WHERE approved_at >= %s AND status = 'approved'", (start_time,))
        coupon_payments = cursor.fetchone()["sum"] or 0
        total_payments = reg_payments + coupon_payments

        cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE completed_at >= %s", (start_time,))
        tasks_completed = cursor.fetchone()["count"] or 0

        cursor.execute("""
            SELECT SUM(t.reward) as sum
            FROM user_tasks ut
            JOIN tasks t ON ut.task_id = t.id
            WHERE ut.completed_at >= %s
        """, (start_time,))
        total_distributed = cursor.fetchone()["sum"] or 0

        # NEW: start presses and active users
        cursor.execute("SELECT COUNT(*) FROM interactions WHERE action='start' AND timestamp >= %s", (start_time,))
        start_presses = cursor.fetchone()["count"] or 0

        cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM interactions WHERE timestamp >= %s", (start_time,))
        active_users = cursor.fetchone()["count"] or 0

        text = (
            f"📊 Daily Summary ({now.strftime('%Y-%m-%d')}):\n\n"
            f"• New Users: {new_users}\n"
            f"• /start presses: {start_presses}\n"
            f"• Active users (interacted): {active_users}\n"
            f"• Total Payments Approved: ₦{total_payments}\n"
            f"• Tasks Completed: {tasks_completed}\n"
            f"• Total Balance Distributed: ${total_distributed}"
        )
        await context.bot.send_message(ADMIN_ID, text)
    except psycopg2.Error as e:
        logger.error(f"Database error in daily_summary: {e}")
        await context.bot.send_message(ADMIN_ID, "Error generating daily summary.")

# ---------- Callback / button handler ----------
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

        elif data == "check_approval":
            # user clicking to check payment status
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
                except psycopg2.Error as e:
                    logger.error(f"Database error in check_approval: {e}")
                    await context.bot.send_message(chat_id, "An error occurred. Please try again.")

        elif data.startswith("approve_"):
            parts = data.split("_")
            # approve_reg_{chat_id}
            if parts[1] == "reg":
                user_chat_id = int(parts[2])
                try:
                    cursor.execute("UPDATE users SET payment_status='pending_details', approved_at=%s WHERE chat_id=%s", (datetime.datetime.datetime.now(), user_chat_id))
                    conn.commit()
                    user_state[user_chat_id] = {'expecting': 'name'}
                    await context.bot.send_message(user_chat_id, "✅ Your payment is approved!\n\nPlease provide your full name:")
                    await query.edit_message_text("Payment approved. Waiting for user details.")
                except psycopg2.Error as e:
                    logger.error(f"Database error in approve_reg: {e}")
                    conn.rollback()
                    await query.edit_message_text("An error occurred. Please try again.")

            # approve_coupon_{payment_id}
            elif parts[1] == "coupon":
                payment_id = int(parts[2])
                # NEW allocation logic: try to allocate preloaded coupons first
                try:
                    cursor.execute("SELECT chat_id, quantity FROM payments WHERE id=%s", (payment_id,))
                    payment_row = cursor.fetchone()
                    if not payment_row:
                        await query.edit_message_text("Payment record not found.")
                        return
                    user_chat_id = payment_row["chat_id"]
                    quantity = int(payment_row.get("quantity", 0) or 0)

                    # Try to select available coupons (unassigned)
                    cursor.execute("SELECT id, code FROM coupons WHERE payment_id IS NULL LIMIT %s", (quantity,))
                    available = cursor.fetchall()
                    available_count = len(available)

                    if available_count < quantity:
                        # Not enough coupons currently available
                        if available_count == 0:
                            await context.bot.send_message(ADMIN_ID, f"No available coupons for payment {payment_id}. Add coupons with /add_coupons or paste coupon codes now.")
                            user_state[ADMIN_ID] = {'expecting': {'type': 'coupon_codes', 'payment_id': payment_id}}
                            await query.edit_message_text("No available coupons. Waiting for admin to add/paste coupon codes.")
                            return
                        else:
                            await context.bot.send_message(ADMIN_ID, f"Only {available_count} coupon(s) available out of {quantity} requested for payment {payment_id}.\nYou can add more coupons (/add_coupons) or paste codes now.")
                            user_state[ADMIN_ID] = {'expecting': {'type': 'coupon_codes', 'payment_id': payment_id}}
                            await query.edit_message_text(f"Insufficient coupons ({available_count}/{quantity}). Waiting for admin input.")
                            return

                    # Enough coupons available: allocate them
                    ids = [row["id"] for row in available]
                    placeholders = ",".join(["%s"] * len(ids))
                    params = ids
                    # mark coupons as sold for this payment_id (we'll update and set sold_at)
                    now = datetime.datetime.datetime.now()
                    cursor.execute(f"UPDATE coupons SET payment_id=%s, sold_at=%s WHERE id IN ({placeholders})", tuple([payment_id, now] + params))
                    cursor.execute("UPDATE payments SET status='approved', approved_at=%s WHERE id=%s", (now, payment_id))
                    conn.commit()

                    codes = [row["code"] for row in available]
                    # Send codes to buyer
                    await context.bot.send_message(user_chat_id, "🎉 Your coupon purchase is approved!\n\nHere are your coupons:\n" + "\n".join(codes))
                    await query.edit_message_text(f"Payment approved and {len(codes)} coupon(s) sent to the user.")
                except psycopg2.Error as e:
                    logger.error(f"Database error in approve_coupon allocation: {e}")
                    conn.rollback()
                    await query.edit_message_text("An error occurred while approving the coupon payment. Please try again.")

            # approve_task flow kept from original
            elif parts[1] == "task":
                task_id = int(parts[2])
                user_chat_id = int(parts[3])
                try:
                    cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, %s)", (user_chat_id, task_id, datetime.datetime.datetime.now()))
                    cursor.execute("SELECT reward FROM tasks WHERE id=%s", (task_id,))
                    reward = cursor.fetchone()["reward"]
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, user_chat_id))
                    conn.commit()
                    await context.bot.send_message(user_chat_id, f"Task approved! You earned ${reward}.")
                    await query.edit_message_text("Task approved and reward awarded.")
                except psycopg2.Error as e:
                    logger.error(f"Database error in approve_task: {e}")
                    conn.rollback()
                    await query.edit_message_text("An error occurred. Please try again.")

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
            except psycopg2.Error as e:
                logger.error(f"Database error in reject_task: {e}")
                conn.rollback()
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
                except psycopg2.Error as e:
                    logger.error(f"Database error in pending_coupon: {e}")
                    await query.edit_message_text("An error occurred. Please try again.")

        elif data.startswith("finalize_reg_"):
            user_chat_id = int(data.split("_")[2])
            user_state[ADMIN_ID] = {'expecting': 'user_credentials', 'for_user': user_chat_id}
            await context.bot.send_message(ADMIN_ID, f"Please send the username and password for user {user_chat_id} in the format:\nusername\npassword")
            await query.edit_message_text("Waiting for user credentials.")

        # NEW: reject_reg_ and reject_coupon_ handlers
        elif data.startswith("reject_reg_"):
            user_chat_id = int(data.split("_")[2])
            try:
                cursor.execute("UPDATE users SET payment_status='declined' WHERE chat_id=%s", (user_chat_id,))
                conn.commit()
                decline_msg = ("Your payment has been declined by the Admin, please check again to ensure you made the correct transactions before you try again. "
                               "Contact @bigscottmedia for any rectification.")
                await context.bot.send_message(user_chat_id, decline_msg)
                await query.edit_message_text("Payment declined and user notified.")
                log_interaction(ADMIN_ID, f"reject_reg_{user_chat_id}")
            except psycopg2.Error as e:
                logger.error(f"Database error in reject_reg: {e}")
                conn.rollback()
                await query.edit_message_text("An error occurred. Please try again.")

        elif data.startswith("reject_coupon_"):
            payment_id = int(data.split("_")[2])
            try:
                cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                row = cursor.fetchone()
                if not row:
                    await query.edit_message_text("Payment record not found.")
                    return
                user_chat_id = row["chat_id"]
                cursor.execute("UPDATE payments SET status='declined' WHERE id=%s", (payment_id,))
                conn.commit()
                decline_msg = ("Your payment has been declined by the Admin, please check again to ensure you made the correct transactions before you try again. "
                               "Contact @bigscottmedia for any rectification.")
                await context.bot.send_message(user_chat_id, decline_msg)
                await query.edit_message_text("Coupon payment declined and user notified.")
                log_interaction(ADMIN_ID, f"reject_coupon_{payment_id}")
            except psycopg2.Error as e:
                logger.error(f"Database error in reject_coupon: {e}")
                conn.rollback()
                await query.edit_message_text("An error occurred. Please try again.")

        elif data == "toggle_reminder":
            try:
                cursor.execute("SELECT alarm_setting FROM users WHERE chat_id=%s", (chat_id,))
                current_setting = cursor.fetchone()["alarm_setting"]
                new_setting = 1 if current_setting == 0 else 0
                cursor.execute("UPDATE users SET alarm_setting=%s WHERE chat_id=%s", (new_setting, chat_id))
                conn.commit()
                status = "enabled" if new_setting == 1 else "disabled"
                await query.edit_message_text(f"Daily reminder {status}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help")]]))
            except psycopg2.Error as e:
                logger.error(f"Database error in toggle_reminder: {e}")
                conn.rollback()
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

# ---------- Message handlers ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if 'expecting' not in user_state.get(chat_id, {}):
        return
    expecting = user_state[chat_id]['expecting']
    file_id = update.message.photo[-1].file_id
    logger.info(f"Processing photo for {expecting}")
    try:
        if expecting == 'reg_screenshot' or expecting == 'reg_screenshot_document':
            cursor.execute("UPDATE users SET screenshot_uploaded_at=%s WHERE chat_id=%s", (datetime.datetime.datetime.now(), chat_id))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_reg_{chat_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_reg_{chat_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_reg_{chat_id}")],
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

        elif expecting == 'coupon_screenshot' or expecting == 'coupon_screenshot_document':
            payment_id = user_state[chat_id]['waiting_approval']['payment_id']
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_coupon_{payment_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_coupon_{payment_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_coupon_{payment_id}")],
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
            cursor.execute("UPDATE users SET screenshot_uploaded_at=%s WHERE chat_id=%s", (datetime.datetime.datetime.now(), chat_id))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_reg_{chat_id}")],
                [InlineKeyboardButton("Pending", callback_data=f"pending_reg_{chat_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_reg_{chat_id}")],
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
                [InlineKeyboardButton("Reject", callback_data=f"reject_coupon_{payment_id}")],
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

    expecting = user_state[chat_id].get('expecting')

    try:
        # Registration flow collected details
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
            try:
                cursor.execute("UPDATE users SET name=%s, email=%s, phone=%s, username=%s, payment_status='registered' WHERE chat_id=%s",
                               (user_state[chat_id]['name'], user_state[chat_id]['email'], user_state[chat_id]['phone'], telegram_username, chat_id))
                conn.commit()
                await update.message.reply_text("✅ Registration complete. Welcome aboard!")
                del user_state[chat_id]
            except psycopg2.Error as e:
                logger.error(f"Database error in finishing registration: {e}")
                conn.rollback()
                await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")
        # Admin: paste coupon codes for a specific payment (when asked to)
        elif isinstance(expecting, dict) and expecting.get('type') == 'coupon_codes' and chat_id == ADMIN_ID:
            payment_id = expecting.get('payment_id')
            codes = [line.strip() for line in text.splitlines() if line.strip()]
            if not codes:
                await update.message.reply_text("No valid codes found. Send one or more codes, each on its own line.")
                return
            try:
                now = datetime.datetime.datetime.now()
                # If called to satisfy a particular payment, attach those codes to that payment_id and send to user
                if payment_id:
                    # Insert codes tied to this payment_id and send to buyer
                    for code in codes:
                        cursor.execute("INSERT INTO coupons (payment_id, code, sold_at) VALUES (%s, %s, %s)", (payment_id, code, now))
                    cursor.execute("UPDATE payments SET status='approved', approved_at=%s WHERE id=%s", (now, payment_id))
                    cursor.execute("SELECT chat_id FROM payments WHERE id=%s", (payment_id,))
                    buyer_row = cursor.fetchone()
                    if buyer_row:
                        buyer_chat = buyer_row["chat_id"]
                        await context.bot.send_message(buyer_chat, "🎉 Your coupon purchase is approved!\n\nHere are your coupons:\n" + "\n".join(codes))
                    conn.commit()
                    await update.message.reply_text(f"Added {len(codes)} coupon(s) and assigned them to payment {payment_id}. Buyer notified.")
                    del user_state[chat_id]
                    log_interaction(chat_id, f"paste_codes_for_payment_{payment_id}")
                else:
                    # If no payment_id then treat as bulk add to pool
                    for code in codes:
                        cursor.execute("INSERT INTO coupons (code) VALUES (%s)", (code,))
                    conn.commit()
                    await update.message.reply_text(f"Added {len(codes)} coupon(s) to the pool.")
                    del user_state[chat_id]
                    log_interaction(chat_id, f"add_coupons_bulk_{len(codes)}")
            except psycopg2.Error as e:
                logger.error(f"Database error adding coupon codes: {e}")
                conn.rollback()
                await update.message.reply_text("An error occurred while adding coupon codes. Please try again.")
        # Admin: bulk add coupons (state from /add_coupons)
        elif expecting == 'add_coupons' and chat_id == ADMIN_ID:
            codes = [line.strip() for line in text.splitlines() if line.strip()]
            if not codes:
                await update.message.reply_text("No valid codes found. Send one or more codes, each on its own line.")
                return
            try:
                inserted = 0
                for code in codes:
                    cursor.execute("INSERT INTO coupons (code) VALUES (%s)", (code,))
                    inserted += 1
                conn.commit()
                await update.message.reply_text(f"Added {inserted} coupon(s) to the pool.")
                log_interaction(chat_id, f"add_coupons_added_{inserted}")
            except psycopg2.Error as e:
                logger.error(f"Database error in add_coupons: {e}")
                conn.rollback()
                await update.message.reply_text("An error occurred while adding coupons. Please try again.")
            del user_state[chat_id]
        # Broadcast
        elif expecting == 'broadcast_message' and chat_id == ADMIN_ID:
            message = text
            try:
                cursor.execute("SELECT chat_id FROM users")
                rows = cursor.fetchall()
                count = 0
                for r in rows:
                    try:
                        await context.bot.send_message(r["chat_id"], message)
                        count += 1
                    except Exception as e:
                        logger.info(f"Failed to broadcast to {r['chat_id']}: {e}")
                await update.message.reply_text(f"Broadcast sent to {count} users.")
            except psycopg2.Error as e:
                logger.error(f"Database error in broadcast: {e}")
                await update.message.reply_text("An error occurred. Please try again.")
            del user_state[chat_id]
        # Support message
        elif expecting == 'support_message':
            msg = text
            await context.bot.send_message(ADMIN_ID, f"Support message from @{update.effective_user.username or 'Unknown'} (chat_id: {chat_id}):\n\n{msg}")
            await update.message.reply_text("Thanks — your message has been sent to the admin.")
            del user_state[chat_id]
        else:
            # Fallback general text handling (keep original flows)
            await update.message.reply_text("I didn't understand that. Use /menu or press the buttons.")
    except Exception as e:
        logger.error(f"Error in handle_text: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")

# ---------- Main ----------
def main():
    from telegram.ext import Application
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", show_main_menu))
        application.add_handler(CommandHandler("game", lambda u, c: None))  # placeholder if you had cmd_game
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("reset", lambda u, c: None))  # placeholder if you had reset_state
        application.add_handler(CommandHandler("support", support))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CommandHandler("add_task", add_task))

        # New admin coupon commands
        application.add_handler(CommandHandler("add_coupons", add_coupons))
        application.add_handler(CommandHandler("remove_coupon", remove_coupon))
        application.add_handler(CommandHandler("preview_coupons", preview_coupons))
        application.add_handler(CommandHandler("coupon_sold", coupon_sold))

        # Callback query handler
        application.add_handler(CallbackQueryHandler(button_handler))

        # Message handlers
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        # Jobs
        application.job_queue.run_daily(daily_reminder, time=datetime.time(hour=8, minute=0))
        application.job_queue.run_daily(daily_summary, time=datetime.time(hour=20, minute=0))

        logger.info("Bot is up and running.")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print("Failed to start bot. Check logs for details.")

if __name__ == "__main__":
    main()
