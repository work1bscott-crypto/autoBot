import os
import logging
import secrets
import datetime
import asyncio
import json
from typing import Dict, Any
from flask import Flask, request, jsonify
from asgiref.wsgi import WsgiToAsgi
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
GROUP_LINK = os.getenv("GROUP_LINK")
SITE_LINK = os.getenv("SITE_LINK")
AI_BOOST_LINK = os.getenv("AI_BOOST_LINK")
DAILY_TASK_LINK = os.getenv("DAILY_TASK_LINK")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBAPP_BASE = os.getenv("WEBAPP_BASE")
PORT = int(os.getenv("PORT", 8080))

# Flask app
app = Flask(__name__)

# Database connection pool
conn_pool: AsyncConnectionPool = None

# Telegram application
application = None

# Database setup
async def setup_db():
    global conn_pool
    logger.info("Initializing database connection pool")
    try:
        conn_pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=10,
            open=False
        )
        await conn_pool.open()
        logger.info("Database connection pool opened successfully")
        async with conn_pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        chat_id BIGINT PRIMARY KEY,
                        username TEXT,
                        balance FLOAT DEFAULT 0.0,
                        payment_status TEXT DEFAULT 'unregistered',
                        registration_step TEXT,
                        name TEXT,
                        email TEXT,
                        phone TEXT,
                        tasks JSONB,
                        last_daily_reward TIMESTAMP
                    )
                """)
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aviator_rounds (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT,
                        seed TEXT,
                        crash_point FLOAT,
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        status TEXT
                    )
                """)
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aviator_plays (
                        id SERIAL PRIMARY KEY,
                        round_id INTEGER,
                        chat_id BIGINT,
                        bet_amount FLOAT,
                        cashout_multiplier FLOAT,
                        payout FLOAT,
                        outcome TEXT
                    )
                """)
                await conn.commit()
                logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        raise

# Helper functions for Aviator game
def _sample_crash_point() -> float:
    """Generate a random crash point for the Aviator game."""
    return max(1.0, secrets.randbelow(1000) / 100.0)

def _multiplier_at_ms(elapsed_ms: float) -> float:
    """Calculate the multiplier based on elapsed time in milliseconds."""
    return 1.0 + (elapsed_ms / 1000.0) * 0.1

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Start command received for chat_id: {update.effective_chat.id}")
    try:
        chat_id = update.effective_chat.id
        async with conn_pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
                user = await cursor.fetchone()
                logger.info(f"User lookup result: {user}")
                if user and user["payment_status"] == "registered":
                    await show_main_menu(update, context)
                else:
                    keyboard = [
                        [InlineKeyboardButton("Register", callback_data="register")],
                        [InlineKeyboardButton("How It Works", callback_data="how_it_works")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        "Welcome to Tapify! Please register to start tapping or learn how it works.",
                        reply_markup=reply_markup
                    )
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        await update.message.reply_text("An error occurred. Please try again or contact support.")
        raise

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Play Tapify", web_app={"url": f"{WEBAPP_BASE}/tap?chat_id={update.effective_chat.id}")],
        [InlineKeyboardButton("Play Aviator", web_app={"url": f"{WEBAPP_BASE}/aviator?chat_id={update.effective_chat.id}")],
        [InlineKeyboardButton("How It Works", callback_data="how_it_works")],
        [InlineKeyboardButton("Support", callback_data="support")],
        [InlineKeyboardButton("Stats", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Welcome back! Choose an option:", reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text("Welcome back! Choose an option:", reply_markup=reply_markup)

async def how_it_works(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    voice_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="main_menu")]])
    try:
        with open("voice.ogg", "rb") as voice:
            await context.bot.send_voice(
                chat_id=query.message.chat_id,
                voice=voice,
                caption="Tapify Explained 🎧",
                reply_markup=voice_markup
            )
    except FileNotFoundError:
        logger.error("voice.ogg not found")
        await query.message.reply_text("Voice explanation unavailable. Please contact support.")

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(f"For support, contact @bigscottmedia or join {GROUP_LINK}.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            balance = user["balance"] if user else 0.0
            await query.message.reply_text(f"Your balance: ${balance:.2f}")

async def reset_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    chat_id = update.effective_chat.id
    async with conn_pool.connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE users SET registration_step = NULL WHERE chat_id=%s", (chat_id,))
            await conn.commit()
    await update.message.reply_text("Registration state reset.")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        task = " ".join(context.args)
        async with conn_pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "UPDATE users SET tasks = COALESCE(tasks, '[]'::jsonb) || %s::jsonb WHERE payment_status='registered'",
                    (json.dumps([task]),)
                )
                await conn.commit()
        await update.message.reply_text(f"Task '{task}' added for all registered users.")
    except Exception as e:
        logger.error(f"Error adding task: {e}")
        await update.message.reply_text("Failed to add task.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    message = " ".join(context.args)
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT chat_id FROM users WHERE payment_status='registered'")
            users = await cursor.fetchall()
            for user in users:
                try:
                    await context.bot.send_message(chat_id=user["chat_id"], text=message)
                except Exception as e:
                    logger.error(f"Failed to send broadcast to {user['chat_id']}: {e}")
    await update.message.reply_text("Broadcast sent.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "main_menu":
        await show_main_menu(update, context)
    elif data == "how_it_works":
        await how_it_works(update, context)
    elif data == "support":
        await support(update, context)
    elif data == "stats":
        await stats(update, context)
    elif data == "register":
        async with conn_pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO users (chat_id, payment_status, registration_step) VALUES (%s, %s, %s) ON CONFLICT (chat_id) UPDATE SET registration_step = %s",
                    (query.message.chat_id, "unregistered", "name", "name")
                )
                await conn.commit()
        await query.message.reply_text("Please enter your name to register.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photos are not supported yet.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Documents are not supported yet.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT registration_step FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            if user and user["registration_step"]:
                step = user["registration_step"]
                if step == "name":
                    await cursor.execute("UPDATE users SET name=%s, registration_step='email' WHERE chat_id=%s", (text, chat_id))
                    await update.message.reply_text("Please enter your email.")
                elif step == "email":
                    await cursor.execute("UPDATE users SET email=%s, registration_step='phone' WHERE chat_id=%s", (text, chat_id))
                    await update.message.reply_text("Please enter your phone number.")
                elif step == "phone":
                    await cursor.execute(
                        "UPDATE users SET phone=%s, payment_status='registered', registration_step=NULL WHERE chat_id=%s",
                        (text, chat_id)
                    )
                    await update.message.reply_text("Registration complete! Use /menu to start.")
                await conn.commit()
            else:
                await update.message.reply_text("Please use /start to begin.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Error in chat {update.effective_chat.id}: {context.error}"
        )
        if update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again or contact @bigscottmedia.")

async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT chat_id FROM users WHERE payment_status='registered'")
            users = await cursor.fetchall()
            for user in users:
                try:
                    await context.bot.send_message(
                        chat_id=user["chat_id"],
                        text=f"Don't forget to complete your daily tasks at {DAILY_TASK_LINK}!"
                    )
                except Exception as e:
                    logger.error(f"Failed to send reminder to {user['chat_id']}: {e}")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT COUNT(*) as count, SUM(balance) as total_balance FROM users WHERE payment_status='registered'")
            stats = await cursor.fetchone()
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Daily Summary: {stats['count']} registered users, total balance ${stats['total_balance']:.2f}"
            )

async def clear_stale_user_state(context: ContextTypes.DEFAULT_TYPE):
    async with conn_pool.connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE users SET registration_step = NULL WHERE registration_step IS NOT NULL AND last_daily_reward < %s",
                (datetime.datetime.now() - datetime.timedelta(days=7),)
            )
            await conn.commit()

# Flask routes
@app.route('/')
async def home():
    return "Tapify is alive!"

@app.post(f"/{BOT_TOKEN}")
async def webhook():
    logger.info("Received webhook request")
    try:
        data = await request.get_json()
        logger.info(f"Received webhook update: {data}")
        update = Update.de_json(data, application.bot)
        logger.info(f"Parsed update: {update}")
        asyncio.create_task(application.process_update(update))
        return {"ok": true}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"ok": false, "error": str(e)}, 500

@app.get("/api/tap")
async def api_tap_get():
    data = request.args
    chat_id = int(data.get("chat_id", 0) or 0)
    if not chat_id:
        return jsonify({"ok": False, "error": "Invalid chat_id"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT balance, payment_status FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            if not user or user["payment_status"] != "registered":
                return jsonify({"ok": False, "error": "User not registered"}), 403
            return jsonify({"ok": True, "balance": user["balance"]}), 200

@app.post("/api/tap")
async def api_tap():
    data = await request.get_json(force=True)
    logger.info(f"API /tap called with data: {data}")
    chat_id = int(data.get("chat_id", 0) or 0)
    if not chat_id:
        return jsonify({"ok": False, "error": "Invalid chat_id"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            if not user or user["payment_status"] != "registered":
                return jsonify({"ok": False, "error": "User not registered"}), 403
            await cursor.execute("UPDATE users SET balance = balance + 0.01 WHERE chat_id=%s AND payment_status='registered'", (chat_id,))
            if cursor.rowcount == 0:
                return jsonify({"ok": False, "error": "User not registered"}), 403
            await cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            balance = (await cursor.fetchone())["balance"]
            await conn.commit()
    return jsonify({"ok": True, "balance": balance}), 200

@app.post("/api/aviator/start")
async def api_aviator_start():
    data = await request.get_json(force=True)
    logger.info(f"API /aviator/start called with data: {data}")
    chat_id = int(data.get("chat_id", 0) or 0)
    bet_amount = float(data.get("bet_amount", 0) or 0)
    if not chat_id or bet_amount <= 0:
        return jsonify({"ok": False, "error": "Invalid chat_id or bet_amount"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT balance, payment_status FROM users WHERE chat_id=%s", (chat_id,))
            user = await cursor.fetchone()
            if not user or user["payment_status"] != "registered":
                return jsonify({"ok": False, "error": "User not registered"}), 403
            if user["balance"] < bet_amount:
                return jsonify({"ok": False, "error": "Insufficient balance"}), 403
            await cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s", (bet_amount, chat_id))
            seed = secrets.token_hex(16)
            crash_point = _sample_crash_point()
            start_time = datetime.datetime.now()
            await cursor.execute(
                """
                INSERT INTO aviator_rounds (chat_id, seed, crash_point, start_time, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id
                """,
                (chat_id, seed, crash_point, start_time)
            )
            round_id = (await cursor.fetchone())["id"]
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
    data = await request.get_json(force=True)
    logger.info(f"API /aviator/cashout called with data: {data}")
    chat_id = int(data.get("chat_id", 0) or 0)
    round_id = int(data.get("round_id", 0) or 0)
    if not chat_id or not round_id:
        return jsonify({"ok": False, "error": "Invalid chat_id or round_id"}), 400
    async with conn_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cursor:
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
            elapsed_ms = (datetime.datetime.now() - round_data["start_time"]).total_seconds() * 1000
            current_multiplier = _multiplier_at_ms(elapsed_ms)
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
                return jsonify({
                    "ok": False,
                    "error": "Round crashed",
                    "crash_point": round_data["crash_point"]
                }), 400
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
        async with conn.cursor(row_factory=dict_row) as cursor:
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
            updateBalance();
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

async def main():
    global application
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("reset", reset_state))
    application.add_handler(CommandHandler("add_task", add_task))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.COMMAND, error_handler))
    application.add_error_handler(error_handler)

    application.job_queue.run_daily(daily_reminder, time=datetime.time(hour=8, minute=0))
    application.job_queue.run_daily(daily_summary, time=datetime.time(hour=23, minute=59))
    application.job_queue.run_repeating(clear_stale_user_state, interval=3600, first=3600)

    await setup_db()
    await application.bot.set_webhook(url=WEBHOOK_URL + BOT_TOKEN)
    logger.info(f"Webhook set to {WEBHOOK_URL + BOT_TOKEN}")

if __name__ == "__main__":
    import uvicorn
    from asgiref.wsgi import WsgiToAsgi
    asyncio.run(main())
    asgi_app = WsgiToAsgi(app)
    uvicorn.run(asgi_app, host="0.0.0.0", port=PORT)
