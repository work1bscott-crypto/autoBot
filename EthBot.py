#!/usr/bin/env python3
# app.py — Merged Tapify Bot and Game Mini App for Render deployment
# Requirements:
#   pip install flask psycopg[binary] python-dotenv python-telegram-bot==20.7 requests
#
# Start:
#   python app.py
#
# Environment (.env):
#   BOT_TOKEN=your_bot_token
#   ADMIN_ID=your_admin_id
#   DATABASE_URL=postgres://user:pass@host:port/dbname
#   GROUP_LINK=your_group_link
#   SITE_LINK=your_site_link
#   AI_BOOST_LINK=your_ai_boost_link
#   DAILY_TASK_LINK=your_daily_task_link
#   WEBAPP_URL=https://yourdomain.onrender.com/app
#   BANK_ACCOUNTS=FirstBank:1234567890,GTBank:0987654321
#   FOOTBALL_API_KEY=your_football_api_key

import logging
import psycopg  # Changed from psycopg2 to psycopg3
import re
import time
import secrets
import datetime
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from pydub import AudioSegment
from flask import Flask, request, jsonify, Response
from threading import Thread
from urllib.parse import parse_qsl
from datetime import datetime, timedelta, timezone, date
from collections import deque, defaultdict
import random
import hmac
import hashlib
import json
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Config & Globals ---------------------------------------------------------

# Bot credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_LINK = os.getenv("GROUP_LINK")
SITE_LINK = os.getenv("SITE_LINK")
AI_BOOST_LINK = os.getenv("AI_BOOST_LINK")
DAILY_TASK_LINK = os.getenv("DAILY_TASK_LINK")
WEBAPP_URL = os.getenv("WEBAPP_URL")
BANK_ACCOUNTS = os.getenv("BANK_ACCOUNTS", "").strip()  # MODIFIED FOR GAME INTEGRATION
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "").strip()  # MODIFIED FOR GAME INTEGRATION

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is required in environment (.env).")
    exit(1)
if not ADMIN_ID:
    print("ERROR: ADMIN_ID is required in environment (.env).")
    exit(1)
if not BANK_ACCOUNTS:
    print("WARNING: BANK_ACCOUNTS not set; deposits may fail.")
if not FOOTBALL_API_KEY:
    print("WARNING: FOOTBALL_API_KEY not set; predictions may fail.")

# Initialize Telegram Bot
bot = Bot(token=BOT_TOKEN)
BOT_USERNAME = ""

# Flask setup
app = Flask('')

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
        "3. Wait for approval, then send details\n"
        "4. Join the group and start earning! 🎉"
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
sound = AudioSegment.from_mp3("voice.mp3")
sound.export("voice.ogg", format="ogg", codec="libopus")

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Game Web App HTML (from game code) ---------------------------------------

INDEX_HEALTH = "Tapify is alive!"

WEBAPP_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tapify</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { 
      background: radial-gradient(1200px 600px at 50% -100px, rgba(255,215,0,0.12), transparent 70%), #0b0f14; 
      font-family: 'Arial', sans-serif;
    }
    .coin {
      width: 220px; height: 220px; border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #ff4500, #8b0000);
      box-shadow: 0 0 30px rgba(255,69,0,0.6), inset 0 0 20px rgba(255,255,255,0.3);
      transition: transform 0.1s ease-in-out, box-shadow 0.3s ease;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.05); }
      100% { transform: scale(1); }
    }
    .coin:active { 
      transform: scale(0.95); 
      box-shadow: 0 0 50px rgba(255,69,0,0.8), inset 0 0 40px rgba(255,255,255,0.4); 
      animation: none;
    }
    .glow { filter: drop-shadow(0 0 20px rgba(255,69,0,0.6)); }
    .tab { 
      opacity: 0.6; 
      transition: opacity 0.3s ease, border-bottom 0.3s ease; 
    }
    .tab.active { 
      opacity: 1; 
      border-bottom: 3px solid #ff4500; 
      color: #ff4500;
    }
    .tab:hover {
      opacity: 0.9;
    }
    .lock { filter: grayscale(0.6); }
    .boostBtn, .actionBtn {
      transition: background-color 0.3s ease, transform 0.2s ease;
    }
    .boostBtn:hover, .actionBtn:hover {
      background-color: #ff4500 !important;
      transform: scale(1.05);
    }
    .particle {
      position: absolute;
      width: 10px;
      height: 10px;
      background: #ff4500;
      border-radius: 50%;
      opacity: 0;
      animation: particle-burst 1s ease-out forwards;
    }
    @keyframes particle-burst {
      0% { transform: translate(0, 0); opacity: 1; }
      100% { transform: translate(var(--dx), var(--dy)); opacity: 0; }
    }
    #balance {
      animation: balance-update 0.5s ease;
    }
    @keyframes balance-update {
      0% { transform: scale(1.2); color: #ff4500; }
      100% { transform: scale(1); color: white; }
    }
    @keyframes fly {
      0% { transform: translateY(0) rotate(45deg); }
      100% { transform: translateY(-200px) rotate(45deg); }
    }
    #plane.active {
      animation: fly 5s linear;
    }
  </style>
</head>
<body class="text-white">
  <div id="root" class="max-w-sm mx-auto px-4 pt-6 pb-24">
    <div class="flex items-center justify-between">
      <div class="text-2xl font-bold text-orange-500">Tapify Adventure</div>
      <div id="streak" class="text-sm opacity-80">🔥 Streak: 0</div>
    </div>
    <div id="locked" class="hidden mt-10 text-center">
      <div class="text-3xl font-bold mb-3">Access Locked</div>
      <div class="opacity-80 mb-6">Complete registration in the bot to start playing.</div>
      <button id="btnCheck" class="px-4 py-2 rounded-lg bg-orange-500 text-black font-semibold">Check again</button>
      <div class="mt-6 text-xs opacity-60">If this persists, close and reopen the webapp.</div>
    </div>
    <div id="game" class="mt-8">
      <div class="flex items-center justify-center relative">
        <div id="energyRing" class="relative glow">
          <div id="tapBtn" class="coin select-none flex items-center justify-center text-4xl font-extrabold text-white">TAP!</div>
        </div>
      </div>
      <div class="mt-6 text-center">
        <div id="balance" class="text-5xl font-extrabold text-orange-400">0</div>
        <div id="energy" class="mt-1 text-sm opacity-80">⚡ 0 / 0</div>
      </div>
      <div class="mt-8 grid grid-cols-6 gap-2 text-center text-sm">
        <button class="tab active py-2" data-tab="play">Play</button>
        <button class="tab py-2" data-tab="boosts">Boosts</button>
        <button class="tab py-2" data-tab="board">Leaderboard</button>
        <button class="tab py-2" data-tab="refer">Refer</button>
        <button class="tab py-2" data-tab="aviator">Aviator</button>
        <button class="tab py-2" data-tab="predict">Predict</button>
      </div>
      <div id="panelPlay" class="mt-6">
        <button id="dailyRewardBtn" class="px-4 py-2 rounded-lg bg-orange-500 text-black font-semibold w-full mb-4">Claim Daily Reward</button>
      </div>
      <div id="panelBoosts" class="hidden mt-6 space-y-3">
        <div class="bg-white/5 p-4 rounded-xl shadow-lg">
          <div class="font-semibold text-orange-400">MultiTap x2 (30m)</div>
          <div class="text-xs opacity-70 mb-2">Cost: 500</div>
          <button data-boost="multitap" class="boostBtn px-3 py-2 rounded-lg bg-orange-500 text-black w-full">Activate</button>
        </div>
        <div class="bg-white/5 p-4 rounded-xl shadow-lg">
          <div class="font-semibold text-orange-400">AutoTap (10m)</div>
          <div class="text-xs opacity-70 mb-2">Cost: 3000</div>
          <button data-boost="autotap" class="boostBtn px-3 py-2 rounded-lg bg-orange-500 text-black w-full">Activate</button>
        </div>
        <div class="bg-white/5 p-4 rounded-xl shadow-lg">
          <div class="font-semibold text-orange-400">Increase Max Energy +100</div>
          <div class="text-xs opacity-70 mb-2">Cost: 2500</div>
          <button data-boost="maxenergy" class="boostBtn px-3 py-2 rounded-lg bg-orange-500 text-black w-full">Upgrade</button>
        </div>
      </div>
      <div id="panelBoard" class="hidden mt-6">
        <div class="flex gap-2 text-sm">
          <button class="lbBtn px-3 py-1 rounded bg-white/10" data-range="day">Today</button>
          <button class="lbBtn px-3 py-1 rounded bg-white/10" data-range="week">This Week</button>
          <button class="lbBtn px-3 py-1 rounded bg-white/10" data-range="all">All Time</button>
        </div>
        <ol id="lbList" class="mt-4 space-y-2"></ol>
      </div>
      <div id="panelRefer" class="hidden mt-6">
        <div class="bg-white/5 p-4 rounded-xl shadow-lg">
          <div class="font-semibold text-orange-400 mb-1">Invite Friends & Earn!</div>
          <div class="text-xs opacity-70 mb-2">Share your link to earn bonuses.</div>
          <input id="refLink" class="w-full px-3 py-2 rounded bg-black/30 border border-white/10" readonly />
          <button id="copyRef" class="mt-2 px-3 py-2 rounded bg-orange-500 text-black w-full">Copy Link</button>
        </div>
        <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <a href="#" id="aiLink" class="text-center bg-white/5 p-3 rounded-lg shadow-lg">AI Boost Task</a>
          <a href="#" id="dailyLink" class="text-center bg-white/5 p-3 rounded-lg shadow-lg">Daily Task</a>
          <a href="#" id="groupLink" class="text-center bg-white/5 p-3 rounded-lg shadow-lg">Join Group</a>
          <a href="#" id="siteLink" class="text-center bg-white/5 p-3 rounded-lg shadow-lg">Visit Site</a>
        </div>
      </div>
      <div id="panelAviator" class="hidden mt-6">
        <div class="bg-white/5 p-4 rounded-xl shadow-lg text-center">
          <div id="plane" class="w-20 h-20 mx-auto bg-orange-500 rotate-45 mb-4"></div>
          <div id="multiplier" class="text-4xl font-bold text-orange-400">1.00x</div>
          <input id="betAmount" type="number" placeholder="Bet amount" class="w-full px-3 py-2 rounded bg-black/30 border border-white/10 mt-4" />
          <button id="placeBet" class="mt-2 px-3 py-2 rounded bg-orange-500 text-black w-full">Place Bet</button>
          <button id="cashOut" class="mt-2 px-3 py-2 rounded bg-green-500 text-black w-full hidden">Cash Out</button>
          <div class="mt-4">
            <button id="fundBtn" class="actionBtn px-3 py-1 rounded bg-blue-500 text-white">Fund Account</button>
            <button id="withdrawBtn" class="actionBtn ml-2 px-3 py-1 rounded bg-red-500 text-white">Withdraw</button>
          </div>
        </div>
      </div>
      <div id="panelPredict" class="hidden mt-6">
        <div class="bg-white/5 p-4 rounded-xl shadow-lg">
          <div class="font-semibold text-orange-400 mb-2">Football Predictions</div>
          <input id="matchSearch" class="w-full px-3 py-2 rounded bg-black/30 border border-white/10" placeholder="Search match (e.g., Arsenal vs Chelsea)" />
          <div id="matchList" class="mt-4 space-y-2"></div>
          <button id="predictBtn" class="mt-4 px-3 py-2 rounded bg-orange-500 text-black w-full">Get Prediction (500 coins)</button>
        </div>
      </div>
    </div>
  </div>
<script>
const tg = window.Telegram?.WebApp;
if (tg) tg.expand();
const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));
function setTab(name) {
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $("#panelPlay").classList.toggle("hidden", name !== "play");
  $("#panelBoosts").classList.toggle("hidden", name !== "boosts");
  $("#panelBoard").classList.toggle("hidden", name !== "board");
  $("#panelRefer").classList.toggle("hidden", name !== "refer");
  $("#panelAviator").classList.toggle("hidden", name !== "aviator");
  $("#panelPredict").classList.toggle("hidden", name !== "predict");
  if (name === "predict") loadMatches();
}
$$(".tab").forEach(b => b.addEventListener("click", () => setTab(b.dataset.tab)));
const haptics = (type = "light") => {
  try { tg?.HapticFeedback?.impactOccurred(type); } catch (e) {}
};
let USER = null;
let LOCKED = false;
let RANGE = "all";
async function api(path, body) {
  const initData = tg?.initData || "";
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.assign({ initData }, body || {}))
  });
  return await res.json();
}
async function resolveAuth() {
  const out = await api("/api/auth/resolve");
  if (!out.ok) {
    $("#locked").classList.remove("hidden");
    $("#game").classList.add("lock");
    LOCKED = true;
    return;
  }
  USER = out.user;
  LOCKED = !out.allowed;
  $("#locked").classList.toggle("hidden", out.allowed);
  $("#game").classList.toggle("lock", !out.allowed);
  $("#refLink").value = out.refLink;
  $("#aiLink").href = out.aiLink;
  $("#dailyLink").href = out.dailyLink;
  $("#groupLink").href = out.groupLink;
  $("#siteLink").href = out.siteLink;
  if (out.allowed) await refreshState();
}
$("#btnCheck").addEventListener("click", resolveAuth);
async function refreshState() {
  const out = await api("/api/state");
  if (!out.ok) return;
  $("#balance").textContent = out.coins;
  $("#energy").textContent = `⚡ ${out.energy} / ${out.max_energy}`;
  $("#streak").textContent = `🔥 Streak: ${out.daily_streak || 0}`;
}
function createParticles(x, y, count = 10) {
  for (let i = 0; i < count; i++) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.style.left = `${x}px`;
    particle.style.top = `${y}px`;
    const angle = Math.random() * 2 * Math.PI;
    const dist = Math.random() * 50 + 20;
    particle.style.setProperty('--dx', `${Math.cos(angle) * dist}px`);
    particle.style.setProperty('--dy', `${Math.sin(angle) * dist}px`);
    document.body.appendChild(particle);
    setTimeout(() => particle.remove(), 1000);
  }
}
async function doTap(e) {
  if (LOCKED) return;
  const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(12))));
  const out = await api("/api/tap", { nonce });
  if (!out.ok) {
    if (out.error) console.log(out.error);
    return;
  }
  haptics("light");
  $("#balance").textContent = out.coins;
  $("#balance").style.animation = 'balance-update 0.5s ease';
  setTimeout(() => $("#balance").style.animation = '', 500);
  $("#energy").textContent = `⚡ ${out.energy} / ${out.max_energy}`;
  const rect = $("#tapBtn").getBoundingClientRect();
  createParticles(rect.left + rect.width / 2, rect.top + rect.height / 2);
}
$("#tapBtn").addEventListener("click", doTap);
$$(".boostBtn").forEach(b => {
  b.addEventListener("click", async () => {
    const out = await api("/api/boost", { name: b.dataset.boost });
    if (out.ok) { await refreshState(); haptics("medium"); }
    else if (out.error) alert(out.error);
  });
});
$$(".lbBtn").forEach(b => {
  b.addEventListener("click", async () => {
    RANGE = b.dataset.range;
    const q = await fetch(`/api/leaderboard?range=${RANGE}`);
    const data = await q.json();
    const list = $("#lbList"); list.innerHTML = "";
    (data.items || []).forEach((r, i) => {
      const li = document.createElement("li");
      li.className = "flex justify-between bg-white/5 px-3 py-2 rounded-lg shadow-md";
      li.innerHTML = `<div>#${i+1} @${r.username || r.chat_id}</div><div>${r.score}</div>`;
      list.appendChild(li);
    });
  });
});
$("#copyRef").addEventListener("click", () => {
  navigator.clipboard.writeText($("#refLink").value);
  haptics("light");
});
$("#dailyRewardBtn").addEventListener("click", async () => {
  const out = await api("/api/daily_reward");
  if (out.ok) {
    await refreshState();
    haptics("medium");
    alert("Claimed 100 coins!");
  } else if (out.error) {
    alert(out.error);
  }
});
let aviatorInterval;
$("#placeBet").addEventListener("click", async () => {
  const amount = parseInt($("#betAmount").value);
  if (amount <= 0) return alert("Invalid bet");
  const out = await api("/api/aviator/bet", {amount});
  if (out.ok) {
    $("#placeBet").classList.add("hidden");
    $("#cashOut").classList.remove("hidden");
    $("#plane").classList.add("active");
    aviatorInterval = setInterval(updateAviator, 100);
  } else alert(out.error);
});
$("#cashOut").addEventListener("click", async () => {
  const out = await api("/api/aviator/cashout");
  if (out.ok) {
    clearInterval(aviatorInterval);
    $("#plane").classList.remove("active");
    alert(`Cashed out! Winnings: ${out.winnings}`);
    $("#cashOut").classList.add("hidden");
    $("#placeBet").classList.remove("hidden");
    await refreshState();
  } else alert(out.error);
});
async function updateAviator() {
  const out = await api("/api/aviator/state");
  if (out.ok) {
    $("#multiplier").textContent = `${out.multiplier}x`;
    if (out.crashed) {
      clearInterval(aviatorInterval);
      $("#plane").classList.remove("active");
      $("#cashOut").classList.add("hidden");
      $("#placeBet").classList.remove("hidden");
      alert("Crashed! Lost bet.");
    }
  }
}
$("#fundBtn").addEventListener("click", async () => {
  const accounts = await (await fetch("/api/deposit/accounts")).json();
  if (!accounts.ok) return alert(accounts.error);
  const bank = prompt(`Select bank account:\n${accounts.accounts.join("\n")}`);
  if (!bank) return;
  const amount = parseInt(prompt("Enter amount (min 1000 Naira):"));
  if (amount < 1000) return alert("Minimum deposit 1000 Naira");
  const out = await api("/api/deposit/request", {amount, bank});
  if (out.ok) alert(out.message);
  else alert(out.error);
});
$("#withdrawBtn").addEventListener("click", async () => {
  const amount = parseInt(prompt("Enter amount (min 50000 Naira):"));
  if (amount < 50000) return alert("Minimum withdrawal 50000 Naira");
  const out = await api("/api/aviator/withdraw", {amount});
  if (out.ok) alert(out.message);
  else alert(out.error);
});
async function loadMatches() {
  const query = $("#matchSearch").value;
  const out = await api("/api/prediction/matches", {query});
  const list = $("#matchList");
  list.innerHTML = "";
  if (!out.ok) {
    list.innerHTML = `<div class="text-red-500">${out.error}</div>`;
    return;
  }
  if (out.matches.length === 0) {
    list.innerHTML = `<div class="text-yellow-500">No matches found</div>`;
    return;
  }
  out.matches.forEach(m => {
    const div = document.createElement("div");
    div.className = "bg-white/10 p-2 rounded";
    div.innerHTML = `${m.homeTeam} vs ${m.awayTeam} (${m.date})`;
    div.dataset.matchId = m.id;
    div.addEventListener("click", () => $("#matchSearch").value = `${m.homeTeam} vs ${m.awayTeam}`);
    list.appendChild(div);
  });
}
$("#predictBtn").addEventListener("click", async () => {
  const query = $("#matchSearch").value;
  if (!query) return alert("Enter a match to predict");
  const out = await api("/api/prediction/request", {query});
  if (out.ok) {
    alert(out.prediction);
    await refreshState();
  } else alert(out.error);
});
$("#matchSearch").addEventListener("input", loadMatches);
setTab("play");
resolveAuth();
setInterval(refreshState, 4000);
</script>
</body>
</html>
"""

# --- Database Setup with PostgreSQL -------------------------------------------

try:
    import urllib.parse as urlparse

    url = os.getenv("DATABASE_URL")
    result = urlparse.urlparse(url)
    conn = psycopg.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode='require'
    )
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

    # Payments table
    cursor.execute("""
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

    # Game-related tables (MODIFIED FOR GAME INTEGRATION)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_users (
            chat_id BIGINT PRIMARY KEY,
            coins BIGINT DEFAULT 0,
            energy INT DEFAULT 500,
            max_energy INT DEFAULT 500,
            energy_updated_at TIMESTAMP,
            multitap_until TIMESTAMP,
            autotap_until TIMESTAMP,
            regen_rate_seconds INT DEFAULT 3,
            last_tap_at TIMESTAMP,
            daily_streak INT DEFAULT 0,
            last_streak_at DATE,
            last_daily_reward DATE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_taps (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            ts TIMESTAMP NOT NULL,
            delta INT NOT NULL,
            nonce TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_referrals (
            referrer BIGINT NOT NULL,
            referee BIGINT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            PRIMARY KEY (referrer, referee)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            amount BIGINT NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            amount BIGINT NOT NULL,
            bank_account TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
except psycopg.Error as e:
    logger.error(f"Database error: {e}")
    raise

# In-memory storage
user_state = {}
start_time = time.time()
aviator_games = {}  # MODIFIED FOR GAME INTEGRATION: Added for Aviator game state
_rate_windows = defaultdict(lambda: deque(maxlen=20 * 3))  # MODIFIED FOR GAME INTEGRATION
_recent_nonces = defaultdict(set)  # MODIFIED FOR GAME INTEGRATION

# --- Helper Functions --------------------------------------------------------

def get_status(chat_id):
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    except psycopg.Error as e:
        logger.error(f"Database error in get_status: {e}")
        return None

def is_registered(chat_id):
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        row = cursor.fetchone()
        return row and row[0] == 'registered'
    except psycopg.Error as e:
        logger.error(f"Database error in is_registered: {e}")
        return False

def log_interaction(chat_id, action):
    try:
        cursor.execute("INSERT INTO interactions (chat_id, action) VALUES (%s, %s)", (chat_id, action))
        conn.commit()
    except psycopg.Error as e:
        logger.error(f"Database error in log_interaction: {e}")

def generate_referral_code():
    return secrets.token_urlsafe(6)

# Game-specific helper functions (MODIFIED FOR GAME INTEGRATION)
def db_execute(query: str, params: tuple = ()):
    try:
        cursor.execute(query, params)
        conn.commit()
        logger.debug(f"DB execute: {query} with params {params}")
    except Exception as e:
        logger.error(f"DB execute failed: {query} | Error: {e}")
        raise

def db_fetchone(query: str, params: tuple = ()):
    try:
        cursor.execute(query, params)
        result = cursor.fetchone()
        logger.debug(f"DB fetchone: {query} with params {params} -> {result}")
        return result
    except Exception as e:
        logger.error(f"DB fetchone failed: {query} | Error: {e}")
        raise

def db_fetchall(query: str, params: tuple = ()):
    try:
        cursor.execute(query, params)
        result = cursor.fetchall()
        logger.debug(f"DB fetchall: {query} with params {params} -> {result}")
        return result
    except Exception as e:
        logger.error(f"DB fetchall failed: {query} | Error: {e}")
        raise

def db_now() -> datetime:
    return datetime.now(timezone.utc)

def db_date_utc() -> date:
    return db_now().date()

def upsert_user_if_missing(chat_id: int, username: str | None):
    existing = db_fetchone("SELECT chat_id FROM users WHERE chat_id = %s", (chat_id,))
    if not existing:
        db_execute("INSERT INTO users (chat_id, username, payment_status, invites) VALUES (%s,%s,%s,%s)",
                   (chat_id, username, None, 0))
    existing_g = db_fetchone("SELECT chat_id FROM game_users WHERE chat_id = %s", (chat_id,))
    if not existing_g:
        now = db_now()
        db_execute("""INSERT INTO game_users
            (chat_id, coins, energy, max_energy, energy_updated_at, regen_rate_seconds, daily_streak, last_daily_reward)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (chat_id, 0, 500, 500, now, 3, 0, None))

def add_referral_if_absent(referrer: int, referee: int):
    if referrer == referee or referee <= 0:
        return
    r = db_fetchone("SELECT 1 FROM game_referrals WHERE referrer=%s AND referee=%s", (referrer, referee))
    if r:
        return
    now = db_now()
    db_execute("INSERT INTO game_referrals (referrer, referee, created_at) VALUES (%s,%s,%s)",
               (referrer, referee, now))
    db_execute("UPDATE users SET invites=COALESCE(invites,0)+1 WHERE chat_id=%s", (referrer,))

def get_game_user(chat_id: int) -> dict:
    row = db_fetchone("SELECT * FROM game_users WHERE chat_id = %s", (chat_id,))
    if not row:
        upsert_user_if_missing(chat_id, None)
        row = db_fetchone("SELECT * FROM game_users WHERE chat_id = %s", (chat_id,))
    return row or {}

def update_game_user_fields(chat_id: int, fields: dict):
    keys = list(fields.keys())
    if not keys:
        return
    set_clause = ", ".join(f"{k}=%s" for k in keys)
    params = tuple(fields[k] for k in keys) + (chat_id,)
    db_execute(f"UPDATE game_users SET {set_clause} WHERE chat_id=%s", params)

def add_tap(chat_id: int, delta: int, nonce: str):
    now = db_now()
    db_execute("INSERT INTO game_taps (chat_id, ts, delta, nonce) VALUES (%s,%s,%s,%s)",
               (chat_id, now, delta, nonce))
    db_execute("UPDATE game_users SET coins=COALESCE(coins,0)+%s, last_tap_at=%s WHERE chat_id=%s",
               (delta, now, chat_id))

def leaderboard(range_: str = "all", limit: int = 50):
    if range_ == "all":
        q = "SELECT u.username, g.chat_id, g.coins AS score FROM game_users g LEFT JOIN users u ON u.chat_id=g.chat_id ORDER BY score DESC LIMIT %s"
        return db_fetchall(q, (limit,))
    else:
        now = db_now()
        if range_ == "day":
            since = now - timedelta(days=1)
        else:
            since = now - timedelta(days=7)
        q = """
            SELECT u.username, t.chat_id, COALESCE(SUM(t.delta),0) AS score
            FROM game_taps t
            LEFT JOIN users u ON u.chat_id=t.chat_id
            WHERE t.ts >= %s
            GROUP BY t.chat_id, u.username
            ORDER BY score DESC
            LIMIT %s
        """
        return db_fetchall(q, (since, limit))

def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()

def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    try:
        items = dict(parse_qsl(init_data, strict_parsing=True))
        provided_hash = items.pop("hash", "")
        pairs = []
        for k in sorted(items.keys()):
            pairs.append(f"{k}={items[k]}")
        data_check_string = "\n".join(pairs).encode("utf-8")
        secret_key = _hmac_sha256(bot_token.encode("utf-8"), b"WebAppData")
        calc_hash = hmac.new(secret_key, data_check_string, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc_hash, provided_hash):
            return None
        user_payload = {}
        if "user" in items:
            user_payload = json.loads(items["user"])
        return {
            "ok": True,
            "user": user_payload,
            "query": items
        }
    except Exception as e:
        logger.warning("verify_init_data error: %s", e)
        return None

def _resolve_user_from_init(init_data: str) -> tuple[bool, dict | None, str]:
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return False, None, "Invalid auth"
    tg_user = auth["user"]
    chat_id = int(tg_user.get("id"))
    username = tg_user.get("username")
    upsert_user_if_missing(chat_id, username)
    return True, {"chat_id": chat_id, "username": username}, ""

MAX_TAPS_PER_SEC = 20
RATE_WINDOW_SEC = 1.0

def _clean_old_nonces(chat_id: int):
    s = _recent_nonces[chat_id]
    if len(s) > 200:
        _recent_nonces[chat_id] = set(list(s)[-100:])

def can_tap_now(chat_id: int) -> bool:
    now = time.monotonic()
    dq = _rate_windows[chat_id]
    while dq and now - dq[0] > RATE_WINDOW_SEC:
        dq.popleft()
    if len(dq) >= MAX_TAPS_PER_SEC:
        return False
    dq.append(now)
    return True

def compute_energy(user_row: dict) -> tuple[int, datetime]:
    max_energy = int(user_row.get("max_energy") or 500)
    regen_rate_seconds = int(user_row.get("regen_rate_seconds") or 3)
    raw = user_row.get("energy_updated_at")
    if isinstance(raw, str):
        try:
            last = datetime.fromisoformat(raw)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception:
            last = db_now()
    else:
        last = raw or db_now()
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    stored_energy = int(user_row.get("energy") or 0)
    now = db_now()
    elapsed = int((now - last).total_seconds())
    regen = elapsed // max(1, regen_rate_seconds)
    energy = min(max_energy, stored_energy + regen)
    if regen > 0:
        last = last + timedelta(seconds=regen * regen_rate_seconds)
    return energy, last

def streak_update(gu: dict, tapped_today: bool) -> tuple[int, date]:
    today = db_date_utc()
    last_str = gu.get("last_streak_at")
    last_date = None
    if isinstance(last_str, str) and last_str:
        try:
            last_date = datetime.fromisoformat(last_str).date()
        except Exception:
            last_date = None
    elif isinstance(last_str, datetime):
        last_date = last_str.date()
    elif isinstance(last_str, date):
        last_date = last_str
    streak = int(gu.get("daily_streak") or 0)
    if not tapped_today:
        return streak, last_date or today
    if last_date == today - timedelta(days=1):
        streak += 1
    elif last_date == today:
        pass
    else:
        streak = 1
    return streak, today

def boost_multiplier(gu: dict) -> int:
    mult = 1
    mt = gu.get("multitap_until")
    at = gu.get("autotap_until")
    now = db_now()
    if isinstance(mt, str) and mt:
        try: mt = datetime.fromisoformat(mt)
        except: mt = None
    if isinstance(at, str) and at:
        try: at = datetime.fromisoformat(at)
        except: at = None
    if isinstance(mt, datetime) and mt.replace(tzinfo=timezone.utc) > now:
        mult = max(mult, 2)
    if isinstance(at, datetime) and at.replace(tzinfo=timezone.utc) > now:
        mult = max(mult, 2)
    return mult

def activate_boost(chat_id: int, boost: str) -> tuple[bool, str]:
    gu = get_game_user(chat_id)
    coins = int(gu.get("coins") or 0)
    now = db_now()
    cost = 0
    field = None
    duration = timedelta(minutes=15)
    if boost == "multitap":
        cost = 500
        field = "multitap_until"
        duration = timedelta(minutes=30)
    elif boost == "autotap":
        cost = 3000
        field = "autotap_until"
        duration = timedelta(minutes=10)
    elif boost == "maxenergy":
        cost = 2500
        if coins < cost:
            return False, "Not enough coins"
        update_game_user_fields(chat_id, {
            "coins": coins - cost,
            "max_energy": int(gu.get("max_energy") or 500) + 100
        })
        return True, "Max energy increased by +100!"
    else:
        return False, "Unknown boost"
    if coins < cost:
        return False, "Not enough coins"
    until = now + duration
    update_game_user_fields(chat_id, {
        "coins": coins - cost,
        field: until
    })
    return True, f"{boost} activated!"

def generate_crash_point():
    seed = str(random.randint(0, 1000000))
    random.seed(seed)
    return 1 / random.random()

def get_aviator_multiplier(start_time):
    elapsed = time.time() - start_time
    return 1 + (elapsed / 2)

def get_football_matches():
    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        response = requests.get("https://api.football-data.org/v4/matches", headers=headers)
        if response.status_code != 200:
            logger.error(f"Football API failed: {response.status_code} {response.text}")
            return []
        data = response.json()
        matches = []
        for match in data.get("matches", []):
            matches.append({
                "id": match["id"],
                "homeTeam": match["homeTeam"]["name"],
                "awayTeam": match["awayTeam"]["name"],
                "date": match["utcDate"],
                "status": match["status"]
            })
        return matches
    except Exception as e:
        logger.error(f"Football API error: {e}")
        return []

def search_matches(query: str):
    matches = get_football_matches()
    query = query.lower().strip()
    if not query:
        return matches[:10]
    return [m for m in matches if query in m["homeTeam"].lower() or query in m["awayTeam"].lower()]

def generate_prediction(match_id):
    return f"Prediction for match {match_id}: 60% chance of home team win"

# --- Flask Routes ------------------------------------------------------------

@app.route('/')
def home():
    return Response(INDEX_HEALTH, mimetype="text/plain")

@app.route('/app')
def app_page():
    return Response(WEBAPP_HTML, mimetype="text/html")

@app.route('/api/auth/resolve', methods=['POST'])
def api_auth_resolve():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    ok, user, err = _resolve_user_from_init(init_data)
    if not ok:
        return jsonify({"ok": False, "error": err})
    chat_id = user["chat_id"]
    allowed = is_registered(chat_id)
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{chat_id}" if BOT_USERNAME else ""
    return jsonify({
        "ok": True,
        "user": user,
        "allowed": allowed,
        "refLink": ref_link,
        "aiLink": AI_BOOST_LINK,
        "dailyLink": DAILY_TASK_LINK,
        "groupLink": GROUP_LINK,
        "siteLink": SITE_LINK,
    })

@app.route('/api/state', methods=['POST'])
def api_state():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    gu = get_game_user(chat_id)
    energy, energy_ts = compute_energy(gu)
    out = {
        "ok": True,
        "coins": int(gu.get("coins") or 0),
        "energy": energy,
        "max_energy": int(gu.get("max_energy") or 500),
        "daily_streak": int(gu.get("daily_streak") or 0),
    }
    update_game_user_fields(chat_id, {"energy": energy, "energy_updated_at": energy_ts})
    return jsonify(out)

@app.route('/api/boost', methods=['POST'])
def api_boost():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    name = data.get("name", "")
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    ok, msg = activate_boost(chat_id, name)
    return jsonify({"ok": ok, "error": None if ok else msg})

@app.route('/api/tap', methods=['POST'])
def api_tap():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    nonce = data.get("nonce", "")
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    if not can_tap_now(chat_id):
        return jsonify({"ok": False, "error": "Rate limited"})
    if not nonce or len(nonce) > 200:
        return jsonify({"ok": False, "error": "Bad nonce"})
    if nonce in _recent_nonces[chat_id]:
        return jsonify({"ok": False, "error": "Replay blocked"})
    _recent_nonces[chat_id].add(nonce)
    _clean_old_nonces(chat_id)
    gu = get_game_user(chat_id)
    energy, energy_ts = compute_energy(gu)
    if energy < 1:
        return jsonify({"ok": False, "error": "No energy", "coins": int(gu.get("coins") or 0),
                        "energy": energy, "max_energy": int(gu.get("max_energy") or 500)})
    mult = boost_multiplier(gu)
    delta = 2 * mult
    add_tap(chat_id, delta, nonce)
    update_game_user_fields(chat_id, {"energy": energy - 1, "energy_updated_at": energy_ts})
    new_streak, streak_date = streak_update(gu, tapped_today=True)
    update_game_user_fields(chat_id, {"daily_streak": new_streak, "last_streak_at": streak_date})
    gu2 = get_game_user(chat_id)
    energy2, _ = compute_energy(gu2)
    return jsonify({
        "ok": True,
        "coins": int(gu2.get("coins") or 0),
        "energy": energy2,
        "max_energy": int(gu2.get("max_energy") or 500),
    })

@app.route('/api/daily_reward', methods=['POST'])
def api_daily_reward():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    gu = get_game_user(chat_id)
    last_reward = gu.get("last_daily_reward")
    today = db_date_utc()
    if last_reward and (isinstance(last_reward, str) and last_reward == today.isoformat() or
                        isinstance(last_reward, date) and last_reward == today):
        return jsonify({"ok": False, "error": "Already claimed today"})
    coins = int(gu.get("coins") or 0) + 100
    update_game_user_fields(chat_id, {"coins": coins, "last_daily_reward": today})
    return jsonify({"ok": True, "coins": coins})

@app.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    rng = request.args.get("range", "all")
    if rng not in ("day", "week", "all"):
        rng = "all"
    items = leaderboard(rng, 50)
    return jsonify({"ok": True, "items": items})

@app.route('/api/aviator/bet', methods=['POST'])
def api_aviator_bet():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    bet_amount = data.get("amount", 0)
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    gu = get_game_user(chat_id)
    coins = int(gu.get("coins") or 0)
    if bet_amount <= 0 or bet_amount > coins:
        return jsonify({"ok": False, "error": "Invalid bet"})
    update_game_user_fields(chat_id, {"coins": coins - bet_amount})
    crash_point = generate_crash_point()
    aviator_games[chat_id] = {'bet': bet_amount, 'start_time': time.time(), 'cashed_out': False, 'crash_point': crash_point}
    return jsonify({"ok": True, "started": True})

@app.route('/api/aviator/state', methods=['POST'])
def api_aviator_state():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if chat_id not in aviator_games:
        return jsonify({"ok": True, "active": False})
    game = aviator_games[chat_id]
    multiplier = get_aviator_multiplier(game['start_time'])
    crashed = multiplier >= game['crash_point']
    if crashed and not game['cashed_out']:
        del aviator_games[chat_id]
        return jsonify({"ok": True, "active": False, "crashed": True, "winnings": 0})
    return jsonify({"ok": True, "active": True, "multiplier": round(multiplier, 2), "crashed": crashed})

@app.route('/api/aviator/cashout', methods=['POST'])
def api_aviator_cashout():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if chat_id not in aviator_games:
        return jsonify({"ok": False, "error": "No active game"})
    game = aviator_games[chat_id]
    if game['cashed_out']:
        return jsonify({"ok": False, "error": "Already cashed out"})
    multiplier = get_aviator_multiplier(game['start_time'])
    if multiplier >= game['crash_point']:
        del aviator_games[chat_id]
        return jsonify({"ok": False, "error": "Crashed", "winnings": 0})
    winnings = int(game['bet'] * multiplier)
    gu = get_game_user(chat_id)
    coins = int(gu.get("coins") or 0) + winnings
    update_game_user_fields(chat_id, {"coins": coins})
    game['cashed_out'] = True
    del aviator_games[chat_id]
    return jsonify({"ok": True, "winnings": winnings})

@app.route('/api/aviator/withdraw', methods=['POST'])
def api_aviator_withdraw():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    amount = data.get("amount", 0)
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    if amount < 50000:
        return jsonify({"ok": False, "error": "Minimum withdrawal 50,000 Naira"})
    gu = get_game_user(chat_id)
    coins = int(gu.get("coins") or 0)
    if amount > coins:
        return jsonify({"ok": False, "error": "Insufficient balance"})
    db_execute("INSERT INTO withdrawals (chat_id, amount) VALUES (%s, %s)", (chat_id, amount))
    try:
        bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Withdrawal request from @{auth['user'].get('username', chat_id)}: {amount} Naira",
        )
    except Exception as e:
        logger.error(f"Failed to notify admin for withdrawal {chat_id}: {e}")
    return jsonify({"ok": True, "message": "Withdrawal requested, awaiting approval"})

@app.route('/api/deposit/accounts', methods=['GET'])
def api_deposit_accounts():
    if not BANK_ACCOUNTS:
        return jsonify({"ok": False, "error": "No bank accounts configured"})
    accounts = [acc.strip() for acc in BANK_ACCOUNTS.split(",")]
    return jsonify({"ok": True, "accounts": accounts})

@app.route('/api/deposit/request', methods=['POST'])
def api_deposit_request():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    amount = data.get("amount", 0)
    bank_account = data.get("bank", "").strip()
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    if amount < 1000:
        return jsonify({"ok": False, "error": "Minimum deposit 1000 Naira"})
    accounts = [acc.strip() for acc in BANK_ACCOUNTS.split(",")]
    if bank_account not in accounts:
        return jsonify({"ok": False, "error": "Invalid bank account"})
    db_execute("INSERT INTO deposits (chat_id, amount, bank_account) VALUES (%s, %s, %s)", 
               (chat_id, amount, bank_account))
    deposit_id = db_fetchone("SELECT id FROM deposits WHERE chat_id = %s ORDER BY requested_at DESC LIMIT 1", (chat_id,))["id"]
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"deposit_approve_{deposit_id}_{chat_id}_{amount}"),
            InlineKeyboardButton("Reject", callback_data=f"deposit_reject_{deposit_id}_{chat_id}")
        ]
    ])
    try:
        bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Deposit request from @{auth['user'].get('username', chat_id)}: {amount} Naira to {bank_account}",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Failed to notify admin for deposit {chat_id}: {e}")
    return jsonify({"ok": True, "message": "Deposit requested, please make payment and await approval"})

@app.route('/api/deposit/approve', methods=['POST'])
def api_deposit_approve():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    deposit_id = data.get("deposit_id", 0)
    chat_id = data.get("chat_id", 0)
    amount = data.get("amount", 0)
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user") or int(auth["user"]["id"]) != ADMIN_ID:
        return jsonify({"ok": False, "error": "Unauthorized"})
    deposit = db_fetchone("SELECT * FROM deposits WHERE id = %s AND chat_id = %s AND status = 'pending'", 
                         (deposit_id, chat_id))
    if not deposit:
        return jsonify({"ok": False, "error": "Invalid or already processed deposit"})
    gu = get_game_user(chat_id)
    coins = int(gu.get("coins") or 0) + amount
    db_execute("UPDATE deposits SET status = 'approved' WHERE id = %s", (deposit_id,))
    update_game_user_fields(chat_id, {"coins": coins})
    db_execute("UPDATE users SET payment_status = 'registered' WHERE chat_id = %s", (chat_id,))
    try:
        bot.send_message(
            chat_id=chat_id,
            text=f"Your deposit of {amount} Naira has been approved! Balance updated."
        )
    except Exception as e:
        logger.error(f"Failed to notify user {chat_id} for deposit approval: {e}")
    return jsonify({"ok": True})

@app.route('/api/deposit/reject', methods=['POST'])
def api_deposit_reject():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    deposit_id = data.get("deposit_id", 0)
    chat_id = data.get("chat_id", 0)
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user") or int(auth["user"]["id"]) != ADMIN_ID:
        return jsonify({"ok": False, "error": "Unauthorized"})
    deposit = db_fetchone("SELECT * FROM deposits WHERE id = %s AND chat_id = %s AND status = 'pending'", 
                         (deposit_id, chat_id))
    if not deposit:
        return jsonify({"ok": False, "error": "Invalid or already processed deposit"})
    db_execute("UPDATE deposits SET status = 'rejected' WHERE id = %s", (deposit_id,))
    try:
        bot.send_message(
            chat_id=chat_id,
            text="Your deposit request was rejected. Please contact support."
        )
    except Exception as e:
        logger.error(f"Failed to notify user {chat_id} for deposit rejection: {e}")
    return jsonify({"ok": True})

@app.route('/api/prediction/matches', methods=['POST'])
def api_prediction_matches():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    query = data.get("query", "").strip()
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    matches = search_matches(query)
    return jsonify({"ok": True, "matches": matches})

@app.route('/api/prediction/request', methods=['POST'])
def api_prediction_request():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    query = data.get("query", "").strip()
    auth = verify_init_data(init_data, BOT_TOKEN)
    if not auth or not auth.get("user"):
        return jsonify({"ok": False, "error": "Invalid auth"})
    chat_id = int(auth["user"]["id"])
    if not is_registered(chat_id):
        return jsonify({"ok": False, "error": "Not registered"})
    gu = get_game_user(chat_id)
    coins = int(gu.get("coins") or 0)
    if coins < 500:
        return jsonify({"ok": False, "error": "Need 500 coins for prediction"})
    matches = search_matches(query)
    if not matches:
        return jsonify({"ok": False, "error": "Match not available"})
    match = matches[0]
    update_game_user_fields(chat_id, {"coins": coins - 500})
    prediction = generate_prediction(match["id"])
    return jsonify({"ok": True, "prediction": prediction})

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- Command Handlers --------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    referral_code = generate_referral_code()
    args = context.args
    referred_by = None
    if args and args[0].startswith("ref_"):
        referred_by = int(args[0].split("_")[1])
    log_interaction(chat_id, "start")
    try:
        cursor.execute("SELECT payment_status FROM users WHERE chat_id=%s", (chat_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (chat_id, username, referral_code, referred_by) VALUES (%s, %s, %s, %s)",
                (chat_id, update.effective_user.username or "Unknown", referral_code, referred_by)
            )
            conn.commit()
            if referred_by:
                cursor.execute("UPDATE users SET invites = invites + 1, balance = balance + 0.1 WHERE chat_id=%s", (referred_by,))
                conn.commit()
                add_referral_if_absent(referred_by, chat_id)  # MODIFIED FOR GAME INTEGRATION
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
    if is_registered(chat_id):
        reply_keyboard.append([KeyboardButton(text="Play Tapify", web_app=WebAppInfo(url=WEBAPP_URL))])
    await update.message.reply_text(
        "Use the button below 'ONLY' if you get stuck on a process:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )

async def cmd_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if not is_registered(chat_id):
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
        payment_status, streaks, invites, package, balance = user
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

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    log_interaction(chat_id, "list_tasks")
    try:
        cursor.execute("SELECT id, type, link, reward, expires_at FROM tasks WHERE expires_at > CURRENT_TIMESTAMP")
        tasks = cursor.fetchall()
        if not tasks:
            await update.message.reply_text("No active tasks available.")
            return
        text = "📋 Available Tasks:\n\n"
        for task in tasks:
            task_id, task_type, link, reward, expires_at = task
            text += f"• {task_type} (ID: {task_id})\n  Link: {link}\n  Reward: ${reward:.2f}\n  Expires: {expires_at}\n\n"
        await update.message.reply_text(text)
    except psycopg.Error as e:
        logger.error(f"Database error in list_tasks: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /complete_task <task_id>")
        return
    try:
        task_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Task ID must be a number.")
        return
    if not is_registered(chat_id):
        await update.message.reply_text("Please complete registration to perform tasks.")
        return
    try:
        cursor.execute("SELECT reward FROM tasks WHERE id=%s AND expires_at > CURRENT_TIMESTAMP", (task_id,))
        task = cursor.fetchone()
        if not task:
            await update.message.reply_text("Task not found or expired.")
            return
        reward = task[0]
        cursor.execute("SELECT 1 FROM user_tasks WHERE user_id=%s AND task_id=%s", (chat_id, task_id))
        if cursor.fetchone():
            await update.message.reply_text("You have already completed this task.")
            return
        cursor.execute(
            "INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (%s, %s, CURRENT_TIMESTAMP)",
            (chat_id, task_id)
        )
        cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id=%s", (reward, chat_id))
        conn.commit()
        await update.message.reply_text(f"Task completed! You earned ${reward:.2f}.")
        log_interaction(chat_id, f"complete_task_{task_id}")
    except psycopg.Error as e:
        logger.error(f"Database error in complete_task: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    log_interaction(chat_id, "menu")
    payment_status = get_status(chat_id)
    if not payment_status:
        cursor.execute(
            "INSERT INTO users (chat_id, username, payment_status) VALUES (%s, %s, %s) ON CONFLICT (chat_id) DO NOTHING",
            (chat_id, update.effective_user.username or "Unknown", "new")
        )
        conn.commit()
        payment_status = "new"
    keyboard = []
    if payment_status == "new":
        keyboard.append([
            InlineKeyboardButton("Free ($0)", callback_data="package_free"),
            InlineKeyboardButton("Starter ($30)", callback_data="package_starter"),
        ])
        keyboard.append([
            InlineKeyboardButton("Pro ($50)", callback_data="package_pro"),
            InlineKeyboardButton("Elite ($100)", callback_data="package_elite"),
        ])
    elif payment_status == "pending_payment":
        keyboard.append([InlineKeyboardButton("Upload Payment Proof", callback_data="upload_screenshot")])
    elif payment_status == "pending_approval":
        keyboard.append([InlineKeyboardButton("Check Approval Status", callback_data="check_approval")])
    elif payment_status == "pending_details":
        keyboard.append([InlineKeyboardButton("Submit Details", callback_data="submit_details")])
    elif payment_status == "registered":
        keyboard.append([InlineKeyboardButton("📊 My Stats", callback_data="stats")])
        keyboard.append([InlineKeyboardButton("🎮 Play Tapify", web_app=WebAppInfo(url=WEBAPP_URL))])
        keyboard.append([InlineKeyboardButton("📋 Tasks", callback_data="list_tasks")])
        keyboard.append([InlineKeyboardButton("💬 Support", callback_data="support")])
        keyboard.append([InlineKeyboardButton("ℹ️ Help", callback_data="help")])
    await update.message.reply_text(
        "Welcome to the Tapify Menu! Choose an option below:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Callback Query Handlers -------------------------------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    data = query.data
    log_interaction(chat_id, f"button_{data}")

    if data.startswith("package_"):
        package = data.split("_")[1].capitalize()
        try:
            cursor.execute(
                "UPDATE users SET package=%s, payment_status='pending_payment' WHERE chat_id=%s",
                (package, chat_id)
            )
            conn.commit()
        except psycopg.Error as e:
            logger.error(f"Database error in package selection: {e}")
            await query.edit_message_text("An error occurred. Please try again.")
            return
        package_prices = {"Free": 0, "Starter": 30, "Pro": 50, "Elite": 100}
        amount = package_prices.get(package, 0)
        payment_options = [
            [InlineKeyboardButton(name, callback_data=f"pay_{name.lower().replace(' ', '_')}")]
            for name in PAYMENT_ACCOUNTS.keys()
        ]
        text = f"You selected the {package} package (${amount}). Please choose a payment account:"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(payment_options))

    elif data.startswith("pay_"):
        payment_account_key = data.split("pay_")[1].replace("_", " ").title()
        payment_account = PAYMENT_ACCOUNTS.get(payment_account_key)
        if not payment_account:
            await query.edit_message_text("Invalid payment account selected.")
            return
        try:
            cursor.execute("SELECT package FROM users WHERE chat_id=%s", (chat_id,))
            package = cursor.fetchone()[0]
            package_prices = {"Free": 0, "Starter": 30, "Pro": 50, "Elite": 100}
            amount = package_prices.get(package, 0)
            cursor.execute(
                "INSERT INTO payments (chat_id, type, package, quantity, total_amount, payment_account, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (chat_id, "package", package, 1, amount, payment_account, "pending_payment")
            )
            payment_id = cursor.fetchone()[0]
            conn.commit()
        except psycopg.Error as e:
            logger.error(f"Database error in payment: {e}")
            await query.edit_message_text("An error occurred. Please try again.")
            return
        await query.edit_message_text(
            f"Please make a payment of ${amount} to:\n{payment_account}\n\n"
            "After payment, upload the screenshot by clicking below.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Upload Screenshot", callback_data="upload_screenshot")]])
        )

    elif data == "upload_screenshot":
        user_state[chat_id] = {'expecting': 'screenshot'}
        await query.edit_message_text("Please upload the payment screenshot.")

    elif data == "check_approval":
        status = get_status(chat_id)
        if status == "pending_approval":
            await query.edit_message_text(
                "Your payment is still pending approval. You'll be notified once approved.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Check Again", callback_data="check_approval")]])
            )
        elif status == "pending_details":
            await query.edit_message_text(
                "Payment approved! Please submit your details.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Submit Details", callback_data="submit_details")]])
            )
        elif status == "registered":
            await query.edit_message_text(
                "You are fully registered! Access the menu with /menu.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Go to Menu", callback_data="menu")]])
            )

    elif data == "submit_details":
        user_state[chat_id] = {'expecting': 'name'}
        await query.edit_message_text("Please provide your full name:")

    elif data == "stats":
        await stats(update, context)

    elif data == "list_tasks":
        await list_tasks(update, context)

    elif data == "support":
        user_state[chat_id] = {'expecting': 'support_message'}
        await query.edit_message_text("Please describe your issue or question:")

    elif data == "help":
        keyboard = [
            [InlineKeyboardButton(topic["label"], callback_data=f"help_{key}")]
            for key, topic in HELP_TOPICS.items()
        ]
        await query.edit_message_text(
            "Select a help topic:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("help_"):
        topic_key = data.split("help_")[1]
        topic = HELP_TOPICS.get(topic_key)
        if not topic:
            await query.edit_message_text("Invalid help topic.")
            return
        if topic["type"] == "video":
            await query.edit_message_text(
                f"{topic['label']}:\n{topic['url']}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Help", callback_data="help")]])
            )
        elif topic["type"] == "text":
            await query.edit_message_text(
                f"{topic['label']}:\n{topic['text']}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Help", callback_data="help")]])
            )
        elif topic["type"] == "toggle":
            try:
                cursor.execute("SELECT alarm_setting FROM users WHERE chat_id=%s", (chat_id,))
                current = cursor.fetchone()[0]
                new_setting = 0 if current == 1 else 1
                cursor.execute("UPDATE users SET alarm_setting=%s WHERE chat_id=%s", (new_setting, chat_id))
                conn.commit()
                status = "ON" if new_setting == 1 else "OFF"
                await query.edit_message_text(
                    f"Daily Reminder is now {status}.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Help", callback_data="help")]])
                )
            except psycopg.Error as e:
                logger.error(f"Database error in toggle reminder: {e}")
                await query.edit_message_text("An error occurred. Please try again.")
        elif topic["type"] == "faq":
            keyboard = [
                [InlineKeyboardButton(faq["question"], callback_data=f"faq_{key}")]
                for key, faq in FAQS.items()
            ]
            keyboard.append([InlineKeyboardButton("Back to Help", callback_data="help")])
            await query.edit_message_text(
                "Select an FAQ:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif topic["type"] == "input":
            user_state[chat_id] = {'expecting': 'password_recovery_email'}
            await query.edit_message_text(topic["text"])

    elif data.startswith("faq_"):
        faq_key = data.split("faq_")[1]
        faq = FAQS.get(faq_key)
        if not faq:
            await query.edit_message_text("Invalid FAQ.")
            return
        await query.edit_message_text(
            f"❓ {faq['question']}\n\n{faq['answer']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to FAQs", callback_data="help_faq")]])
        )

    elif data == "withdraw":
        try:
            cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            balance = cursor.fetchone()[0]
            if balance < 30:
                await query.edit_message_text("Minimum withdrawal is $30.")
                return
            user_state[chat_id] = {'expecting': 'withdraw_amount'}
            await query.edit_message_text(f"Your balance is ${balance:.2f}. Enter the amount to withdraw:")
        except psycopg.Error as e:
            logger.error(f"Database error in withdraw: {e}")
            await query.edit_message_text("An error occurred. Please try again.")

    elif data.startswith("deposit_approve_"):
        if chat_id != ADMIN_ID:
            await query.answer("Only the admin can approve deposits.")
            return
        _, _, deposit_id, user_chat_id, amount = data.split("_")
        try:
            cursor.execute(
                "UPDATE deposits SET status='approved' WHERE id=%s AND chat_id=%s AND status='pending'",
                (deposit_id, user_chat_id)
            )
            if cursor.rowcount == 0:
                await query.edit_message_text("Deposit not found or already processed.")
                return
            cursor.execute("UPDATE users SET payment_status='registered' WHERE chat_id=%s", (user_chat_id,))
            gu = get_game_user(int(user_chat_id))
            coins = int(gu.get("coins") or 0) + int(amount)
            update_game_user_fields(int(user_chat_id), {"coins": coins})
            conn.commit()
            await bot.send_message(
                chat_id=user_chat_id,
                text=f"Your deposit of {amount} Naira has been approved! Balance updated."
            )
            await query.edit_message_text("Deposit approved and user notified.")
        except psycopg.Error as e:
            logger.error(f"Database error in deposit_approve: {e}")
            await query.edit_message_text("An error occurred. Please try again.")

    elif data.startswith("deposit_reject_"):
        if chat_id != ADMIN_ID:
            await query.answer("Only the admin can reject deposits.")
            return
        _, _, deposit_id, user_chat_id = data.split("_")
        try:
            cursor.execute(
                "UPDATE deposits SET status='rejected' WHERE id=%s AND chat_id=%s AND status='pending'",
                (deposit_id, user_chat_id)
            )
            if cursor.rowcount == 0:
                await query.edit_message_text("Deposit not found or already processed.")
                return
            conn.commit()
            await bot.send_message(
                chat_id=user_chat_id,
                text="Your deposit request was rejected. Please contact support."
            )
            await query.edit_message_text("Deposit rejected and user notified.")
        except psycopg.Error as e:
            logger.error(f"Database error in deposit_reject: {e}")
            await query.edit_message_text("An error occurred. Please try again.")

# --- Message Handlers --------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message = update.message
    state = user_state.get(chat_id, {})
    expecting = state.get('expecting')

    if expecting == 'screenshot':
        if not message.photo:
            await message.reply_text("Please upload a photo of the payment screenshot.")
            return
        try:
            cursor.execute(
                "SELECT id, package, total_amount FROM payments WHERE chat_id=%s AND status='pending_payment' ORDER BY timestamp DESC LIMIT 1",
                (chat_id,)
            )
            payment = cursor.fetchone()
            if not payment:
                await message.reply_text("No pending payment found.")
                return
            payment_id, package, amount = payment
            file = await message.photo[-1].get_file()
            file_path = f"screenshots/{chat_id}_{payment_id}.jpg"
            os.makedirs("screenshots", exist_ok=True)
            await file.download_to_drive(file_path)
            cursor.execute(
                "UPDATE users SET payment_status='pending_approval', screenshot_uploaded_at=CURRENT_TIMESTAMP WHERE chat_id=%s",
                (chat_id,)
            )
            cursor.execute("UPDATE payments SET status='pending_approval' WHERE id=%s", (payment_id,))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_{chat_id}_{payment_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_{chat_id}_{payment_id}")]
            ]
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=open(file_path, 'rb'),
                caption=f"Payment screenshot from {message.from_user.username or chat_id} for {package} (${amount})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await message.reply_text(
                "Screenshot uploaded. Awaiting admin approval.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Check Status", callback_data="check_approval")]])
            )
            user_state.pop(chat_id, None)
        except (psycopg.Error, Exception) as e:
            logger.error(f"Error in handle_screenshot: {e}")
            await message.reply_text("An error occurred. Please try again.")

    elif expecting == 'name':
        name = message.text.strip()
        if not name:
            await message.reply_text("Please provide a valid name.")
            return
        user_state[chat_id]['name'] = name
        user_state[chat_id]['expecting'] = 'email'
        await message.reply_text("Please provide your email address:")

    elif expecting == 'email':
        email = message.text.strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            await message.reply_text("Please provide a valid email address.")
            return
        user_state[chat_id]['email'] = email
        user_state[chat_id]['expecting'] = 'phone'
        await message.reply_text("Please provide your phone number:")

    elif expecting == 'phone':
        phone = message.text.strip()
        if not re.match(r"\+?\d{10,15}", phone):
            await message.reply_text("Please provide a valid phone number.")
            return
        user_state[chat_id]['phone'] = phone
        user_state[chat_id]['expecting'] = 'password'
        await message.reply_text("Please set a password for your account:")

    elif expecting == 'password':
        password = message.text.strip()
        if len(password) < 6:
            await message.reply_text("Password must be at least 6 characters long.")
            return
        try:
            cursor.execute(
                "UPDATE users SET name=%s, email=%s, phone=%s, password=%s, payment_status='registered', registration_date=CURRENT_TIMESTAMP WHERE chat_id=%s",
                (user_state[chat_id]['name'], user_state[chat_id]['email'], user_state[chat_id]['phone'], password, chat_id)
            )
            conn.commit()
            await message.reply_text(
                "Registration complete! You can now access all features.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Go to Menu", callback_data="menu")]])
            )
            user_state.pop(chat_id, None)
        except psycopg.Error as e:
            logger.error(f"Database error in complete_registration: {e}")
            await message.reply_text("An error occurred. Please try again.")

    elif expecting == 'support_message':
        support_message = message.text.strip()
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Support request from @{message.from_user.username or chat_id}:\n{support_message}"
            )
            await message.reply_text("Your support request has been sent to the admin. You'll hear back soon.")
            user_state.pop(chat_id, None)
        except Exception as e:
            logger.error(f"Error in handle_support_message: {e}")
            await message.reply_text("An error occurred. Please try again.")

    elif expecting == 'password_recovery_email':
        email = message.text.strip()
        try:
            cursor.execute("SELECT chat_id FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()
            if not user:
                await message.reply_text("No account found with this email.")
                return
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Password recovery request from {email} (Chat ID: {user[0]})"
            )
            await message.reply_text("Password recovery request sent to admin. You'll be contacted soon.")
            user_state.pop(chat_id, None)
        except psycopg.Error as e:
            logger.error(f"Database error in password_recovery: {e}")
            await message.reply_text("An error occurred. Please try again.")

    elif expecting == 'withdraw_amount':
        try:
            amount = float(message.text.strip())
            cursor.execute("SELECT balance FROM users WHERE chat_id=%s", (chat_id,))
            balance = cursor.fetchone()[0]
            if amount < 30:
                await message.reply_text("Minimum withdrawal is $30.")
                return
            if amount > balance:
                await message.reply_text("Insufficient balance.")
                return
            cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id=%s", (amount, chat_id))
            conn.commit()
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Withdrawal request from @{message.from_user.username or chat_id}: ${amount}"
            )
            await message.reply_text("Withdrawal request sent to admin. You'll be notified once processed.")
            user_state.pop(chat_id, None)
        except ValueError:
            await message.reply_text("Please enter a valid amount.")
        except psycopg.Error as e:
            logger.error(f"Database error in withdraw_amount: {e}")
            await message.reply_text("An error occurred. Please try again.")

    elif message.text.startswith("/coupon_"):
        coupon_code = message.text.split("_")[1] if "_" in message.text else None
        if not coupon_code:
            await message.reply_text("Please provide a coupon code, e.g., /coupon_ABC123")
            return
        try:
            cursor.execute(
                "SELECT p.id, p.chat_id, p.package, p.total_amount FROM coupons c JOIN payments p ON c.payment_id=p.id WHERE c.code=%s AND p.status='pending_coupon'",
                (coupon_code,)
            )
            payment = cursor.fetchone()
            if not payment:
                await message.reply_text("Invalid or already used coupon code.")
                return
            payment_id, user_chat_id, package, amount = payment
            if chat_id != user_chat_id:
                await message.reply_text("This coupon code is not associated with your account.")
                return
            cursor.execute("UPDATE payments SET status='pending_approval' WHERE id=%s", (payment_id,))
            cursor.execute("UPDATE users SET payment_status='pending_approval' WHERE chat_id=%s", (chat_id,))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("Approve", callback_data=f"approve_{chat_id}_{payment_id}")],
                [InlineKeyboardButton("Reject", callback_data=f"reject_{chat_id}_{payment_id}")]
            ]
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Coupon redemption from @{message.from_user.username or chat_id} for {package} (${amount}) with code {coupon_code}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await message.reply_text(
                "Coupon submitted. Awaiting admin approval.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Check Status", callback_data="check_approval")]])
            )
        except psycopg.Error as e:
            logger.error(f"Database error in coupon redemption: {e}")
            await message.reply_text("An error occurred. Please try again.")

    else:
        if message.text.startswith("/"):
            await message.reply_text("Unknown command. Use /menu to see options.")
        else:
            await message.reply_text("Please use the menu to proceed: /menu")

# --- Admin Callback Handlers -------------------------------------------------

async def admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    if chat_id != ADMIN_ID:
        await query.answer("Only the admin can perform this action.")
        return
    data = query.data
    action, user_chat_id, payment_id = data.split("_")
    try:
        cursor.execute("SELECT package, total_amount FROM payments WHERE id=%s AND status='pending_approval'", (payment_id,))
        payment = cursor.fetchone()
        if not payment:
            await query.edit_message_text("Payment not found or already processed.")
            return
        package, amount = payment
        if action == "approve":
            cursor.execute("UPDATE payments SET status='approved', approved_at=CURRENT_TIMESTAMP WHERE id=%s", (payment_id,))
            cursor.execute("UPDATE users SET payment_status='pending_details' WHERE chat_id=%s", (user_chat_id,))
            conn.commit()
            await bot.send_message(
                chat_id=user_chat_id,
                text="Your payment has been approved! Please submit your details.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Submit Details", callback_data="submit_details")]])
            )
            await query.edit_message_text("Payment approved. User notified to submit details.")
        elif action == "reject":
            cursor.execute("UPDATE payments SET status='rejected' WHERE id=%s", (payment_id,))
            cursor.execute("UPDATE users SET payment_status='pending_payment' WHERE chat_id=%s", (user_chat_id,))
            conn.commit()
            await bot.send_message(
                chat_id=user_chat_id,
                text="Your payment was rejected. Please upload a new screenshot.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Upload Screenshot", callback_data="upload_screenshot")]])
            )
            await query.edit_message_text("Payment rejected. User notified.")
    except psycopg.Error as e:
        logger.error(f"Database error in admin_approval: {e}")
        await query.edit_message_text("An error occurred. Please try again.")

# --- Job Queue Handlers ------------------------------------------------------

async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    try:
        cursor.execute("SELECT chat_id FROM users WHERE alarm_setting=1")
        users = cursor.fetchall()
        for user in users:
            chat_id = user[0]
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="🌟 Daily Reminder: Complete your tasks and play Tapify to earn more!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Go to Menu", callback_data="menu")]])
                )
            except Exception as e:
                logger.error(f"Failed to send reminder to {chat_id}: {e}")
    except psycopg.Error as e:
        logger.error(f"Database error in daily_reminder: {e}")

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    try:
        cursor.execute("SELECT chat_id, balance, streaks, invites FROM users WHERE payment_status='registered'")
        users = cursor.fetchall()
        for user in users:
            chat_id, balance, streaks, invites = user
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"📈 Your Daily Summary:\n\n"
                        f"• Balance: ${balance:.2f}\n"
                        f"• Streaks: {streaks}\n"
                        f"• Invites: {invites}\n\n"
                        "Keep tapping and completing tasks!"
                    ),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Go to Menu", callback_data="menu")]])
                )
            except Exception as e:
                logger.error(f"Failed to send summary to {chat_id}: {e}")
    except psycopg.Error as e:
        logger.error(f"Database error in daily_summary: {e}")

async def set_bot_username(context: ContextTypes.DEFAULT_TYPE):
    global BOT_USERNAME
    try:
        bot_info = await bot.get_me()
        BOT_USERNAME = f"@{bot_info.username}"
        logger.info(f"Bot username set to {BOT_USERNAME}")
    except Exception as e:
        logger.error(f"Failed to set bot username: {e}")

# --- Main Application Setup --------------------------------------------------

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", cmd_game))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("reset_state", reset_state))
    application.add_handler(CommandHandler("add_task", add_task))
    application.add_handler(CommandHandler("list_tasks", list_tasks))
    application.add_handler(CommandHandler("complete_task", complete_task))
    application.add_handler(CommandHandler("menu", menu))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(package_|pay_|upload_screenshot|check_approval|submit_details|stats|list_tasks|support|help|help_|faq_|withdraw|deposit_approve_|deposit_reject_)"))
    application.add_handler(CallbackQueryHandler(admin_approval, pattern="^(approve_|reject_)"))

    # Message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.PHOTO, handle_message))

    # Job queue
    job_queue = application.job_queue
    job_queue.run_repeating(daily_reminder, interval=86400, first=0)
    job_queue.run_repeating(daily_summary, interval=86400, first=0)
    job_queue.run_once(set_bot_username, 0)

    # Start Flask server
    keep_alive()

    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
