#!/usr/bin/env python3
"""
BreachCheck Server v5 — API Server + Telegram Bot
==================================================
يعمل كسيرفر مركزي يحتوي على فهرس SQLite
المستخدمون يستعلمون عبر API أو Telegram Bot

Endpoints:
  GET  /search?email=user@example.com     → نتائج الإيميل
  GET  /domain?d=gmail.com&limit=100      → نتائج الدومين
  GET  /stats                             → إحصائيات القاعدة
  GET  /health                            → حالة السيرفر
  POST /bulk                              → بحث متعدد

Deploy:
  python3 server.py --port 8080
  # أو عبر Docker
  docker build -t breachcheck . && docker run -p 8080:8080 breachcheck
"""

import os
import sys
import time
import json
import sqlite3
import argparse
import threading
from datetime import datetime

try:
    from flask import Flask, request, jsonify, Response
except ImportError:
    print("❌ pip install flask --break-system-packages")
    sys.exit(1)

# ============ CONFIG ============
DB_PATH = os.environ.get("DB_PATH", "breachcheck_index.db")
API_KEY = os.environ.get("API_KEY", "")  # Optional API key protection
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "0"))  # 0 = unlimited

app = Flask(__name__)
_db = None
_db_lock = threading.Lock()

# ============ DATABASE ============
def get_db():
    global _db
    if _db is None:
        if not os.path.exists(DB_PATH):
            print(f"❌ Database not found: {DB_PATH}")
            print(f"   Run build_index.py first to create the index")
            sys.exit(1)
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA cache_size=-200000")  # 200MB cache
        _db.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        print(f"✅ Database loaded: {DB_PATH} ({os.path.getsize(DB_PATH)/1024**3:.1f}GB)")
    return _db


def check_api_key():
    """Optional API key validation."""
    if not API_KEY:
        return True
    key = request.headers.get("X-API-Key", request.args.get("key", ""))
    return key == API_KEY


# Rate limiting (simple in-memory)
_request_counts = {}
_request_times = {}
def check_rate_limit(ip):
    if RATE_LIMIT == 0:
        return True
    now = time.time()
    if ip not in _request_counts:
        _request_counts[ip] = 0
        _request_times[ip] = now
    if now - _request_times[ip] > 60:  # Reset every minute
        _request_counts[ip] = 0
        _request_times[ip] = now
    if _request_counts[ip] >= RATE_LIMIT:
        return False
    _request_counts[ip] += 1
    return True


# ============ ENDPOINTS ============
@app.route("/health")
def health():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    return jsonify({
        "status": "online",
        "records": count,
        "db_size_gb": round(os.path.getsize(DB_PATH) / 1024**3, 2),
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route("/stats")
def stats():
    if not check_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    db = get_db()
    
    total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    emails = db.execute("SELECT COUNT(DISTINCT email) FROM records").fetchone()[0]
    breaches = db.execute("SELECT COUNT(DISTINCT breach) FROM records").fetchone()[0]
    
    # Top breaches
    top = db.execute(
        "SELECT breach, COUNT(*) as cnt FROM records GROUP BY breach ORDER BY cnt DESC LIMIT 20"
    ).fetchall()
    
    # Top domains
    domains = db.execute(
        """SELECT substr(email, instr(email, '@')+1) as domain, COUNT(*) as cnt 
           FROM records GROUP BY domain ORDER BY cnt DESC LIMIT 20"""
    ).fetchall()
    
    return jsonify({
        "total_records": total,
        "unique_emails": emails,
        "breach_sources": breaches,
        "db_size_gb": round(os.path.getsize(DB_PATH) / 1024**3, 2),
        "top_breaches": [{"name": b[0], "count": b[1]} for b in top],
        "top_domains": [{"domain": d[0], "count": d[1]} for d in domains]
    })


@app.route("/search")
def search_email():
    """Search for a specific email — instant."""
    if not check_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    
    ip = request.remote_addr
    if not check_rate_limit(ip):
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    
    db = get_db()
    t0 = time.time()
    
    cursor = db.execute(
        "SELECT email, password, breach FROM records WHERE email = ? ORDER BY breach",
        (email,)
    )
    results = cursor.fetchall()
    elapsed = time.time() - t0
    
    return jsonify({
        "email": email,
        "found": len(results) > 0,
        "count": len(results),
        "search_time_ms": round(elapsed * 1000, 1),
        "results": [
            {"email": r[0], "password": r[1], "breach": r[2]}
            for r in results
        ]
    })


@app.route("/domain")
def search_domain():
    """Search for all emails with a specific domain."""
    if not check_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    
    ip = request.remote_addr
    if not check_rate_limit(ip):
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    domain = request.args.get("d", "").strip().lower().lstrip("@")
    limit = min(int(request.args.get("limit", 100)), 10000)
    offset = int(request.args.get("offset", 0))
    
    if not domain:
        return jsonify({"error": "Domain required"}), 400
    
    db = get_db()
    t0 = time.time()
    
    count = db.execute(
        "SELECT COUNT(*) FROM records WHERE email LIKE ?",
        (f"%@{domain}",)
    ).fetchone()[0]
    
    cursor = db.execute(
        "SELECT email, password, breach FROM records WHERE email LIKE ? LIMIT ? OFFSET ?",
        (f"%@{domain}", limit, offset)
    )
    results = cursor.fetchall()
    elapsed = time.time() - t0
    
    return jsonify({
        "domain": domain,
        "total_count": count,
        "returned": len(results),
        "offset": offset,
        "search_time_ms": round(elapsed * 1000, 1),
        "results": [
            {"email": r[0], "password": r[1], "breach": r[2]}
            for r in results
        ]
    })


@app.route("/bulk", methods=["POST"])
def bulk_search():
    """Search multiple emails at once."""
    if not check_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    
    data = request.get_json()
    if not data or "emails" not in data:
        return jsonify({"error": "JSON with 'emails' array required"}), 400
    
    emails = [e.strip().lower() for e in data["emails"][:100]]  # Max 100
    if not emails:
        return jsonify({"error": "No emails provided"}), 400
    
    db = get_db()
    t0 = time.time()
    
    results = {}
    for email in emails:
        cursor = db.execute(
            "SELECT email, password, breach FROM records WHERE email = ?",
            (email,)
        )
        rows = cursor.fetchall()
        if rows:
            results[email] = [
                {"email": r[0], "password": r[1], "breach": r[2]}
                for r in rows
            ]
    
    elapsed = time.time() - t0
    
    return jsonify({
        "queried": len(emails),
        "found": len(results),
        "search_time_ms": round(elapsed * 1000, 1),
        "results": results
    })


# ============ PLAINTEXT OUTPUT ============
@app.route("/search.txt")
def search_email_txt():
    """Search and return plaintext output: email:password [breach]"""
    if not check_api_key():
        return "ERROR: Invalid API key\n", 401
    
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return "ERROR: Valid email required\n", 400
    
    db = get_db()
    cursor = db.execute(
        "SELECT email, password, breach FROM records WHERE email = ? ORDER BY breach",
        (email,)
    )
    results = cursor.fetchall()
    
    if not results:
        return f"NOT_FOUND: {email}\n", 404
    
    lines = []
    for r in results:
        lines.append(f"{r[0]}:{r[1]} [{r[2]}]")
    
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@app.route("/domain.txt")
def search_domain_txt():
    """Search domain and return plaintext output."""
    if not check_api_key():
        return "ERROR: Invalid API key\n", 401
    
    domain = request.args.get("d", "").strip().lower().lstrip("@")
    limit = min(int(request.args.get("limit", 1000)), 10000)
    
    if not domain:
        return "ERROR: Domain required\n", 400
    
    db = get_db()
    cursor = db.execute(
        "SELECT email, password, breach FROM records WHERE email LIKE ? LIMIT ?",
        (f"%@{domain}", limit)
    )
    results = cursor.fetchall()
    
    if not results:
        return f"NOT_FOUND: @{domain}\n", 404
    
    lines = [f"# Domain: {domain} | Results: {len(results)}"]
    for r in results:
        lines.append(f"{r[0]}:{r[1]} [{r[2]}]")
    
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


# ============ TELEGRAM BOT ============
def run_telegram_bot(token):
    """Run Telegram bot alongside the API server."""
    try:
        import telebot
    except ImportError:
        print("⚠ Telegram bot requires: pip install pyTelegramBotAPI --break-system-packages")
        return
    
    db = get_db()
    bot = telebot.TeleBot(token)
    
    @bot.message_handler(commands=["start"])
    def start(message):
        bot.reply_to(message,
            "🔍 BreachCheck Bot\n\n"
            "Commands:\n"
            "/search user@example.com — Search for email\n"
            "/domain gmail.com — Search by domain\n"
            "/stats — Database statistics\n"
            "/help — Show help")
    
    @bot.message_handler(commands=["help"])
    def help_cmd(message):
        bot.reply_to(message,
            "🔍 BreachCheck Search Bot\n\n"
            "/search user@example.com\n"
            "/domain gmail.com\n"
            "/stats\n\n"
            "Or just send an email address directly!")
    
    @bot.message_handler(commands=["search"])
    def search_cmd(message):
        email = message.text.replace("/search", "").strip().lower()
        if not email or "@" not in email:
            bot.reply_to(message, "❌ Usage: /search user@example.com")
            return
        
        cursor = db.execute(
            "SELECT email, password, breach FROM records WHERE email = ? ORDER BY breach",
            (email,)
        )
        results = cursor.fetchall()
        
        if not results:
            bot.reply_to(message, f"❌ NOT FOUND: {email}")
            return
        
        response = f"🎯 Found {len(results)} record(s) for {email}\n\n"
        for i, (em, pw, breach) in enumerate(results, 1):
            response += f"#{i} [{breach}]\n{em}:{pw}\n\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n... (truncated)"
        
        bot.reply_to(message, response)
    
    @bot.message_handler(commands=["domain"])
    def domain_cmd(message):
        domain = message.text.replace("/domain", "").strip().lower().lstrip("@")
        if not domain:
            bot.reply_to(message, "❌ Usage: /domain gmail.com")
            return
        
        count = db.execute(
            "SELECT COUNT(*) FROM records WHERE email LIKE ?",
            (f"%@{domain}",)
        ).fetchone()[0]
        
        if count == 0:
            bot.reply_to(message, f"❌ No records for @{domain}")
            return
        
        cursor = db.execute(
            "SELECT email, password, breach FROM records WHERE email LIKE ? LIMIT 50",
            (f"%@{domain}",)
        )
        results = cursor.fetchall()
        
        response = f"📊 @{domain}: {count:,} records total\n\nShowing first 50:\n\n"
        for em, pw, breach in results:
            response += f"{em}:{pw} [{breach}]\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n... (truncated)"
        
        bot.reply_to(message, response)
    
    @bot.message_handler(commands=["stats"])
    def stats_cmd(message):
        total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        emails = db.execute("SELECT COUNT(DISTINCT email) FROM records").fetchone()[0]
        breaches = db.execute("SELECT COUNT(DISTINCT breach) FROM records").fetchone()[0]
        
        bot.reply_to(message,
            f"📊 Database Statistics\n\n"
            f"Total records: {total:,}\n"
            f"Unique emails: {emails:,}\n"
            f"Breach sources: {breaches}\n"
            f"DB size: {os.path.getsize(DB_PATH)/1024**3:.1f}GB")
    
    @bot.message_handler(func=lambda m: "@" in m.text and not m.text.startswith("/"))
    def auto_search(message):
        """Auto-detect email in message and search."""
        email = message.text.strip().lower()
        if "@" not in email:
            return
        
        cursor = db.execute(
            "SELECT email, password, breach FROM records WHERE email = ?",
            (email,)
        )
        results = cursor.fetchall()
        
        if not results:
            bot.reply_to(message, f"❌ NOT FOUND: {email}")
            return
        
        response = f"🎯 Found {len(results)} record(s)\n\n"
        for i, (em, pw, breach) in enumerate(results, 1):
            response += f"#{i} [{breach}]\n{em}:{pw}\n\n"
        
        if len(response) > 4000:
            response = response[:4000] + "\n... (truncated)"
        
        bot.reply_to(message, response)
    
    print(f"🤖 Telegram bot started")
    bot.infinity_polling()


# ============ MAIN ============
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BreachCheck API Server")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    parser.add_argument("--db", type=str, default=DB_PATH, help="SQLite database path")
    parser.add_argument("--telegram", type=str, default="", help="Telegram bot token (optional)")
    parser.add_argument("--api-key", type=str, default="", help="API key for protection")
    args = parser.parse_args()
    
    DB_PATH = args.db
    if args.api_key:
        API_KEY = args.api_key
    
    print(f"""
  ╔═══════════════════════════════════════════════════════════╗
  ║   🔍 BreachCheck API Server v5.0                           ║
  ║   Central Index • Fast API • Telegram Bot                  ║
  ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Load database
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    print(f"  📊 Records: {count:,}")
    print(f"  💾 DB size: {os.path.getsize(DB_PATH)/1024**3:.1f}GB")
    print(f"  🌐 Server: http://{args.host}:{args.port}")
    print(f"  🔑 API key: {'enabled' if API_KEY else 'disabled'}")
    
    # Start Telegram bot if token provided
    if args.telegram:
        tg_thread = threading.Thread(target=run_telegram_bot, args=(args.telegram,), daemon=True)
        tg_thread.start()
        print(f"  🤖 Telegram bot: enabled")
    
    print(f"\n  Endpoints:")
    print(f"    GET  /search?email=user@example.com")
    print(f"    GET  /domain?d=gmail.com&limit=100")
    print(f"    GET  /search.txt?email=user@example.com  (plaintext)")
    print(f"    GET  /domain.txt?d=gmail.com              (plaintext)")
    print(f"    GET  /stats")
    print(f"    GET  /health")
    print(f"    POST /bulk  {{\"emails\": [\"a@b.com\", \"c@d.com\"]}}")
    print(f"\n  Press Ctrl+C to stop\n")
    
    app.run(host=args.host, port=args.port, threaded=True)
