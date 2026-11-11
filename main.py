import os
import sqlite3
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
DB_PATH = os.environ.get("DB_PATH", "bot_data.sqlite3")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                uid TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                completed_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                last_completed_at TEXT
            )
        """)

def now():
    return datetime.now(timezone.utc)

def parse_dt(value):
    return datetime.fromisoformat(value) if value else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Free Fire Likes Bot\\n\\n"
        "আপনার Free Fire UID পাঠান। অ্যাডমিন অনুমোদন করলে "
        "আপনার অনুরোধটি গ্রহণ করা হবে।\\n"
        "/status — অনুরোধের অবস্থা দেখুন"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with db() as con:
        row = con.execute(
            "SELECT * FROM requests WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        user = con.execute(
            "SELECT last_completed_at FROM users WHERE user_id=?", (user_id,)
        ).fetchone()

    lines = []
    if row:
        labels = {
            "pending": "অ্যাডমিনের অনুমতির অপেক্ষায়",
            "approved": "অনুমোদিত — অ্যাডমিন লাইক প্রক্রিয়া সম্পন্ন করবেন",
            "rejected": "অনুরোধটি অনুমোদিত হয়নি",
            "completed": "সম্পন্ন"
        }
        lines.append(f"সর্বশেষ অনুরোধ: {labels.get(row['status'], row['status'])}")
        lines.append(f"UID: {row['uid']}")
    else:
        lines.append("আপনার কোনো অনুরোধ পাওয়া যায়নি। UID পাঠিয়ে অনুরোধ করুন।")

    if user and user["last_completed_at"]:
        ready = parse_dt(user["last_completed_at"]) + timedelta(hours=24)
        remaining = ready - now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            lines.append(f"পরবর্তী অনুরোধের আগে বাকি: {hours} ঘণ্টা {minutes} মিনিট")
        else:
            lines.append("আপনি আবার অনুরোধ করতে পারবেন।")

    await update.message.reply_text("\\n".join(lines))

async def receive_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = update.message.text.strip()

    if not uid.isdigit() or not (5 <= len(uid) <= 15):
        await update.message.reply_text("দয়া করে সঠিক সংখ্যার Free Fire UID পাঠান।")
        return

    with db() as con:
        last = con.execute(
            "SELECT last_completed_at FROM users WHERE user_id=?", (user.id,)
        ).fetchone()
        if last and last["last_completed_at"]:
            ready = parse_dt(last["last_completed_at"]) + timedelta(hours=24)
            if now() < ready:
                await update.message.reply_text(
                    "⏳ ২৪ ঘণ্টা পূর্ণ হয়নি। পরে আবার চেষ্টা করুন।"
                )
                return

        pending = con.execute(
            "SELECT id FROM requests WHERE user_id=? AND status IN ('pending','approved')",
            (user.id,)
        ).fetchone()
        if pending:
            await update.message.reply_text(
                "আপনার আগের অনুরোধটি এখনো নিষ্পত্তি হয়নি। /status লিখে দেখুন।"
            )
            return

        cur = con.execute(
            "INSERT INTO requests (user_id, username, uid, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (user.id, user.username or "", uid, now().isoformat())
        )
        request_id = cur.lastrowid

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ অনুমোদন", callback_data=f"approve:{request_id}"),
        InlineKeyboardButton("❌ বাতিল", callback_data=f"reject:{request_id}")
    ]])
    admin_text = (
        "নতুন Free Fire লাইক অনুরোধ\\n"
        f"Request: #{request_id}\\n"
        f"ব্যবহারকারী: @{user.username or 'username নেই'}\\n"
        f"Telegram ID: {user.id}\\n"
        f"Free Fire UID: {uid}"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID, text=admin_text, reply_markup=keyboard
        )
    except Exception:
        with db() as con:
            con.execute("UPDATE requests SET status='rejected' WHERE id=?", (request_id,))
        await update.message.reply_text(
            "অ্যাডমিনের কাছে অনুরোধ পাঠানো যায়নি। পরে আবার চেষ্টা করুন।"
        )
        return

    await update.message.reply_text(
        "✅ আপনার অনুরোধ অ্যাডমিনের কাছে পাঠানো হয়েছে। অনুমতির জন্য অপেক্ষা করুন।"
    )

async def review_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("শুধু অ্যাডমিন এই কাজ করতে পারবেন।", show_alert=True)
        return

    action, req_id_text = query.data.split(":")
    req_id = int(req_id_text)
    new_status = "approved" if action == "approve" else "rejected"

    with db() as con:
        row = con.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
        if not row or row["status"] != "pending":
            await query.edit_message_text("এই অনুরোধটি আগে থেকেই নিষ্পত্তি হয়েছে।")
            return
        con.execute(
            "UPDATE requests SET status=?, reviewed_at=? WHERE id=?",
            (new_status, now().isoformat(), req_id)
        )

    if new_status == "approved":
        await context.bot.send_message(
            row["user_id"],
            "✅ আপনার অনুরোধ অ্যাডমিন অনুমোদন করেছেন। "
            "লাইক পাঠানো হলে অ্যাডমিন /complete কমান্ড দিয়ে ২৪ ঘণ্টার সময়সীমা শুরু করবেন।"
        )
        await query.edit_message_text(query.message.text + "\\n\\nস্ট্যাটাস: অনুমোদিত")
    else:
        await context.bot.send_message(
            row["user_id"], "দুঃখিত, অ্যাডমিন আপনার অনুরোধটি অনুমোদন করেননি।"
        )
        await query.edit_message_text(query.message.text + "\\n\\nস্ট্যাটাস: বাতিল")

async def complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("এই কমান্ড শুধু অ্যাডমিন ব্যবহার করতে পারবেন।")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("ব্যবহার: /complete REQUEST_ID")
        return

    req_id = int(context.args[0])
    with db() as con:
        row = con.execute(
            "SELECT * FROM requests WHERE id=? AND status='approved'", (req_id,)
        ).fetchone()
        if not row:
            await update.message.reply_text("অনুমোদিত অনুরোধটি পাওয়া যায়নি।")
            return
        con.execute(
            "UPDATE requests SET status='completed', completed_at=? WHERE id=?",
            (now().isoformat(), req_id)
        )
        con.execute(
            "INSERT INTO users(user_id, last_completed_at) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_completed_at=excluded.last_completed_at",
            (row["user_id"], now().isoformat())
        )

    await context.bot.send_message(
        row["user_id"], "🎉 আপনার অনুরোধ সম্পন্ন হয়েছে। ২৪ ঘণ্টা পর আবার অনুরোধ করতে পারবেন।"
    )
    await update.message.reply_text(f"Request #{req_id} সম্পন্ন হয়েছে। ২৪ ঘণ্টার কুলডাউন শুরু।")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "/start — শুরু\\n/status — অনুরোধের অবস্থা\\n"
    if update.effective_user.id == ADMIN_ID:
        msg += "/complete REQUEST_ID — লাইক দেওয়ার কাজ শেষ হলে ব্যবহার করুন"
    await update.message.reply_text(msg)

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("complete", complete))
    app.add_handler(CallbackQueryHandler(review_request, pattern=r"^(approve|reject):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_uid))
    app.run_polling()

if __name__ == "__main__":
    main()