import os
import re
import json
import time
import asyncio
import random
import logging
import datetime
import sqlite3
from io import BytesIO
from collections import deque

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.error import BadRequest, RetryAfter, Forbidden, NetworkError
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PollAnswerHandler, ContextTypes, filters, TypeHandler, ApplicationHandlerStop
)
from telegram.request import HTTPXRequest

# =========================================================
# ðŸ“¦ EXTERNAL DEPENDENCIES (OCR, PDF, DOCX, WATERMARK)
# =========================================================
try:
    import pytesseract  # type: ignore # noqa
    from PIL import Image, ImageDraw, ImageFont  # type: ignore # noqa
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import PyPDF2  # type: ignore # noqa
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import docx  # type: ignore # noqa
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# =========================================================
# ðŸŒ¿ HORTICULTURE MASTER BOT v25.0 ULTRA PRO
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("HorticultureMasterBot")

# =========================================================
# ðŸ”‘ CREDENTIALS
# =========================================================

ADMIN_ID = 5183668353
BOT_TOKEN = os.getenv("BOT_TOKEN", "8818348293:AAEj3janjuJlBjknF4hSZrW3IWkgYU0bulo")

# =========================================================
# ðŸ’¾ DATABASE SETUP & PERSISTENCE (SQLite)
# =========================================================

DB_FILE = "horticulture_bot.db"

MAX_QUESTIONS = 1000
SPEED_BONUS_TIME = 5.0
HISTORY_PAGE_SIZE = 10
IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

creation = {}
group_sessions = {}
quizzes = {}
saved_groups = {}
users_data = {}
banned_users = []
approved_users = []
system_data = {"quiz_days": [], "auto_schedules": []}
active_polls = {}
needs_save = False
bot_message_tracker = {}

db_lock = asyncio.Lock()

async def init_db():
    async with db_lock:
        conn = sqlite3.connect(DB_FILE, timeout=20.0)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("CREATE TABLE IF NOT EXISTS users (uid TEXT PRIMARY KEY, data TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS quizzes (quiz_id TEXT PRIMARY KEY, data TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS groups (gid TEXT PRIMARY KEY, data TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS system (key TEXT PRIMARY KEY, data TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS active_sessions (sid TEXT PRIMARY KEY, data TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS active_polls (poll_id TEXT PRIMARY KEY, data TEXT)")
        conn.commit()
        conn.close()

async def load_all_data():
    global quizzes, saved_groups, users_data, banned_users, approved_users, system_data, group_sessions, active_polls
    await init_db()

    async with db_lock:
        conn = sqlite3.connect(DB_FILE, timeout=20.0)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")

        c.execute("SELECT * FROM users")
        for row in c.fetchall(): users_data[row[0]] = json.loads(row[1])
        c.execute("SELECT * FROM quizzes")
        for row in c.fetchall(): quizzes[row[0]] = json.loads(row[1])
        c.execute("SELECT * FROM groups")
        for row in c.fetchall(): saved_groups[row[0]] = json.loads(row[1])

        c.execute("SELECT * FROM active_sessions")
        for row in c.fetchall(): group_sessions[row[0]] = json.loads(row[1])
        c.execute("SELECT * FROM active_polls")
        for row in c.fetchall(): active_polls[row[0]] = json.loads(row[1])

        c.execute("SELECT * FROM system")
        for row in c.fetchall():
            key = row[0]
            data = json.loads(row[1])
            if key == "banned": banned_users = data
            elif key == "approved": approved_users = data
            elif key == "system_data": system_data = data

        if "quiz_days" not in system_data: system_data["quiz_days"] = []
        if "auto_schedules" not in system_data: system_data["auto_schedules"] = []
        conn.close()

async def save_db_sync():
    global needs_save
    async with db_lock:
        try:
            conn = sqlite3.connect(DB_FILE, timeout=20.0)
            c = conn.cursor()
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("BEGIN TRANSACTION")

            for k, v in users_data.items(): c.execute("INSERT OR REPLACE INTO users (uid, data) VALUES (?, ?)", (str(k), json.dumps(v)))
            for k, v in quizzes.items(): c.execute("INSERT OR REPLACE INTO quizzes (quiz_id, data) VALUES (?, ?)", (str(k), json.dumps(v)))
            for k, v in saved_groups.items(): c.execute("INSERT OR REPLACE INTO groups (gid, data) VALUES (?, ?)", (str(k), json.dumps(v)))

            for k, v in group_sessions.items():
                session_copy = v.copy()
                session_copy.pop("timer_task", None)
                c.execute("INSERT OR REPLACE INTO active_sessions (sid, data) VALUES (?, ?)", (str(k), json.dumps(session_copy)))

            for k, v in active_polls.items():
                c.execute("INSERT OR REPLACE INTO active_polls (poll_id, data) VALUES (?, ?)", (str(k), json.dumps(v)))

            c.execute("INSERT OR REPLACE INTO system (key, data) VALUES (?, ?)", ("banned", json.dumps(banned_users)))
            c.execute("INSERT OR REPLACE INTO system (key, data) VALUES (?, ?)", ("approved", json.dumps(approved_users)))
            c.execute("INSERT OR REPLACE INTO system (key, data) VALUES (?, ?)", ("system_data", json.dumps(system_data)))

            c.execute("COMMIT")
            conn.close()
        except Exception as e:
            logger.error(f"Database Save Error: {e}")

async def force_remove_session_db(sid):
    async with db_lock:
        try:
            conn = sqlite3.connect(DB_FILE, timeout=20.0)
            c = conn.cursor()
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("DELETE FROM active_sessions WHERE sid = ?", (str(sid),))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Force DB Remove Error: {e}")

async def auto_save_loop():
    global needs_save
    while True:
        try:
            await asyncio.sleep(15)
            if needs_save:
                await save_db_sync()
                needs_save = False
        except asyncio.CancelledError: break
        except Exception as e: logger.error(f"Auto save error: {e}")

# =========================================================
# ðŸ§¹ MEMORY LEAK CLEANUP
# =========================================================
async def cleanup_stale_sessions():
    global needs_save
    while True:
        await asyncio.sleep(3600)
        try:
            current_time = time.time()
            to_delete_creation = []
            for uid, st in creation.items():
                if current_time - st.get("start_time", current_time) > 7200:
                    to_delete_creation.append(uid)
            for uid in to_delete_creation: creation.pop(uid, None)

            to_delete_sessions = []
            for sid, sess in group_sessions.items():
                if not sess.get("running") and sess.get("state") == "lobby":
                    if current_time - sess.get("question_start", current_time) > 14400:
                        to_delete_sessions.append(sid)
            for sid in to_delete_sessions:
                group_sessions.pop(sid, None)
                needs_save = True
        except Exception as e: logger.error(f"Cleanup error: {e}")

async def resume_active_quizzes(context):
    global needs_save
    for sid, session in list(group_sessions.items()):
        if session.get("running"):
            logger.info(f"Resuming interrupted quiz {sid}")
            q_start = session.get("question_start", time.time())
            time_passed = time.time() - q_start
            quiz = quizzes.get(session.get("quiz_id"))

            if not quiz:
                group_sessions.pop(sid, None)
                continue

            idx = session.get("index", 0)
            if idx < len(session.get("questions", [])):
                q = session["questions"][idx]
                q_timer = get_question_timer(quiz, idx, q)
                remaining = q_timer - time_passed

                if remaining < 0: remaining = 0
                session["timer_task"] = asyncio.create_task(group_timer(sid, context, remaining))
            else:
                await finish_group(sid, context)

            await asyncio.sleep(2)

    needs_save = True

# =========================================================
# ðŸ›¡ï¸ SMART ACCESS & WELCOME MODULE
# =========================================================

ACCESS_DENIED_LINES = [
    "ðŸ‘‘ ACCESS DENIED",
    "âš ï¸ Warning!",
    "Hey there! ðŸ‘‹",
    "Iâ€™m not available for everyone. ðŸ˜‰",
    "My Boss is Akash Dwivedi â€” and I donâ€™t take orders without his permission. ðŸ”¥",
    "ðŸ” Want my help?",
    "Contact my Boss directly: Click here to Message Akash",
    "Once Akash Dwivedi gives the green signal,",
    "ðŸ¤– Iâ€™ll be happy to serve you. ðŸ˜ŽðŸ‘‘"
]

async def access_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    if not update.effective_user: return

    uid = update.effective_user.id
    uid_str = str(uid)

    if uid_str not in users_data:
        users_data[uid_str] = {"name": update.effective_user.full_name, "username": update.effective_user.username, "xp": 0, "played": 0, "streak": 0, "last_play_date": "", "correct_answers": 0, "wrong_answers": 0, "fast_answers": 0, "is_blocked": False, "topic_stats": {}, "monthly_xp": 0, "monthly_played": 0, "last_month": ""}
        needs_save = True
    else:
        users_data[uid_str]["username"] = update.effective_user.username

    if users_data[uid_str].get("is_blocked"): return

    if uid == ADMIN_ID or uid in approved_users: return
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]: return
    if update.poll or update.poll_answer: return

    if update.callback_query:
        chat_id = update.effective_chat.id
        data = update.callback_query.data
        await update.callback_query.answer()

        if data == "other_features":
            vibrate_frames = ["âš¡ [|| ] âš¡", "âš¡ [||||| ] âš¡", "âš¡ [||||||||||] âš¡", "ðŸš¨ *SECURITY BREACH DETECTED* ðŸš¨"]
            try:
                sent_vib = await context.bot.send_message(chat_id, vibrate_frames[0], parse_mode="Markdown")
                for i in range(1, 4):
                    await asyncio.sleep(0.3)
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=sent_vib.message_id, text=vibrate_frames[i], parse_mode="Markdown")
                await asyncio.sleep(0.5)
                await context.bot.delete_message(chat_id=chat_id, message_id=sent_vib.message_id)
            except Exception: pass

            for line in ACCESS_DENIED_LINES:
                try:
                    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                    await asyncio.sleep(0.6)
                    await context.bot.send_message(chat_id=chat_id, text=line, parse_mode="Markdown", disable_web_page_preview=True)
                except Exception: pass

            user_name = update.effective_user.full_name
            username = update.effective_user.username
            user_url = f"https://t.me/{username}" if username else f"tg://user?id={uid}"
            admin_notification = f"ðŸš¨ *UNAUTHORIZED ACCESS ATTEMPT*\n\nðŸ‘¤ *Name:* {clean_markdown_name(user_name)}\nðŸ†” *ID:* `{uid}`\nðŸ’¬ *Username:* @{username if username else 'No Username'}\n\nUser clicked 'Other Features' and hit Boss Mode! ðŸ›‘"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ’¬ Send Direct Message", url=user_url)]])
            try: await context.bot.send_message(chat_id=ADMIN_ID, text=admin_notification, parse_mode="Markdown", reply_markup=reply_markup)
            except Exception: pass

            raise ApplicationHandlerStop()
        else:
            await context.bot.send_message(chat_id=chat_id, text="âš ï¸ *Please ask Admin for full access.*", parse_mode="Markdown")
            raise ApplicationHandlerStop()

    if update.message and update.effective_chat and update.effective_chat.type == "private":
        text = update.message.text or ""

        if text.startswith("/start"):
            chat_id = update.effective_chat.id
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(0.5)
            await context.bot.send_message(chat_id, "ðŸŒ¿ *Welcome to Horticulture Master!*", parse_mode="Markdown")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(1.2)
            await context.bot.send_message(chat_id, "We provide the best study materials and quizzes for your agricultural exams. ðŸ“š\n\nðŸ‘‡ *Join our official platforms below:*", parse_mode="Markdown")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(1.5)

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("ðŸŒ Google Sites", url="https://sites.google.com/view/horticulture-master/home/icar-pg/previous-year-question_1")],
                [InlineKeyboardButton("ðŸ“¢ Telegram Channel", url="https://t.me/akashdwivedilink")],
                [InlineKeyboardButton("ðŸ’¬ Telegram Group", url="https://t.me/horticulturmasterquiz")],
                [InlineKeyboardButton("ðŸŸ¢ WhatsApp Group", url="https://chat.whatsapp.com/KLNOleZhkCv1AzzI6nhDg0?s=cl&p=a&ilr=0&amv=1")],
                [InlineKeyboardButton("â–¶ï¸ YouTube Channel", url="https://youtube.com/@_akash_dwivedi")]
            ])
            await context.bot.send_message(chat_id, "ðŸ”— *Official Links:*", parse_mode="Markdown", reply_markup=markup)
            await asyncio.sleep(1.0)
            feat_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ” Explore Other Features", callback_data="other_features")]])
            await context.bot.send_message(chat_id, "Want to create quizzes and use advanced bot tools?", reply_markup=feat_markup)
            raise ApplicationHandlerStop()

        elif text.startswith("/profile") or text.startswith("/clear"):
            pass
        else:
            await update.message.reply_text("ðŸš¨ Unrecognized command. Send /start to view menu.", parse_mode="Markdown")
            raise ApplicationHandlerStop()

def track_msg(uid, msg_id):
    if uid not in bot_message_tracker:
        bot_message_tracker[uid] = deque(maxlen=100)
    bot_message_tracker[uid].append(msg_id)

# =========================================================
# âš™ï¸ UTILITIES & UNIVERSAL REGEX PARSER
# =========================================================

TIMER_REGEX = re.compile(r"(?im)^(?:timer|time|duration)\s*[:\-]\s*(\d+)")
EXP_REGEX = re.compile(r"(?im)^(?:explanation|exp|solution)\s*[:\-]?\s*(.*)", re.DOTALL)
ANS_REGEX = re.compile(r"(?i)(?:\b|^\s*)(?:correct\s*answer|answer|ans|correct\s*option)\s*[:\-]?\s*[\(]?([a-e1-5])[\)]?(?:\s|$)")
OPT_MARKER_REGEX = re.compile(r"(?im)^options\s*[:\-]?\s*")
OPT_MATCH_REGEX = re.compile(r"(?im)^([^a-zA-Z0-9\(\)]*)[\(]?([a-e1-5])[\)\.\-:]+\s+")

def format_schedule_time(text):
    text = str(text).strip()
    if text.upper() in ["OFF", "SKIP", "NOT SET", "NO", "NONE"]: return "Off"

    match_full = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2})\s*[:\.]\s*(\d{2})\s*(AM|PM)?", text, re.IGNORECASE)
    if match_full:
        date_str = match_full.group(1)
        h, m, ampm = int(match_full.group(2)), int(match_full.group(3)), (match_full.group(4) or "").upper()
        if h == 0: h = 12
        if h > 12: h -= 12
        return f"{date_str} {h:02d}:{m:02d} {ampm}"

    match = re.search(r"(\d{1,2})\s*[:\.]\s*(\d{2})\s*(AM|PM)?", text, re.IGNORECASE)
    if match:
        h, m, ampm = int(match.group(1)), int(match.group(2)), (match.group(3) or "").upper()
        if not ampm:
            if h >= 24: h = 0
            if h == 0: ampm, h = 12
            elif h == 12: ampm = "PM"
            elif h > 12: h -= 12; ampm = "PM"
            else: ampm = "AM"
        else:
            if h == 0: h = 12
            if h > 12: h -= 12
        return f"{h:02d}:{m:02d} {ampm}"

    match_short = re.search(r"(\d{1,2})\s*(AM|PM)", text, re.IGNORECASE)
    if match_short:
        h, ampm = int(match_short.group(1)), match_short.group(2).upper()
        if h == 0: h = 12
        if h > 12: h -= 12
        return f"{h:02d}:00 {ampm}"
    return text.title()

def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    else:
        m = int(seconds // 60)
        s = seconds % 60
        if s == 0:
            return f"{m}m"
        return f"{m}m {s:.1f}s"

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("âž• Create Manual Quiz", callback_data="newquiz")],
        [InlineKeyboardButton("ðŸ“… Schedule Auto-Quiz", callback_data="autoschedule_start")],
        [InlineKeyboardButton("ðŸ“š My Quizzes", callback_data="myquizzes"), InlineKeyboardButton("ðŸ“‚ Categories", callback_data="categories")],
        [InlineKeyboardButton("ðŸ“¢ Broadcast to Groups", callback_data="broadcast_setup")],
        [InlineKeyboardButton("ðŸ† Global Rank", callback_data="show_rank"), InlineKeyboardButton("ðŸ‘¥ Registered Groups", callback_data="groups")],
        [InlineKeyboardButton("ðŸ§¹ Clean Chat", callback_data="clearchat_main")]
    ])

def question_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("âœ… OK (Done)", callback_data="done"), InlineKeyboardButton("âš¡ Add More", callback_data="addmore")],
        [InlineKeyboardButton("âœï¸ Edit Last", callback_data="editlast"), InlineKeyboardButton("â†©ï¸ Undo Last", callback_data="undolast")],
        [InlineKeyboardButton("ðŸ§¹ Clear Chat", callback_data="clearchat_qs"), InlineKeyboardButton("ðŸ—‘ï¸ Clear All", callback_data="clearall")]
    ])

def timer_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("20 sec", callback_data="timer_20"), InlineKeyboardButton("30 sec", callback_data="timer_30")],
        [InlineKeyboardButton("40 sec", callback_data="timer_40"), InlineKeyboardButton("45 sec", callback_data="timer_45")],
        [InlineKeyboardButton("60 sec", callback_data="timer_60"), InlineKeyboardButton("âœï¸ Custom", callback_data="timer_custom")]
    ])

def marking_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("âž•4 / âž–1", callback_data="mark_4_-1")],
        [InlineKeyboardButton("âž•1 / âž–0.25", callback_data="mark_1_-0.25")],
        [InlineKeyboardButton("âž•1 / 0", callback_data="mark_1_0")]
    ])

def shuffle_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("âŒ No Shuffle", callback_data="shuffle_none")],
        [InlineKeyboardButton("ðŸ”€ Questions", callback_data="shuffle_questions")],
        [InlineKeyboardButton("ðŸ”€ Answers", callback_data="shuffle_answers")],
        [InlineKeyboardButton("ðŸ”€ All", callback_data="shuffle_all")]
    ])

def mode_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ðŸ† Live Quiz", callback_data="mode_live")],
        [InlineKeyboardButton("ðŸ“ Direct Polls", callback_data="mode_direct")]
    ])

def autodel_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 min", callback_data="autodel_60")],
        [InlineKeyboardButton("5 min", callback_data="autodel_300")],
        [InlineKeyboardButton("15 min", callback_data="autodel_900")],
        [InlineKeyboardButton("30 min", callback_data="autodel_1800")],
        [InlineKeyboardButton("50 min", callback_data="autodel_3000")],
        [InlineKeyboardButton("120 min", callback_data="autodel_7200")],
        [InlineKeyboardButton("âŒ Auto-Delete OFF", callback_data="autodel_0")]
    ])

def normalize(text):
    return re.sub(r"\r\n?", "\n", text or "").strip()

def parse_question(block):
    block = normalize(block)
    if not block: return None

    custom_timer = None
    timer_match = TIMER_REGEX.search(block)
    if timer_match:
        custom_timer = int(timer_match.group(1))
        block = block[:timer_match.start()] + block[timer_match.end():]

    answer_idx = -1
    explanation = "No explanation provided."

    exp_match = EXP_REGEX.search(block)
    if exp_match:
        explanation = exp_match.group(1).strip()
        block = block[:exp_match.start()].strip()

    ans_match = ANS_REGEX.search(block)
    if ans_match:
        ans_str = ans_match.group(1).lower().strip()
        mapping = {"a":0, "b":1, "c":2, "d":3, "e":4, "1":0, "2":1, "3":2, "4":3, "5":4}
        answer_idx = mapping.get(ans_str, -1)
        block = re.sub(r"(?i)(?:\b|^\s*)(?:correct\s*answer|answer|ans|correct\s*option)\s*[:\-]?\s*[\(]?[a-e1-5][\)]?(?:\s|$)", "", block).strip()

    lines = block.split('\n')
    block = '\n'.join([l for l in lines if not re.match(r"(?im)^(?:question\s*id.*)$", l.strip())])

    options = []
    q_lines = []

    opt_marker_match = OPT_MARKER_REGEX.search(block)

    if opt_marker_match:
        q_part = block[:opt_marker_match.start()].strip()
        opt_part = block[opt_marker_match.end():].strip()

        q_lines = q_part.split('\n')

        opt_matches = list(OPT_MATCH_REGEX.finditer(opt_part))
        if opt_matches:
            for i in range(len(opt_matches)):
                start = opt_matches[i].end()
                end = opt_matches[i+1].start() if i+1 < len(opt_matches) else len(opt_part)
                opt_text = opt_part[start:end].strip()
                prefix = opt_matches[i].group(1)
                if "âœ“" in prefix or "âœ…" in prefix or "âœ”" in prefix: answer_idx = i
                options.append(opt_text)
        else:
            options = [l.strip() for l in opt_part.split('\n') if l.strip()]
    else:
        mode = "question"
        for line in block.split('\n'):
            line = line.strip()
            if not line: continue

            opt_match = re.match(r"^([^a-zA-Z0-9\(\)]*)[\(]?([a-e])[\)\.\-:]+\s+(.+)$", line, re.I)
            num_match = re.match(r"^([^a-zA-Z0-9\(\)]*)[\(]?([1-5])[\)\.\-:]+\s+(.+)$", line, re.I)

            if opt_match and mode in ["question", "options"]:
                prefix = opt_match.group(1)
                if "âœ“" in prefix or "âœ…" in prefix: answer_idx = len(options)
                options.append(opt_match.group(3).strip())
                mode = "options"
            elif num_match and mode == "options":
                prefix = num_match.group(1)
                if "âœ“" in prefix or "âœ…" in prefix: answer_idx = len(options)
                options.append(num_match.group(3).strip())
            else:
                if mode == "question":
                    q_lines.append(line)
                elif mode == "options":
                    if options: options[-1] += " " + line

        if len(options) < 2:
            options = []
            q_lines = []
            mode = "question"
            for line in block.split('\n'):
                line = line.strip()
                if not line: continue
                num_match = re.match(r"^([^a-zA-Z0-9\(\)]*)[\(]?([1-5])[\)\.\-:]+\s+(.+)$", line, re.I)
                if num_match and mode in ["question", "options"]:
                    prefix = num_match.group(1)
                    if "âœ“" in prefix or "âœ…" in prefix: answer_idx = len(options)
                    options.append(num_match.group(3).strip())
                    mode = "options"
                else:
                    if mode == "question": q_lines.append(line)
                    elif mode == "options":
                        if options: options[-1] += " " + line

    question = "\n".join(q_lines).strip()
    question = re.sub(r"^(?:q|question|que)?\.?\s*\d+\s*[\.\:\-\)]?\s*", "", question, flags=re.I).strip()

    if len(options) > 10: options = options[:10]

    if not question or len(options) < 2: return None
    if answer_idx == -1 or answer_idx >= len(options): answer_idx = 0

    result = {"question": question, "options": options, "correct": answer_idx, "explanation": explanation}
    if custom_timer: result["timer"] = custom_timer
    return result

def parse_many(text):
    text = normalize(text)
    if not text: return []

    ans_count = len(re.findall(r"(?i)(?:\b|^\s*)(?:correct\s*answer|answer|ans|correct\s*option)\s*[:\-]?\s*[\(]?[a-e1-5][\)]?(?:\s|$)", text))
    q_single = parse_question(text)

    if q_single and ans_count <= 1:
        opts_count = len(re.findall(r"(?im)^options\s*[:\-]?\s*", text))
        if opts_count <= 1:
            return [q_single]

    parts = re.split(r"(?im)^\s*(?:q|question|que)\.?\s*\d+[\.\:\-\)]?\s+", text)
    if len(parts) <= 1:
        parts = re.split(r"\n\s*\n+", text)

    result = []
    for part in parts:
        if not part.strip(): continue
        q = parse_question(part)
        if q: result.append(q)

    if len(result) < 2 and len(text) > 100:
        alt_parts = re.split(r"(?im)^\s*\d+[\.\:\-\)]\s+", "\n" + text)
        alt_result = []
        for p in alt_parts:
            if not p.strip(): continue
            q = parse_question(p)
            if q: alt_result.append(q)
        if len(alt_result) > len(result):
            result = alt_result

    return result

def clean_markdown_name(name):
    return str(name or "Unknown").replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "")

def escape_markdown(text):
    text = str(text or "")
    for ch in ("_", "*", "`", "["): text = text.replace(ch, "\\" + ch)
    return text

async def is_banned(uid): return uid in banned_users

async def register_user(update):
    global needs_save
    user = update.effective_user
    if not user: return
    uid = str(user.id)
    if uid not in users_data:
        users_data[uid] = {"name": user.full_name, "username": user.username, "xp": 0, "played": 0, "streak": 0, "last_play_date": "", "correct_answers": 0, "wrong_answers": 0, "fast_answers": 0, "is_blocked": False, "topic_stats": {}, "monthly_xp": 0, "monthly_played": 0, "last_month": ""}
        needs_save = True

async def is_group_admin(context, chat_id, user_id):
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception: return False

def get_lobby_text(quiz, ready_count):
    sub = quiz.get("subject", "Uncategorized")
    top = quiz.get("topic", "General")
    stime = quiz.get("schedule_time", "Manual Start")
    qs = len(quiz.get("questions", []))
    tm = quiz.get("timer", 30)
    mc = quiz.get("mark_correct", 4)
    mw = quiz.get("mark_wrong", -1)

    return (
        f"ðŸŒ¿ HORTICULTURE MASTER\n"
        f"ðŸ”´ LIVE QUIZ\n\n"
        f"ðŸ“š Category: {sub}\n"
        f"ðŸ“Œ Topic: {top}\n"
        f"ðŸ•¤ Starts: {stime}\n"
        f"â“ Questions: {qs}\n"
        f"â± Time: {tm} sec / Question\n"
        f"ðŸŽ¯ Marking: +{mc:g} / {mw:g}\n\n"
        f"ðŸ”¥ Get Ready! Quiz Starts Shortly..."
    )

def get_user_rank_title(xp):
    if xp <= 500: return "Beginner"
    if xp <= 2000: return "Intermediate"
    if xp <= 5000: return "Advanced"
    if xp <= 10000: return "Expert"
    return "Horticulture Master ðŸ‘‘"

# =========================================================
# ðŸŸ¢ COMMAND HANDLERS
# =========================================================

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    name = update.effective_user.full_name
    username = update.effective_user.username

    if uid not in users_data:
        users_data[uid] = {"name": name, "username": username, "xp": 0, "played": 0, "streak": 0, "last_play_date": "", "correct_answers": 0, "wrong_answers": 0, "fast_answers": 0, "is_blocked": False, "topic_stats": {}, "monthly_xp": 0, "monthly_played": 0, "last_month": ""}
        global needs_save
        needs_save = True

    user = users_data.get(uid)
    user["username"] = username

    current_month = datetime.datetime.now(IST_TZ).strftime("%Y-%m")
    if user.get("last_month") != current_month:
        user["monthly_xp"] = 0
        user["monthly_played"] = 0
        user["last_month"] = current_month
        needs_save = True

    xp = user.get("xp", 0)
    streak = user.get("streak", 0)
    name_clean = clean_markdown_name(user.get("name", name))
    rank = get_user_rank_title(xp)

    total_correct = user.get("correct_answers", 0)
    total_wrong = user.get("wrong_answers", 0)
    total_fast = user.get("fast_answers", 0)
    total_qs = total_correct + total_wrong
    accuracy = (total_correct / total_qs * 100) if total_qs > 0 else 0

    if xp <= 500: next_tier, next_name = 501 - xp, "Intermediate"
    elif xp <= 2000: next_tier, next_name = 2001 - xp, "Advanced"
    elif xp <= 5000: next_tier, next_name = 5001 - xp, "Expert"
    elif xp <= 10000: next_tier, next_name = 10001 - xp, "Horticulture Master ðŸ‘‘"
    else: next_tier, next_name = 0, "Max Level"

    text = (
        f"ðŸ‘¤ *YOUR DETAILED PROFILE*\n\n"
        f"ðŸ“› *Name:* {name_clean}\n"
        f"ðŸ‘‘ *Rank:* {rank}\n"
        f"ðŸ”¥ *Current Streak:* {streak} Days\n\n"
        f"ðŸ“… *MONTHLY STATS ({current_month})*\n"
        f"âœ¨ *Monthly XP:* {user.get('monthly_xp', 0):g}\n"
        f"ðŸ“ *Quizzes Played:* {user.get('monthly_played', 0)}\n\n"
        f"ðŸ“Š *LIFETIME ANALYTICS*\n"
        f"âœ¨ *Total XP:* {xp:g}\n"
        f"ðŸ“ *Total Played:* {user.get('played', 0)}\n"
        f"âœ… *Correct Answers:* {total_correct}\n"
        f"âŒ *Wrong Answers:* {total_wrong}\n"
        f"âš¡ *Fast Answers:* {total_fast}\n"
        f"ðŸŽ¯ *Overall Accuracy:* {accuracy:.1f}%\n\n"
    )

    topic_stats = user.get("topic_stats", {})
    if topic_stats:
        text += "ðŸ“ˆ *TOPIC STRENGTHS*\n"
        topic_accuracies = []
        for top, data in topic_stats.items():
            t_cor = data.get("correct", 0)
            t_tot = t_cor + data.get("wrong", 0)
            if t_tot >= 5:
                acc = (t_cor/t_tot)*100
                topic_accuracies.append((top, acc))
        topic_accuracies.sort(key=lambda x: x[1], reverse=True)
        if topic_accuracies:
            text += f"ðŸ’ª Strongest: *{topic_accuracies[0][0]}* ({topic_accuracies[0][1]:.1f}%)\n"
            if len(topic_accuracies) > 1:
                text += f"ðŸ“‰ Weakest: *{topic_accuracies[-1][0]}* ({topic_accuracies[-1][1]:.1f}%)\n\n"

    if user.get("last_quiz_title"):
        text += (
            f"ðŸ•’ *LAST QUIZ DETAILS*\n"
            f"ðŸ“š *Topic:* {user.get('last_quiz_title')}\n"
            f"ðŸ† *Score:* {user.get('last_quiz_score', 0):g}\n"
            f"âœ… *Correct:* {user.get('last_quiz_correct', 0)} | âŒ *Wrong:* {user.get('last_quiz_wrong', 0)}\n\n"
        )

    if next_tier > 0: text += f"ðŸŽ¯ *Need {next_tier:g} more XP to reach {next_name}!*"
    else: text += f"ðŸŒŸ *You have reached the highest possible rank!*"

    try:
        msg = await update.effective_message.reply_text(text, parse_mode="Markdown")
        track_msg(update.effective_user.id, msg.message_id)
    except Exception as e:
        logger.error(f"Failed to send profile: {e}")

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_document")
        await save_db_sync()
        with open(DB_FILE, "rb") as db_file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=db_file,
                caption="ðŸ’¾ *Database Backup Completed!*\nAll users, streaks, and quizzes are safe.",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.effective_message.reply_text(f"âŒ Backup failed: {e}")

async def clear_chat_action(uid, chat_id, context):
    if uid in bot_message_tracker:
        for mid in list(bot_message_tracker[uid]):
            try: await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            except BadRequest: pass
            except Exception: pass
        bot_message_tracker[uid].clear()

    st = creation.get(uid)
    if st and "chat_msgs" in st:
        for mid in st["chat_msgs"]:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            except BadRequest: pass
            except Exception: pass
        st["chat_msgs"] = []

    anim_msg = await context.bot.send_message(chat_id, "ðŸ§¹ *Cleaning Chat...*", parse_mode="Markdown")
    await asyncio.sleep(0.4)
    try: await context.bot.edit_message_text(chat_id=chat_id, message_id=anim_msg.message_id, text="â™»ï¸ *Removing old messages...*", parse_mode="Markdown")
    except: pass
    await asyncio.sleep(0.4)
    try: await context.bot.edit_message_text(chat_id=chat_id, message_id=anim_msg.message_id, text="âœ¨ *Chat Cleaned Successfully!*", parse_mode="Markdown")
    except: pass
    await asyncio.sleep(1)
    try: await context.bot.delete_message(chat_id=chat_id, message_id=anim_msg.message_id)
    except: pass

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    if update.effective_message:
        try: await update.effective_message.delete()
        except: pass
    await clear_chat_action(uid, chat_id, context)
    msg = await context.bot.send_message(
        chat_id,
        "ðŸŒ± Horticulture Master Quiz Bot v25.0 ULTRA PRO\n\nâœ… Auto-Scheduler Engine\nâœ… MS Word Downloads\nâœ… Forward Messages To Groups!\n\nðŸ‘‡ Select an option:",
        parse_mode="Markdown", reply_markup=main_menu()
    )
    track_msg(uid, msg.message_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await is_banned(uid): return
    creation.pop(uid, None)
    await register_user(update)
    if update.effective_message:
        try: await update.effective_message.delete()
        except: pass
    msg = await context.bot.send_message(
        update.effective_chat.id,
        "ðŸŒ± Horticulture Master Quiz Bot v25.0 ULTRA PRO\n\nâœ… Auto-Scheduler Engine\nâœ… MS Word Downloads\nâœ… Forward Messages To Groups!\n\nðŸ‘‡ Select an option:",
        parse_mode="Markdown", reply_markup=main_menu()
    )
    track_msg(uid, msg.message_id)

async def list_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = "ðŸ‘¥ USERS WHO STARTED THE BOT:\n\n"
    count = 0
    for uid, data in users_data.items():
        text += f"ðŸ‘¤ {clean_markdown_name(data.get('name', 'Unknown'))} (@{data.get('username', 'No_User')}) ID:{uid}\n"
        count += 1
    final_text = f"ðŸ“Š *Total Users:* {count}\n\n" + text
    if len(final_text) > 4000:
        for x in range(0, len(final_text), 4000): await update.effective_message.reply_text(final_text[x:x+4000], parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(final_text, parse_mode="Markdown")

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.effective_message.reply_text("âš ï¸ Usage: /approve USER_ID", parse_mode="Markdown")
        return
    try:
        target = int(context.args[0])
        if target not in approved_users:
            approved_users.append(target)
            needs_save = True
        await update.effective_message.reply_text(f"âœ… User {target} is now APPROVED to use the bot.", parse_mode="Markdown")
        try: await context.bot.send_message(target, "ðŸŸ¢ Good News!\nBoss Akash Dwivedi has given the green signal. You can now use the bot! Send /start to begin.", parse_mode="Markdown")
        except Exception: pass
    except Exception:
        await update.effective_message.reply_text("âŒ Invalid User ID.")

async def revoke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.effective_message.reply_text("âš ï¸ Usage: /revoke USER_ID", parse_mode="Markdown")
        return
    try:
        target = int(context.args[0])
        if target in approved_users:
            approved_users.remove(target)
            needs_save = True
        await update.effective_message.reply_text(f"âŒ User {target} access revoked.", parse_mode="Markdown")
    except Exception:
        await update.effective_message.reply_text("âŒ Invalid User ID.")

async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    chat, user = update.effective_chat, update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("âš ï¸ Please use this command inside a group.")
        return
    if user.id != ADMIN_ID and not await is_group_admin(context, chat.id, user.id):
        await update.effective_message.reply_text("âŒ Only group admins can register.")
        return
    saved_groups[str(chat.id)] = {"title": chat.title or str(chat.id), "type": chat.type, "registered_by": user.id}
    needs_save = True
    await update.effective_message.reply_text(f"âœ… Group Registered!\n\nðŸ“¢ {escape_markdown(chat.title)}\nðŸ†” {chat.id}", parse_mode="Markdown")

async def unregister_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    chat, user = update.effective_chat, update.effective_user
    if not chat or chat.type not in ("group", "supergroup"): return
    if user.id != ADMIN_ID and not await is_group_admin(context, chat.id, user.id): return
    gid = str(chat.id)
    if gid in saved_groups:
        saved_groups.pop(gid, None)
        needs_save = True
        await update.effective_message.reply_text("âœ… Group unregistered.")

async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if await is_banned(update.effective_user.id): return
    user = users_data.get(uid, {"xp": 0, "played": 0, "streak": 0})
    lb = sorted(users_data.values(), key=lambda x: x.get("xp", 0), reverse=True)
    text = f"ðŸŒ *--- HORTICULTURE LEADERBOARD ---*\n\nâœ¨ Your XP: *{user.get('xp', 0):g}*\nðŸ“ Played: *{user.get('played', 0)}*\nðŸ”¥ Streak: *{user.get('streak', 0)}*\n\nðŸ† *TOP 10 PLAYERS*\n\n"
    for i, p in enumerate(lb[:10], 1):
        medal = "ðŸ¥‡" if i == 1 else "ðŸ¥ˆ" if i == 2 else "ðŸ¥‰" if i == 3 else "ðŸ…"
        p_title = get_user_rank_title(p.get('xp', 0))
        text += f"{medal} *{clean_markdown_name(p.get('name'))}*\n â†³ {p_title} | XP: `{p.get('xp', 0):g}` | ðŸ”¥ `{p.get('streak', 0)}`\n\n"
    target = update.callback_query.message if update.callback_query else update.effective_message
    if update.callback_query: await target.edit_text(text, parse_mode="Markdown")
    else:
        msg = await target.reply_text(text, parse_mode="Markdown")
        track_msg(update.effective_user.id, msg.message_id)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    players = sorted(users_data.values(), key=lambda x: x.get("xp", 0), reverse=True)
    text = f"ðŸ“Š BOT ANALYTICS\n\nðŸ‘¥ Users: {len(users_data)}\nðŸ“¢ Groups: {len(saved_groups)}\nðŸ“š Quizzes: {len(quizzes)}\n\nðŸ† TOP 5\n"
    for i, p in enumerate(players[:5], 1):
        text += f"{i}. {clean_markdown_name(p.get('name'))} â€” {p.get('xp', 0):g} XP\n"
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.effective_message.reply_text("Usage: /ban USER_ID")
        return
    try:
        target = int(context.args[0])
        if target not in banned_users:
            banned_users.append(target)
            needs_save = True
        await update.effective_message.reply_text(f"âœ… User {target} banned.", parse_mode="Markdown")
    except Exception: await update.effective_message.reply_text("âŒ Invalid User ID.")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.effective_message.reply_text("Usage: /unban USER_ID")
        return
    try:
        target = int(context.args[0])
        if target in banned_users:
            banned_users.remove(target)
            needs_save = True
        await update.effective_message.reply_text(f"âœ… User {target} unbanned.", parse_mode="Markdown")
    except Exception: await update.effective_message.reply_text("âŒ Invalid User ID.")

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save
    if update.effective_user.id != ADMIN_ID: return
    stopped = 0
    for sid, session in list(group_sessions.items()):
        if session.get("running"):
            session["running"] = False
            task = session.get("timer_task")
            if task: task.cancel()
            stopped += 1
    needs_save = True
    await update.effective_message.reply_text(f"ðŸ›‘ Active quizzes stopped: {stopped}")

# =========================================================
# ðŸ’¬ MESSAGE HANDLER & STATE MANAGEMENT
# =========================================================

def sync_parse_pdf(byte_array):
    if not HAS_PDF: return ""
    reader = PyPDF2.PdfReader(BytesIO(byte_array))
    file_text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted: file_text += extracted + "\n"
    return file_text

def sync_parse_docx(byte_array):
    if not HAS_DOCX: return ""
    file_text = ""
    try:
        from docx.document import Document as _Document
        from docx.oxml.text.paragraph import CT_P
        from docx.oxml.table import CT_Tbl
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc_file = docx.Document(BytesIO(byte_array))
        for child in doc_file.element.body:
            if isinstance(child, CT_P):
                file_text += Paragraph(child, doc_file).text + "\n"
            elif isinstance(child, CT_Tbl):
                table = Table(child, doc_file)
                for row in table.rows:
                    file_text += " | ".join([cell.text.replace("\n", " ").strip() for cell in row.cells]) + "\n"
                file_text += "\n"
    except Exception as e:
        logger.error(f"Advanced DOCX Parsing Error: {e}")
        doc_file = docx.Document(BytesIO(byte_array))
        file_text = "\n".join([para.text for para in doc_file.paragraphs])
    return file_text

async def finalize_quiz(uid, context, target_message):
    st = creation.get(uid)
    if not st: return

    quiz_id = f"{uid}_{int(time.time()*1000)}"
    sub = st.get("subject", "Uncategorized")
    top = st.get("topic", "General")

    quizzes[quiz_id] = {
        "quiz_id": quiz_id,
        "subject": sub,
        "topic": top,
        "title": f"{sub} - {top}",
        "questions": st["questions"],
        "timer": st["timer"],
        "mark_correct": st["mark_correct"],
        "mark_wrong": st["mark_wrong"],
        "shuffle": st["shuffle"],
        "mode": st["quiz_mode"],
        "auto_delete": st["auto_delete"],
        "schedule_time": st.get("schedule_time", "Off"),
        "end_message": st.get("end_message", ""),
        "owner": uid,
        "created": time.time(),
        "leaderboard": []
    }
    global needs_save
    needs_save = True
    creation.pop(uid, None)

    quiz = quizzes[quiz_id]

    auto_del_val = int(quiz.get("auto_delete", 0))
    del_text = "OFF" if auto_del_val == 0 else f"{auto_del_val//60} mins"

    try:
        anim_msg = await target_message.edit_text("â³ *Finalizing Quiz Settings...*", parse_mode="Markdown")
        await asyncio.sleep(0.4)
        await target_message.edit_text("âš¡ *Saving to Database...*", parse_mode="Markdown")
        await asyncio.sleep(0.4)
    except Exception: pass

    text = (f"ðŸ“š *Quiz Ready!*\n\n"
            f"ðŸ“– Category: *{escape_markdown(quiz['subject'])}*\n"
            f"ðŸ“Œ Topic: *{escape_markdown(quiz['topic'])}*\n"
            f"ðŸ•¤ Schedule: *{quiz['schedule_time']}*\n"
            f"â“ Questions: *{len(quiz['questions'])}*\n"
            f"â± Timer: *{quiz['timer']} sec*\n"
            f"ðŸŽ¯ Marking: *+{quiz['mark_correct']:g} / {quiz['mark_wrong']:g}*\n"
            f"ðŸ”€ Shuffle: *{quiz['shuffle']}*\n"
            f"ðŸ—‘ Auto-Delete: *{del_text}*")

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("ðŸ“¢ Share Quiz", callback_data=f"share|{quiz_id}")],
        [InlineKeyboardButton("ðŸ”™ My Quizzes", callback_data="myquizzes")]
    ])
    try: await target_message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        msg = await target_message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        track_msg(uid, msg.message_id)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save, system_data
    if not update.effective_user: return
    uid = update.effective_user.id
    if await is_banned(uid): return
    message = update.effective_message

    track_msg(uid, message.message_id)

    st = creation.get(uid)
    if not st: return

    # ðŸ“¢ BROADCAST HANDLING
    if st.get("mode") == "wait_broadcast":
        if uid != ADMIN_ID: return
        st["mode"] = "done"
        await message.reply_text(
            "âœ… Message received! Click the button below to forward it to all registered groups.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ðŸ“¢ Forward to Registered Groups", callback_data=f"fw_bcast|{message.message_id}")],
                [InlineKeyboardButton("âŒ Cancel", callback_data="mainmenu")]
            ])
        )
        return

    text = ""
    if message.photo and not message.poll:
        caption_text = normalize(message.caption)
        if caption_text:
            text = caption_text
        elif HAS_OCR and st.get("mode") in ("questions", "append_q", "edit", "wait_eq_text"):
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            try:
                m_load = await message.reply_text("â³ *Scanning Image using AI OCR...*", parse_mode="Markdown")
                file = await message.photo[-1].get_file()
                byte_array = await file.download_as_bytearray()
                def run_ocr():
                    img = Image.open(BytesIO(byte_array))
                    return pytesseract.image_to_string(img)
                ocr_text = await asyncio.to_thread(run_ocr)
                text = ocr_text.strip()
                await context.bot.delete_message(chat_id=message.chat_id, message_id=m_load.message_id)
            except Exception as e:
                logger.error(f"OCR Error: {e}")
                try: await context.bot.delete_message(chat_id=message.chat_id, message_id=m_load.message_id)
                except: pass
    else:
        text = normalize(message.text)

    if st.get("mode") == "wait_custom_timer":
        if not text.isdigit():
            m = await message.reply_text("âŒ Please send a valid number in seconds.")
            track_msg(uid, m.message_id)
            return
        st["timer"] = int(text)
        st["mode"] = "done"
        m = await message.reply_text(f"â±ï¸ Timer: *{st['timer']} seconds*\n\nðŸ“Š Select marking scheme:", parse_mode="Markdown", reply_markup=marking_menu())
        track_msg(uid, m.message_id)
        return

    if st.get("mode") == "eq_wait_custom_timer":
        quiz = quizzes.get(st.get("qid"))
        if not quiz: return
        if not text.isdigit():
            m = await message.reply_text("âŒ Please send a valid number.")
            track_msg(uid, m.message_id)
            return
        quiz["timer"] = int(text)
        needs_save = True
        st["mode"] = "done"
        m = await message.reply_text(f"âœ… Timer updated to {quiz['timer']} seconds!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if st.get("mode") == "wait_auto_rand_count":
        if not text.isdigit():
            m = await message.reply_text("âŒ Please send a valid number.")
            track_msg(uid, m.message_id)
            return
        count = int(text)
        quiz_id = st["qid"]
        rand_mode = st["rand_mode"]
        quiz = quizzes.get(quiz_id)

        if not quiz: return

        pool = []
        for qid, q_data in quizzes.items():
            if qid != quiz_id:
                if uid == ADMIN_ID or str(q_data.get("owner")) == str(uid):
                    pool.extend(q_data.get("questions", []))

        if len(pool) == 0:
            m = await message.reply_text("âŒ Not enough questions in your other quizzes to pull from.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back", callback_data=f"editquiz|{quiz_id}")]]))
            track_msg(uid, m.message_id)
            st["mode"] = "done"
            return

        random.shuffle(pool)
        selected_qs = pool[:count]

        if rand_mode == "replace":
            quiz["questions"] = selected_qs
        else:
            quiz["questions"].extend(selected_qs)

        needs_save = True

        m = await message.reply_text(
            f"âœ… *Successfully added {len(selected_qs)} random questions!*\n\nðŸ“š Total Questions now: *{len(quiz['questions'])}*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{quiz_id}")]])
        )
        track_msg(uid, m.message_id)
        st["mode"] = "done"
        return

    if st.get("mode") == "wait_auto_count":
        if not text.isdigit():
            m = await message.reply_text("âŒ Please send a valid number for question count.")
            track_msg(uid, m.message_id)
            return
        st["auto_count"] = int(text)
        st["mode"] = "wait_auto_time"
        m = await message.reply_text(f"âœ… *Count Saved: {st['auto_count']}*\n\nðŸ•¤ Send the specific Date & Time for this to auto-start.\nExample: `25/08/2026 10:00 AM` or simply `10:00 AM` for today.", parse_mode="Markdown")
        track_msg(uid, m.message_id)
        return

    if st.get("mode") == "wait_auto_time":
        if not text: return
        schedule_str = format_schedule_time(text)

        anim = await message.reply_text("â³ *Generating Custom Scheduled Quiz...*", parse_mode="Markdown")
        await asyncio.sleep(0.5)

        pool = []
        for qid, q in quizzes.items():
            if st["auto_cat"] == "Random" or q.get("subject", "") == st["auto_cat"]:
                pool.extend(q.get("questions", []))

        if len(pool) == 0:
            await anim.edit_text("âŒ No questions found for this selection. Try another category.")
            st["mode"] = "done"
            return

        random.shuffle(pool)
        selected_qs = pool[:st["auto_count"]]

        new_quiz_id = f"auto_{int(time.time()*1000)}"
        quizzes[new_quiz_id] = {
            "quiz_id": new_quiz_id,
            "subject": f"Auto Scheduled - {st['auto_cat']}",
            "topic": "Daily Challenge",
            "title": f"Auto - {st['auto_cat']}",
            "questions": selected_qs,
            "timer": 30,
            "mark_correct": 4,
            "mark_wrong": -1,
            "shuffle": "all",
            "mode": "live",
            "auto_delete": 0,
            "schedule_time": schedule_str,
            "end_message": "",
            "owner": uid,
            "created": time.time(),
            "leaderboard": []
        }

        system_data["auto_schedules"].append({
            "group_id": st["auto_gid"],
            "quiz_id": new_quiz_id,
            "trigger_time": schedule_str,
            "owner": uid
        })
        needs_save = True

        await anim.edit_text(f"âœ… *Auto-Quiz Scheduled Successfully!*\n\nðŸ“¢ Group: {st['auto_gname']}\nðŸ“š Category: {st['auto_cat']}\nâ“ Questions: {len(selected_qs)}\nðŸ•¤ Scheduled For: {schedule_str}\n\nðŸ‘‡ *You can edit marking, timer, or other settings below before it starts!*", parse_mode="Markdown")
        st["mode"] = "done"

        quiz_auto = quizzes[new_quiz_id]
        buttons = [
            [InlineKeyboardButton("âž• Add Qs", callback_data=f"q_add|{new_quiz_id}"), InlineKeyboardButton("ðŸŽ² Random Qs", callback_data=f"eq_auto_rand|{new_quiz_id}")],
            [InlineKeyboardButton("ðŸ—‘ï¸ Delete Qs (Bulk)", callback_data=f"q_bulk|{new_quiz_id}"), InlineKeyboardButton("âœï¸ Specific Q", callback_data=f"eq_spec_q|{new_quiz_id}")],
            [InlineKeyboardButton("âœï¸ Category", callback_data=f"eq_menu_sub|{new_quiz_id}"), InlineKeyboardButton("âœï¸ Topic", callback_data=f"eq_menu_top|{new_quiz_id}")],
            [InlineKeyboardButton("â±ï¸ Timer", callback_data=f"eq_menu_timer|{new_quiz_id}"), InlineKeyboardButton("ðŸ“Š Marking", callback_data=f"eq_menu_mark|{new_quiz_id}")],
            [InlineKeyboardButton("ðŸ”€ Shuffle", callback_data=f"eq_menu_shuf|{new_quiz_id}"), InlineKeyboardButton("ðŸ”„ Mode", callback_data=f"eq_menu_mode|{new_quiz_id}")],
            [InlineKeyboardButton("ðŸ•¤ Schedule Time", callback_data=f"eq_menu_sch|{new_quiz_id}"), InlineKeyboardButton("ðŸ—‘ï¸ Auto-Delete", callback_data=f"eq_menu_autodel|{new_quiz_id}")],
            [InlineKeyboardButton("ðŸ End Message", callback_data=f"eq_menu_end|{new_quiz_id}")],
            [InlineKeyboardButton("ðŸ“„ MS Word Report", callback_data=f"eq_dl_word|{new_quiz_id}")],
            [InlineKeyboardButton("ðŸ”™ Back to Quiz", callback_data=f"quizview|{new_quiz_id}")]
        ]

        auto_del_val = int(quiz_auto.get('auto_delete', 0))
        auto_del_str = 'OFF' if auto_del_val == 0 else f"{auto_del_val//60} mins"

        await context.bot.send_message(
            message.chat_id,
            f"âš™ï¸ *Edit Auto-Quiz Settings*\n\n"
            f"ðŸ“– Category: *{escape_markdown(quiz_auto.get('subject','Uncategorized'))}*\n"
            f"ðŸ“Œ Topic: *{escape_markdown(quiz_auto.get('topic','General'))}*\n\n"
            f"ðŸ“ Total Qs: {len(quiz_auto['questions'])}\n"
            f"â±ï¸ Timer: {quiz_auto.get('timer', 30)}s\n"
            f"ðŸ“Š Marking: +{quiz_auto.get('mark_correct', 4):g} / {quiz_auto.get('mark_wrong', -1):g}\n"
            f"ðŸ”€ Shuffle: {quiz_auto.get('shuffle', 'none')}\n"
            f"ðŸ”„ Mode: {quiz_auto.get('mode', 'live').title()}\n"
            f"ðŸ•¤ Schedule: {quiz_auto.get('schedule_time', 'Off')}\n"
            f"ðŸ—‘ï¸ Auto-Delete: {auto_del_str}\n\n"
            "ðŸ‘‡ Choose what you want to edit:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if st.get("mode") in ("questions", "append_q") and message.document:
        if "chat_msgs" not in st: st["chat_msgs"] = []
        st["chat_msgs"].append(message.message_id)

        filename = message.document.file_name.lower()
        if filename.endswith(('.txt', '.csv', '.pdf', '.docx')):
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            try:
                file = await message.document.get_file()
                byte_array = await file.download_as_bytearray()
                file_text = ""

                if filename.endswith(('.txt', '.csv')):
                    file_text = byte_array.decode('utf-8')

                elif filename.endswith('.docx'):
                    if not HAS_DOCX:
                        m = await message.reply_text("âŒ DOCX support missing. Please install `python-docx` on the server.")
                        track_msg(uid, m.message_id)
                        return
                    file_text = await asyncio.to_thread(sync_parse_docx, byte_array)

                elif filename.endswith('.pdf'):
                    if not HAS_PDF:
                        m = await message.reply_text("âŒ PDF support missing. Please run `pip install PyPDF2` on your PythonAnywhere bash console.")
                        track_msg(uid, m.message_id)
                        return
                    file_text = await asyncio.to_thread(sync_parse_pdf, byte_array)

                if not file_text.strip():
                    m = await message.reply_text("âŒ Could not extract any readable text from this file.")
                    track_msg(uid, m.message_id)
                    return

                qs = parse_many(file_text)
                if not qs:
                    m = await message.reply_text("âŒ *Invalid format in text/file.* Could not extract valid questions.\nEnsure answers and options are clear.", parse_mode="Markdown")
                    track_msg(uid, m.message_id)
                    return

                room = MAX_QUESTIONS - len(st.get("questions", quizzes.get(st.get("qid"), {}).get("questions", [])))
                qs = qs[:room]

                if st["mode"] == "append_q":
                    quiz = quizzes.get(st.get("qid"))
                    quiz["questions"].extend(qs)
                    needs_save = True
                    m = await message.reply_text(f"âœ… *Questions Added!*\n\nâž• Added: {len(qs)}\nðŸ“š Total Questions: {len(quiz['questions'])}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
                    st["chat_msgs"].append(m.message_id)
                    track_msg(uid, m.message_id)
                else:
                    st["questions"].extend(qs)
                    m = await message.reply_text(f"âš¡ *Questions Extract Ho Gaye!*\n\nâž• Added: {len(qs)}\nðŸ“š Total: {len(st['questions'])}", parse_mode="Markdown", reply_markup=question_menu())
                    st["chat_msgs"].append(m.message_id)
                    track_msg(uid, m.message_id)
            except Exception as e:
                m = await message.reply_text(f"âŒ Failed to process file: {e}")
                track_msg(uid, m.message_id)
            return
        else:
            m = await message.reply_text("âŒ Please upload only `.txt`, `.csv`, `.pdf`, or `.docx` files.")
            track_msg(uid, m.message_id)
            return

    if st["mode"] == "wait_subject":
        if not text:
            m = await message.reply_text("âŒ Please send the Category/Subject as text (e.g. Vegetable Science).")
            track_msg(uid, m.message_id)
            return
        st["subject"] = text
        st["mode"] = "wait_topic"
        m = await message.reply_text("âœ… *Category Saved!*\n\nðŸ“Œ Now, please send the *Topic* (e.g. Vegetable Breeding):", parse_mode="Markdown")
        st.setdefault("chat_msgs", []).append(m.message_id)
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "wait_topic":
        if not text:
            m = await message.reply_text("âŒ Please send the Topic as text.")
            track_msg(uid, m.message_id)
            return
        st["topic"] = text
        st["mode"] = "questions"
        m = await message.reply_text("âœ… *Topic Saved!*\n\nâš¡ Now send the questions (Or upload a `.txt`, `.pdf`, `.docx` file for Bulk Upload!).", parse_mode="Markdown", reply_markup=question_menu())
        st.setdefault("chat_msgs", []).append(m.message_id)
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "wait_schedule":
        if not text: return
        st["schedule_time"] = format_schedule_time(text)
        st["mode"] = "wait_end_msg"
        m = await message.reply_text(f"âœ… *Schedule Saved as {st['schedule_time']}!*\n\nðŸ“ Now, please send the *Final Message* to be sent after the MS Word report (or type 'Skip' if you don't want any):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("âŒ Skip", callback_data="skip_end_msg")]]))
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "wait_end_msg":
        if not text: return
        if text.lower() == "skip": st["end_message"] = ""
        else: st["end_message"] = text
        await finalize_quiz(uid, context, message)
        return

    if st["mode"] == "eq_spec_sub":
        if not text: return
        quiz = quizzes.get(st.get("qid"))
        if quiz: quiz["subject"] = text; needs_save = True
        st["mode"] = "done"
        m = await message.reply_text(f"âœ… Category updated to: {text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "eq_spec_top":
        if not text: return
        quiz = quizzes.get(st.get("qid"))
        if quiz: quiz["topic"] = text; needs_save = True
        st["mode"] = "done"
        m = await message.reply_text(f"âœ… Topic updated to: {text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "eq_spec_sch":
        if not text: return
        quiz = quizzes.get(st.get("qid"))
        if quiz: quiz["schedule_time"] = format_schedule_time(text); needs_save = True
        st["mode"] = "done"
        m = await message.reply_text(f"âœ… Schedule updated to: {quiz['schedule_time']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "eq_spec_end":
        if not text: return
        quiz = quizzes.get(st.get("qid"))
        if quiz: quiz["end_message"] = text if text.lower() != "skip" else ""; needs_save = True
        st["mode"] = "done"
        m = await message.reply_text(f"âœ… End Message updated!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "bulk_rem_q":
        quiz = quizzes.get(st.get("qid"))
        if not quiz: return
        indices = set()
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = map(int, part.split("-"))
                    for i in range(start, end + 1): indices.add(i - 1)
                except Exception: pass
            elif part.isdigit(): indices.add(int(part) - 1)
        valid_indices = sorted([i for i in indices if 0 <= i < len(quiz["questions"])], reverse=True)
        if not valid_indices:
            m = await message.reply_text("âŒ No valid question numbers found.")
            track_msg(uid, m.message_id)
            return
        for idx in valid_indices: quiz["questions"].pop(idx)
        needs_save = True
        st["mode"] = "done"
        m = await message.reply_text(f"âœ… Successfully removed {len(valid_indices)} questions!\n\nðŸ“š Total remaining: *{len(quiz['questions'])}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Quiz", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if st["mode"] == "wait_eq_num":
        quiz = quizzes.get(st.get("qid"))
        if not quiz: return
        if not text.isdigit():
            m = await message.reply_text("âŒ Please send a valid number.")
            track_msg(uid, m.message_id)
            return
        idx = int(text) - 1
        if idx < 0 or idx >= len(quiz["questions"]):
            m = await message.reply_text(f"âŒ Invalid question number. Please send a number between 1 and {len(quiz['questions'])}.")
            track_msg(uid, m.message_id)
            return
        st["edit_idx"] = idx
        st["mode"] = "wait_eq_text"
        m = await message.reply_text(f"âœ… You are editing *Question {idx + 1}*.\n\nðŸ“ Now send the completely new question text with options, answer, and explanation.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{st['qid']}")]]))
        track_msg(uid, m.message_id)
        return

    if message.poll:
        if st["mode"] not in ("questions", "append_q"):
            m = await message.reply_text("âŒ Send Category & Topic first.")
            track_msg(uid, m.message_id)
            return
        if message.poll.type != "quiz":
            m = await message.reply_text("âŒ Please forward a Telegram Quiz Poll only.")
            track_msg(uid, m.message_id)
            return
        st["questions"].append({"question": message.poll.question, "options": [x.text for x in message.poll.options], "correct": message.poll.correct_option_id, "explanation": message.poll.explanation or "No explanation provided."})
        m = await message.reply_text(f"ðŸ—³ï¸ *Poll Added!*\n\nðŸ“š Total Questions: *{len(st['questions'])}*", parse_mode="Markdown", reply_markup=question_menu())
        st.setdefault("chat_msgs", []).append(m.message_id)
        track_msg(uid, m.message_id)
        return

    if st["mode"] in ("questions", "append_q", "edit", "wait_eq_text"):
        if not text:
            m = await message.reply_text("âŒ Could not read text. Please send valid text or attach a proper caption.")
            track_msg(uid, m.message_id)
            return

        qs = parse_many(text)

        if not qs:
            m = await message.reply_text("âŒ *Invalid format in text/file.* Could not extract valid questions.\nMake sure you have an Answer and Options.", parse_mode="Markdown")
            track_msg(uid, m.message_id)
            return

        if message.photo:
            qs[0]["photo"] = message.photo[-1].file_id

        if st["mode"] == "edit":
            st["questions"][-1] = qs[0]
            st["mode"] = "questions"
            m = await message.reply_text(f"âœï¸ *Last Question Updated!*\n\nTotal: {len(st['questions'])}", parse_mode="Markdown", reply_markup=question_menu())
            st.setdefault("chat_msgs", []).append(m.message_id)
            track_msg(uid, m.message_id)
            return

        elif st["mode"] == "wait_eq_text":
            idx = st["edit_idx"]
            quiz = quizzes.get(st.get("qid"))
            quiz["questions"][idx] = qs[0]
            needs_save = True
            qid = st["qid"]
            st["mode"] = "done"
            m = await message.reply_text(f"âœ… *Question {idx + 1} Successfully Updated!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{qid}")]]))
            track_msg(uid, m.message_id)
            return

        elif st["mode"] == "append_q":
            room = MAX_QUESTIONS - len(quizzes.get(st.get("qid"), {}).get("questions", []))
            qs = qs[:room]
            quiz = quizzes.get(st.get("qid"))
            quiz["questions"].extend(qs)
            needs_save = True
            m = await message.reply_text(f"âœ… *Questions Added!*\n\nâž• Added: {len(qs)}\nðŸ“š Total Questions: {len(quiz['questions'])}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Edit Menu", callback_data=f"editquiz|{st['qid']}")]]))
            st.setdefault("chat_msgs", []).append(m.message_id)
            track_msg(uid, m.message_id)
            return

        elif st["mode"] == "questions":
            room = MAX_QUESTIONS - len(st.get("questions", []))
            qs = qs[:room]
            st["questions"].extend(qs)
            m = await message.reply_text(f"âš¡ *Questions Added!*\n\nâž• Added: {len(qs)}\nðŸ“š Total: {len(st['questions'])}", parse_mode="Markdown", reply_markup=question_menu())
            st.setdefault("chat_msgs", []).append(m.message_id)
            track_msg(uid, m.message_id)
            return

def prepare_quiz_for_run(quiz):
    questions = []
    for original in quiz["questions"]:
        q = dict(original)
        q["options"] = list(original["options"])
        q["correct"] = int(original["correct"])
        questions.append(q)

    mode = quiz.get("shuffle", "none")

    if mode in ("questions", "all"):
        random.shuffle(questions)

    if mode in ("answers", "all"):
        for q in questions:
            opts_with_flags = [(opt, i == q["correct"]) for i, opt in enumerate(q["options"])]
            random.shuffle(opts_with_flags)
            q["options"] = [opt for opt, is_correct in opts_with_flags]
            q["correct"] = next((i for i, (_, is_correct) in enumerate(opts_with_flags) if is_correct), 0)

    return questions

async def start_quiz_from_lobby(sid, context, message=None):
    session = group_sessions.get(sid)
    if not session or session.get("state") != "lobby": return
    if session.get("running"): return

    session["state"] = "running"
    session["running"] = True
    session["sent_msgs"] = []
    quiz = quizzes.get(session["quiz_id"])

    global needs_save
    needs_save = True

    start_text = f"ðŸŒ¿ *HORTICULTURE MASTER*\nðŸ”´ *LIVE QUIZ*\n\nðŸ“š Category: *{escape_markdown(quiz.get('subject', 'Uncategorized'))}*\nðŸ“Œ Topic: *{escape_markdown(quiz.get('topic', 'General'))}*\n\nðŸŸ¢ *Quiz Starting Now! Get Ready!*"

    if message:
        try: await message.edit_text(start_text, parse_mode="Markdown")
        except Exception: pass
        session["sent_msgs"].append(message.message_id)
    elif session.get("lobby_msg_id"):
        try: await context.bot.edit_message_text(chat_id=session["chat_id"], message_id=session["lobby_msg_id"], text=start_text, parse_mode="Markdown")
        except Exception: pass

    await asyncio.sleep(0.5)
    asyncio.create_task(send_group_question(sid, context))

def get_question_timer(quiz, idx, q):
    if q.get("timer"):
        try: return int(q["timer"])
        except Exception: pass
    return int(quiz.get("timer", 30))

async def send_group_question(sid, context):
    global needs_save
    session = group_sessions.get(sid)
    if not session or not session.get("running"): return

    questions = session["questions"]
    idx = session["index"]

    try:
        if idx >= len(questions):
            await finish_group(sid, context)
            return

        q = questions[idx]
        quiz = quizzes.get(session["quiz_id"])
        q_timer = get_question_timer(quiz, idx, q)

        full_question = f"ðŸ“ *Q{idx + 1}/{len(questions)}*\n\n{q['question']}"
        poll_question = f"Q{idx + 1}/{len(questions)}: {q['question']}"

        needs_separate_msg = q.get("photo") or len(poll_question) > 280 or '\n' in q['question']

        if needs_separate_msg:
            if q.get("photo"):
                try:
                    m1 = await context.bot.send_photo(session["chat_id"], q["photo"], caption=full_question[:1024], parse_mode="Markdown")
                    session["sent_msgs"].append(m1.message_id)
                except Exception: pass
            else:
                try:
                    m1 = await context.bot.send_message(session["chat_id"], full_question, parse_mode="Markdown")
                    session["sent_msgs"].append(m1.message_id)
                except BadRequest as err:
                    logger.warning(f"Markdown failed in question {idx+1}, sending raw text. Error: {err}")
                    m1 = await context.bot.send_message(session["chat_id"], f"Q{idx + 1}/{len(questions)}\n\n{q['question']}")
                    session["sent_msgs"].append(m1.message_id)
                except Exception: pass

            poll_question = f"Q{idx + 1}/{len(questions)}: Select the correct option."

        options = [str(x)[:100] for x in q["options"]]
        explanation = q.get("explanation", "Correct Answer!")[:200]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                poll = await context.bot.send_poll(
                    chat_id=session["chat_id"],
                    question=poll_question,
                    options=options,
                    type="quiz",
                    correct_option_id=q["correct"],
                    explanation=explanation,
                    open_period=int(q_timer),
                    is_anonymous=False
                )
                active_polls[poll.poll.id] = {"sid": sid, "index": idx}
                session["active_poll"] = poll.poll.id
                session["question_start"] = time.time()
                session["sent_msgs"].append(poll.message_id)
                session["timer_task"] = asyncio.create_task(group_timer(sid, context, q_timer))
                needs_save = True
                break
            except RetryAfter as e:
                logger.warning(f"Flood control! Sleeping for {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after + 1)
            except Exception as e:
                logger.error(f"Poll Send Error on attempt {attempt + 1}: {e}")
                await asyncio.sleep(2)
        else:
            logger.error("Failed to send question after multiple attempts. Skipping to next question.")
            session["index"] += 1
            await send_group_question(sid, context)

    except Exception as e:
        logger.error(f"Critical error in send_group_question: {e}. Forcing finish_group to save MS Word Report.")
        await finish_group(sid, context)

async def group_timer(sid, context, seconds):
    try:
        await asyncio.sleep(seconds + 0.5)
        session = group_sessions.get(sid)
        if not session or not session.get("running"): return

        wait_time_before_next = 3
        await asyncio.sleep(wait_time_before_next)

        session = group_sessions.get(sid)
        if not session or not session.get("running"): return

        session["index"] += 1
        await send_group_question(sid, context)
    except asyncio.CancelledError: pass
    except Exception as e: logger.error("Timer Error: %s", e)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save, system_data
    answer = update.poll_answer
    if await is_banned(answer.user.id): return

    info = active_polls.get(answer.poll_id)
    if not info: return
    sid = info["sid"]
    session = group_sessions.get(sid)
    if not session: return

    uid = answer.user.id
    idx = info.get("index", session["index"])
    if idx >= len(session["questions"]): return
    q = session["questions"][idx]
    quiz = quizzes.get(session["quiz_id"], {})

    quiz_subject = quiz.get("subject", "Uncategorized")

    answered = session.setdefault("answered", {})
    poll_users = answered.setdefault(answer.poll_id, [])
    if uid in poll_users: return
    poll_users.append(uid)

    player = session["players"].setdefault(str(uid), {"name": answer.user.full_name, "score": 0, "correct": 0, "wrong": 0, "fast_count": 0, "answered": 0, "time_taken": 0.0})
    player["name"] = answer.user.full_name
    player["answered"] += 1

    time_spent = time.time() - session.get("question_start", time.time())
    player["time_taken"] += time_spent

    uid_str = str(uid)
    if uid_str not in users_data:
        users_data[uid_str] = {"name": answer.user.full_name, "username": "", "xp": 0, "played": 0, "streak": 0, "last_play_date": "", "correct_answers": 0, "wrong_answers": 0, "fast_answers": 0, "is_blocked": False, "topic_stats": {}, "monthly_xp": 0, "monthly_played": 0, "last_month": ""}

    users_data[uid_str]["name"] = answer.user.full_name
    topic_stats = users_data[uid_str].setdefault("topic_stats", {})
    if quiz_subject not in topic_stats: topic_stats[quiz_subject] = {"correct": 0, "wrong": 0}

    selected = answer.option_ids[0] if answer.option_ids else -1
    if selected == q["correct"]:
        player["correct"] += 1
        player["score"] += session["mark_correct"]
        topic_stats[quiz_subject]["correct"] += 1
        if time_spent <= SPEED_BONUS_TIME:
            player["fast_count"] += 1
    else:
        player["wrong"] += 1
        player["score"] += session["mark_wrong"]
        topic_stats[quiz_subject]["wrong"] += 1

    needs_save = True

async def delayed_delete_task(chat_id, msg_ids, delay_seconds, context):
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
        for msg_id in msg_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                await asyncio.sleep(0.5)
            except Exception: pass

async def send_with_retry(context, chat_id, text=None, document=None, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if text:
                await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            elif document:
                doc_msg = await context.bot.send_document(chat_id=chat_id, document=document, **kwargs)
                return doc_msg
            return True
        except NetworkError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Network error sending message (503). Retrying in 3s... ({e})")
                await asyncio.sleep(3)
            else:
                logger.error(f"Failed to send after {max_retries} attempts: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in send_with_retry: {e}")
            return False
    return False

async def finish_group(sid, context):
    global needs_save, system_data

    session = group_sessions.pop(sid, None)
    if not session or not session.get("running"):
        return

    session["running"] = False
    needs_save = True

    await force_remove_session_db(sid)

    try:
        task = session.get("timer_task")
        if task and task != asyncio.current_task(): task.cancel()
        for pid, pinfo in list(active_polls.items()):
            if pinfo.get("sid") == sid: active_polls.pop(pid, None)

        quiz = quizzes.get(session["quiz_id"])
        if not quiz:
            return

        players = session.get("players", {})
        quiz_lb = quiz.setdefault("leaderboard", [])

        now_ist = datetime.datetime.now(IST_TZ)
        today_ist = now_ist.date().isoformat()
        current_month = now_ist.strftime("%Y-%m")
        if "quiz_days" not in system_data: system_data["quiz_days"] = []
        if today_ist not in system_data["quiz_days"]:
            system_data["quiz_days"].append(today_ist)
            system_data["quiz_days"].sort()

        valid_days = system_data["quiz_days"]

        for uid, p in players.items():
            uid_str = str(uid)
            u_data = users_data.setdefault(uid_str, {"name": p["name"], "username": "", "xp": 0, "played": 0, "streak": 0, "last_play_date": "", "correct_answers": 0, "wrong_answers": 0, "fast_answers": 0, "is_blocked": False, "topic_stats": {}, "monthly_xp": 0, "monthly_played": 0, "last_month": current_month})

            if u_data.get("last_month") != current_month:
                u_data["monthly_xp"] = 0
                u_data["monthly_played"] = 0
                u_data["last_month"] = current_month

            last_play = u_data.get("last_play_date", "")
            if last_play != today_ist:
                if len(valid_days) > 1: prev_valid_day = valid_days[-2]
                else: prev_valid_day = ""
                if last_play == prev_valid_day and prev_valid_day != "": u_data["streak"] = u_data.get("streak", 0) + 1
                else: u_data["streak"] = 1
                u_data["last_play_date"] = today_ist

            u_data["xp"] += p["score"]
            u_data["played"] += 1
            u_data["monthly_xp"] += p["score"]
            u_data["monthly_played"] += 1
            u_data["correct_answers"] = u_data.get("correct_answers", 0) + p["correct"]
            u_data["wrong_answers"] = u_data.get("wrong_answers", 0) + p["wrong"]
            u_data["fast_answers"] = u_data.get("fast_answers", 0) + p.get("fast_count", 0)
            u_data["last_quiz_title"] = quiz.get("title", "Unknown Quiz")
            u_data["last_quiz_score"] = p["score"]
            u_data["last_quiz_correct"] = p["correct"]
            u_data["last_quiz_wrong"] = p["wrong"]

            existing = next((x for x in quiz_lb if str(x.get("user")) == str(uid)), None)
            if existing:
                if p["score"] > existing["score"]:
                    existing["score"] = p["score"]
                    existing["name"] = p["name"]
            else:
                quiz_lb.append({"user": int(uid), "name": p["name"], "score": p["score"]})

        quiz_lb.sort(key=lambda x: x.get("score", 0), reverse=True)
        needs_save = True

        ranking = [{"uid": uid, "name": p["name"], "score": p["score"], "correct": p.get("correct", 0), "wrong": p.get("wrong", 0), "fast": p.get("fast_count", 0), "time": p.get("time_taken", 0.0)} for uid, p in players.items()]
        ranking.sort(key=lambda x: (-x["score"], x["time"]))

        lines = [
            "ðŸ *QUIZ FINISHED!*",
            "",
            f"ðŸ“š *{escape_markdown(quiz.get('subject','Uncategorized'))}* - *{escape_markdown(quiz.get('topic','General'))}*",
            f"ðŸ‘¥ Participants: *{len(ranking)}*",
            "",
            "ðŸ† *TOP 10 LEADERBOARD*",
            ""
        ]
        for rank, p in enumerate(ranking[:10], 1):
            medal = "ðŸ¥‡" if rank == 1 else "ðŸ¥ˆ" if rank == 2 else "ðŸ¥‰" if rank == 3 else f"{rank}."
            lines.append(f"{medal} {clean_markdown_name(p['name'])} â€” *{p['score']:g} pts* | â± `{format_time(p['time'])}`")

        lines.append("")
        lines.append("ðŸ“¢ *Those who have participated in the quiz can check the complete results in the report given below.*")

        await send_with_retry(context, session["chat_id"], text="\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error during finish_group calculations: {e}")

    try:
        await create_word_report(session, quiz, ranking, context)
    except Exception as e:
        logger.error(f"Failed to call create_word_report: {e}")

    try:
        end_msg = quiz.get("end_message", "")
        if end_msg:
            await send_with_retry(context, session["chat_id"], text=end_msg, parse_mode="Markdown")

        auto_del_val = quiz.get("auto_delete", 0)
        delay_secs = int(auto_del_val) if isinstance(auto_del_val, (int, float, str)) and str(auto_del_val).isdigit() else 0
        if delay_secs > 0:
            asyncio.create_task(delayed_delete_task(session["chat_id"], session.get("sent_msgs", []), delay_secs, context))
    except Exception as e:
        logger.error(f"Error during final cleanup: {e}")

    needs_save = True

def set_cell_background(cell, hex_color):
    try:
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls
        shading_elm = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls("w"), hex_color))
        cell._tc.get_or_add_tcPr().append(shading_elm)
    except Exception: pass

def add_hyperlink(paragraph, text, url):
    try:
        from docx.opc.constants import RELATIONSHIP_TYPE
        from docx.oxml.shared import OxmlElement, qn
        part = paragraph.part
        r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), r_id)

        new_run = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        c = OxmlElement("w:color")
        c.set(qn("w:val"), "0563C1")
        rPr.append(c)
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rPr.append(u)
        new_run.append(rPr)

        text_node = OxmlElement("w:t")
        text_node.text = text
        new_run.append(text_node)
        hyperlink.append(new_run)
        paragraph._p.append(hyperlink)
    except Exception:
        paragraph.add_run(f"{text} ({url})")

def sync_create_word_report(quiz, session_questions, ranking):
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        return None

    try:
        doc = Document()

        try:
            section = doc.sections[0]
            header = section.header
            header_para = header.paragraphs[0]
            header_para.text = "Â© Horticulture Master\t\t"
            header_para.style.font.color.rgb = RGBColor(0, 100, 0)
            header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception: pass

        logo_file = next((f for f in ["1786547079689.png", "1000103378.jpg", "1000103378.png", "logo.jpg", "logo.png"] if os.path.exists(f)), None)
        stamp_file = next((f for f in ["1000103482_2.jpg", "IMG_20260813_141208.jpg", "1000103482.jpg", "IMG_20260812_202720.jpg", "1000103374.jpg", "seal.jpg", "seal.png"] if os.path.exists(f)), None)

        p_logo = doc.add_paragraph()
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if logo_file:
            try:
                r_logo = p_logo.add_run()
                r_logo.add_picture(logo_file, width=Inches(2.0))
            except Exception: pass

        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_title = p_title.add_run("HORTICULTURE MASTER\n")
        run_title.font.size = Pt(28)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(0, 100, 0)

        table_banner = doc.add_table(rows=1, cols=1)
        table_banner.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell_banner = table_banner.rows[0].cells[0]
        set_cell_background(cell_banner, "006400")

        p_banner = cell_banner.paragraphs[0]
        p_banner.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_banner = p_banner.add_run("QUIZ REPORT CARD")
        run_banner.font.size = Pt(16)
        run_banner.font.bold = True
        run_banner.font.color.rgb = RGBColor(255, 255, 255)

        doc.add_paragraph()

        meta_table = doc.add_table(rows=5, cols=4)
        meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        current_date = datetime.datetime.now(IST_TZ).strftime("%d %b %Y")
        current_time = datetime.datetime.now(IST_TZ).strftime("%I:%M %p")

        m_data = [
            ("Category", quiz.get("subject", "Uncategorized"), "Topic", quiz.get("topic", "General")),
            ("Total Questions", str(len(session_questions)), "Quiz Mode", "Live Quiz"),
            ("Timer", f"{quiz.get('timer', 30)} Seconds", "Date", current_date),
            ("Time", current_time, "Marking Correct", f"+{quiz.get('mark_correct', 4):g}"),
            ("Marking Wrong", f"{quiz.get('mark_wrong', -1):g}", "", "")
        ]

        for i, row_data in enumerate(m_data):
            row = meta_table.rows[i]
            r1 = row.cells[0].paragraphs[0].add_run(row_data[0] + " :" if row_data[0] else "")
            r1.bold = True
            r1.font.color.rgb = RGBColor(0, 0, 0)
            row.cells[1].paragraphs[0].add_run(row_data[1]).font.color.rgb = RGBColor(0, 0, 0)

            r2 = row.cells[2].paragraphs[0].add_run(row_data[2] + " :" if row_data[2] else "")
            r2.bold = True
            r2.font.color.rgb = RGBColor(0, 0, 0)
            row.cells[3].paragraphs[0].add_run(row_data[3]).font.color.rgb = RGBColor(0, 0, 0)

        doc.add_paragraph()

        table = doc.add_table(rows=1, cols=8)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Rank", "Name", "Score", "Correct", "Wrong", "Fast", "Time", "%"]

        for i, title in enumerate(headers):
            p = table.rows[0].cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(title)
            r.font.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(255, 255, 255)
            set_cell_background(table.rows[0].cells[i], "006400")

        total_questions = max(len(session_questions), 1)

        for rank, p in enumerate(ranking, 1):
            cells = table.add_row().cells
            percentage = round((p["correct"] / total_questions) * 100, 2)
            values = [str(rank), str(p["name"]), str(p["score"]), str(p["correct"]), str(p["wrong"]), str(p["fast"]), format_time(p['time']), f"{percentage}%"]

            for i, val in enumerate(values):
                para = cells[i].paragraphs[0]
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = para.add_run(val)
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0, 0, 0)
                if i == 2:
                    run.font.bold = True
                    run.font.color.rgb = RGBColor(0, 100, 0)
                if rank % 2 == 0:
                    set_cell_background(cells[i], "F5F5F5")

        doc.add_paragraph()

        footer_table = doc.add_table(rows=1, cols=3)
        footer_table.alignment = WD_TABLE_ALIGNMENT.CENTER

        cell_sum = footer_table.rows[0].cells[0]
        set_cell_background(cell_sum, "F0F5F1")
        p_sum = cell_sum.paragraphs[0]
        p_sum.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sum.add_run("SUMMARY").bold = True

        highest_score = max([p["score"] for p in ranking]) if ranking else 0
        avg_score = sum([p["score"] for p in ranking]) / len(ranking) if ranking else 0
        sum_p = cell_sum.add_paragraph(f"\nTotal Participants: {len(ranking)}\nTotal Questions: {total_questions}\nHighest Score: {highest_score}\nAverage Score: {avg_score:.2f}")
        for r in sum_p.runs: r.font.color.rgb = RGBColor(0, 0, 0)

        cell_sig = footer_table.rows[0].cells[1]
        cell_sig.vertical_alignment = 1
        p_seal = cell_sig.add_paragraph()
        p_seal.alignment = WD_ALIGN_PARAGRAPH.CENTER

        if stamp_file:
            try:
                r_stamp = p_seal.add_run()
                r_stamp.add_picture(stamp_file, width=Inches(1.5))
                p_seal.add_run("\n")
            except Exception: pass

        run_cond = p_seal.add_run("Conducted by\n")
        run_cond.font.name = 'Brush Script MT'
        run_cond.font.size = Pt(14)
        run_cond.font.color.rgb = RGBColor(0, 0, 0)
        run_team = p_seal.add_run("Horticulture Master Team")
        run_team.font.name = 'Brush Script MT'
        run_team.font.size = Pt(12)
        run_team.font.bold = True
        run_team.font.color.rgb = RGBColor(0, 100, 0)

        p_team2 = cell_sig.add_paragraph()
        p_team2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_team2 = p_team2.add_run("Official Quiz & Learning Platform")
        r_team2.font.size = Pt(8)
        r_team2.font.color.rgb = RGBColor(100, 100, 100)

        cell_note = footer_table.rows[0].cells[2]
        set_cell_background(cell_note, "F0F5F1")
        p_note = cell_note.paragraphs[0]
        p_note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_note.add_run("RULES & NOTE").bold = True
        note_p = cell_note.add_paragraph(f"\nâ€¢ Fast Answer: within 5 seconds.\nâ€¢ Marking: +{quiz.get('mark_correct', 4):g} correct, {quiz.get('mark_wrong', -1):g} wrong.\nâ€¢ Keep learning and keep growing!")
        for r in note_p.runs: r.font.color.rgb = RGBColor(0, 0, 0)

        doc.add_page_break()
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER

        if logo_file:
            try:
                r_logo2 = p2.add_run()
                r_logo2.add_picture(logo_file, width=Inches(2.0))
                p2.add_run("\n")
            except Exception: pass

        r2 = p2.add_run("JOIN OUR OFFICIAL PLATFORMS\n\n")
        r2.font.size = Pt(20)
        r2.font.bold = True
        r2.font.color.rgb = RGBColor(0, 100, 0)

        def add_link_section(title, desc, url):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(f"{title}\n")
            r.font.bold = True
            r.font.size = Pt(14)
            r.font.color.rgb = RGBColor(0, 0, 0)
            r_desc = p.add_run(f"{desc}\n")
            r_desc.font.color.rgb = RGBColor(0, 0, 0)
            add_hyperlink(p, url, url)
            p.add_run("\n")

        add_link_section("ðŸŒ Google Sites:", "Click here to visit our website", "https://sites.google.com/view/horticulture-master/home/icar-pg/previous-year-question_1")
        add_link_section("ðŸ“¢ Telegram Channel:", "Join Horticulture Master Channel", "https://t.me/akashdwivedilink")
        add_link_section("ðŸ’¬ Telegram Group:", "Join Horticulture Master Quiz Group", "https://t.me/horticulturmasterquiz")
        add_link_section("ðŸŸ¢ WhatsApp Group:", "Join our WhatsApp Community", "https://chat.whatsapp.com/KLNOleZhkCv1AzzI6nhDg0?s=cl&p=a&ilr=0&amv=1")
        add_link_section("â–¶ï¸ YouTube Channel:", "Subscribe to our YouTube Channel", "https://youtube.com/@_akash_dwivedi")

        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"Sync Docx Gen error: {e}")
        return None

async def create_word_report(session, quiz, ranking, context):
    output = await asyncio.to_thread(sync_create_word_report, quiz, session["questions"], ranking)

    if not output:
        try: await context.bot.send_message(session["chat_id"], "âš ï¸ MS Word report generate nahi ho payi. `python-docx` library install nahi hai.")
        except: pass
        return

    topic_clean = re.sub(r'\W+', '_', quiz.get("topic", "Report"))[:20]
    filename = f"HM_{topic_clean}.docx"
    output.name = filename

    await send_with_retry(
        context,
        session["chat_id"],
        document=output,
        filename=filename,
        caption=f"ðŸ“„ *Horticulture Master â€” MS Word Report*\n\nðŸ‘¥ Participants: {len(ranking)}\nðŸ† Leaderboard: Complete Result\n\nConducted By *Horticulture Master Team*",
        parse_mode="Markdown",
        read_timeout=600,
        write_timeout=600,
        connect_timeout=120
    )

def watermark_pil_image(img_bytes):
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
        txt = Image.new('RGBA', img.size, (255,255,255,0))
        draw = ImageDraw.Draw(txt)
        w, h = img.size
        text = "Â© Horticulture Master"
        draw.text((w/4, h - (h/10)), text, fill=(0, 100, 0, 180))
        out = Image.alpha_composite(img, txt).convert("RGB")
        buf = BytesIO()
        out.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception as e:
        return img_bytes

def sync_generate_word_doc(quiz, downloaded_photos):
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        try:
            section = doc.sections[0]
            header = section.header
            header_para = header.paragraphs[0]
            header_para.text = "Â© Horticulture Master\t\t"
            header_para.style.font.color.rgb = RGBColor(0, 100, 0)
            header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception: pass

        logo_file = next((f for f in ["1786547079689.png", "1000103378.jpg", "1000103378.png", "logo.jpg", "logo.png"] if os.path.exists(f)), None)
        stamp_file = next((f for f in ["1000103482_2.jpg", "IMG_20260813_141208.jpg", "1000103482.jpg", "IMG_20260812_202720.jpg", "1000103374.jpg", "seal.jpg", "seal.png"] if os.path.exists(f)), None)

        if logo_file:
            p_logo = doc.add_paragraph()
            p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_logo = p_logo.add_run()
            r_logo.add_picture(logo_file, width=Inches(2.0))

        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_title = p_title.add_run("HORTICULTURE MASTER QUIZ\n")
        run_title.font.size = Pt(24)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(0, 100, 0)

        doc.add_paragraph(f"Category: {quiz.get('subject', 'General')}\nTopic: {quiz.get('topic', 'Quiz')}")
        doc.add_paragraph(f"Total Questions: {len(quiz['questions'])}\n\n")

        for idx, q in enumerate(quiz['questions']):
            p_q = doc.add_paragraph()
            r_q = p_q.add_run(f"Q{idx + 1}. {q['question']}")
            r_q.font.bold = True

            if q.get('photo') and q['photo'] in downloaded_photos:
                try:
                    img_bytes = downloaded_photos[q['photo']]
                    wm_img_bytes = watermark_pil_image(img_bytes)
                    doc.add_picture(BytesIO(wm_img_bytes), width=Inches(3.5))
                except Exception as e:
                    logger.error(f"Failed to embed photo in DOCX: {e}")

            for opt_idx, opt in enumerate(q['options']):
                p_opt = doc.add_paragraph(f"   {chr(65 + opt_idx)}) {opt}")
                if opt_idx == q['correct']:
                    p_opt.runs[0].font.bold = True
                    p_opt.runs[0].font.color.rgb = RGBColor(0, 128, 0)

            exp = q.get('explanation', '')
            if exp and exp != "No explanation provided.":
                p_exp = doc.add_paragraph()
                r_exp = p_exp.add_run(f"Explanation: {exp}")
                r_exp.font.italic = True
                r_exp.font.color.rgb = RGBColor(100, 100, 100)
            doc.add_paragraph()

        doc.add_page_break()
        p_footer = doc.add_paragraph()
        p_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

        if stamp_file:
            r_stamp = p_footer.add_run()
            r_stamp.add_picture(stamp_file, width=Inches(1.5))
            p_footer.add_run("\n")

        r2 = p_footer.add_run("JOIN OUR OFFICIAL PLATFORMS\n\n")
        r2.font.size = Pt(16)
        r2.font.bold = True
        r2.font.color.rgb = RGBColor(0, 100, 0)

        def local_add_link(title, desc, url):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(f"{title}\n")
            r.font.bold = True
            r.font.size = Pt(12)
            p.add_run(f"{desc}\n")
            add_hyperlink(p, url, url)
            p.add_run("\n")

        local_add_link("ðŸŒ Google Sites:", "Click here to visit our website", "https://sites.google.com/view/horticulture-master/home/icar-pg/previous-year-question_1")
        local_add_link("ðŸ“¢ Telegram Channel:", "Join Horticulture Master Channel", "https://t.me/akashdwivedilink")
        local_add_link("ðŸ’¬ Telegram Group:", "Join Horticulture Master Quiz Group", "https://t.me/horticulturmasterquiz")
        local_add_link("ðŸŸ¢ WhatsApp Group:", "Join our WhatsApp Community", "https://chat.whatsapp.com/KLNOleZhkCv1AzzI6nhDg0?s=cl&p=a&ilr=0&amv=1")
        local_add_link("â–¶ï¸ YouTube Channel:", "Subscribe to our YouTube Channel", "https://youtube.com/@_akash_dwivedi")

        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"Sync Docx Gen error: {e}")
        return None

async def generate_word_doc(quiz, context, chat_id):
    if not HAS_DOCX:
        await context.bot.send_message(chat_id, "âŒ DOCX support missing.")
        return

    m_anim = await context.bot.send_message(chat_id, "â³ Generating MS Word Document with images... Please wait.")

    downloaded_photos = {}
    for q in quiz.get('questions', []):
        if q.get('photo'):
            try:
                file = await context.bot.get_file(q['photo'])
                img_bytes = await file.download_as_bytearray()
                downloaded_photos[q['photo']] = img_bytes
            except Exception as e:
                logger.error(f"Could not download photo {q['photo']} for docx: {e}")

    output = await asyncio.to_thread(sync_generate_word_doc, quiz, downloaded_photos)

    if output:
        topic_clean = re.sub(r'\W+', '_', quiz.get("topic", "Report"))[:20]
        filename = f"HM_QBank_{topic_clean}.docx"
        try: await context.bot.delete_message(chat_id=chat_id, message_id=m_anim.message_id)
        except BadRequest: pass
        except Exception: pass

        doc_msg = await send_with_retry(
            context,
            chat_id,
            document=output,
            filename=filename,
            caption=f"ðŸ“„ *Quiz Document with Embedded Photos & Watermarks*\n\nâœ… Complete Question Bank with Answers & Explanations.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ“¢ Forward to Registered Groups", callback_data=f"fw_doc|{filename}")]])
        )
    else:
        await context.bot.send_message(chat_id, "âŒ Failed to generate MS Word file.")

async def send_direct_polls_task(chat_id, quiz_id, context):
    global needs_save
    quiz = quizzes.get(quiz_id)
    if not quiz: return
    questions = prepare_quiz_for_run(quiz)

    sid = f"d_{int(time.time()*1000)}_{random.randint(100,999)}"
    group_sessions[sid] = {
        "chat_id": chat_id,
        "quiz_id": quiz_id,
        "questions": questions,
        "index": 0,
        "players": {},
        "answered": {},
        "running": True,
        "timer": 3600,
        "mark_correct": quiz.get("mark_correct", 1),
        "mark_wrong": quiz.get("mark_wrong", 0),
        "direct": True,
        "sent_msgs": []
    }
    session = group_sessions[sid]
    needs_save = True

    try:
        m = await context.bot.send_message(
            chat_id=chat_id,
            text=(f"ðŸ“š *{escape_markdown(quiz.get('subject','Uncategorized'))}* - *{escape_markdown(quiz.get('topic','General'))}*\n\nðŸ“Š Marking: *+{quiz.get('mark_correct', 1):g} / {quiz.get('mark_wrong', 0):g}*\n\nðŸ‘‡ Quiz Started\nComplete all questions."),
            parse_mode="Markdown"
        )
        session["sent_msgs"].append(m.message_id)
    except Exception: return

    for idx, q in enumerate(questions):
        if not session["running"]: break

        poll_question = f"Q{idx + 1}/{len(questions)}: {q['question']}"
        needs_separate_msg = q.get("photo") or len(poll_question) > 280 or '\n' in q['question']

        if needs_separate_msg:
            if q.get("photo"):
                try:
                    m1 = await context.bot.send_photo(chat_id, q["photo"], caption=f"ðŸ“ *Q{idx+1}/{len(questions)}*\n\n{escape_markdown(q['question'])[:1000]}", parse_mode="Markdown")
                    session["sent_msgs"].append(m1.message_id)
                except Exception: pass
            else:
                m1 = await context.bot.send_message(chat_id, f"ðŸ“ *Q{idx+1}/{len(questions)}*\n\n{escape_markdown(q['question'])}", parse_mode="Markdown")
                session["sent_msgs"].append(m1.message_id)
            poll_question = f"Q{idx + 1}/{len(questions)}: Select correct option."
        else:
            pass

        try:
            poll = await context.bot.send_poll(
                chat_id=chat_id,
                question=poll_question,
                options=[str(x)[:100] for x in q["options"]],
                type="quiz",
                correct_option_id=q["correct"],
                explanation=q.get("explanation", "Correct Answer!")[:200],
                is_anonymous=False
            )
            active_polls[poll.poll.id] = {"sid": sid, "index": idx}
            session["sent_msgs"].append(poll.message_id)
            needs_save = True
        except Exception: pass
        await asyncio.sleep(2)

    await asyncio.sleep(5)
    auto_del_val = int(quiz.get("auto_delete", 0))
    delay_secs = auto_del_val if isinstance(auto_del_val, (int, float, str)) and str(auto_del_val).isdigit() else 0
    if delay_secs > 0:
        asyncio.create_task(delayed_delete_task(chat_id, session.get("sent_msgs", []), delay_secs, context))
    group_sessions.pop(sid, None)
    needs_save = True

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0, filter_cat: str = None):
    uid = update.effective_user.id
    is_admin = uid == ADMIN_ID

    if filter_cat:
        mine = [(qid, q) for qid, q in quizzes.items() if (str(q.get("owner")) == str(uid) or is_admin) and q.get("subject", "Uncategorized")[:40] == filter_cat]
        title_text = f"ðŸ“‚ Category: {escape_markdown(filter_cat)}"
    else:
        mine = [(qid, q) for qid, q in quizzes.items() if str(q.get("owner")) == str(uid) or is_admin]
        title_text = "ðŸ“š MY QUIZZES (ALL)"

    target = update.callback_query.message if update.callback_query else update.effective_message

    if not mine:
        text = f"{title_text}\n\nâŒ No quizzes found here."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Main Menu", callback_data="mainmenu")]])
        if update.callback_query: await target.edit_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            msg = await target.reply_text(text, parse_mode="Markdown", reply_markup=markup)
            track_msg(uid, msg.message_id)
        return

    mine.reverse()
    total_pages = max(1, (len(mine) + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = mine[page * HISTORY_PAGE_SIZE:(page + 1) * HISTORY_PAGE_SIZE]

    buttons = [[InlineKeyboardButton(f"ðŸ“š {escape_markdown(q.get('subject','Uncategorized'))} - {escape_markdown(q.get('topic','General'))}"[:40], callback_data=f"quizview|{qid}")] for qid, q in chunk]

    nav = []
    if page > 0:
        nav_data = f"catpage|{page-1}|{filter_cat}" if filter_cat else f"histpage|{page-1}"
        nav.append(InlineKeyboardButton("â¬…ï¸ Prev", callback_data=nav_data))
    if page < total_pages - 1:
        nav_data = f"catpage|{page+1}|{filter_cat}" if filter_cat else f"histpage|{page+1}"
        nav.append(InlineKeyboardButton("âž¡ï¸ Next", callback_data=nav_data))
    if nav: buttons.append(nav)
    if filter_cat: buttons.append([InlineKeyboardButton("ðŸ”™ Categories", callback_data="categories")])
    buttons.append([InlineKeyboardButton("ðŸ”™ Main Menu", callback_data="mainmenu")])

    text = f"{title_text} â€” Page {page+1}/{total_pages}\n\nðŸ‘‡ Select a quiz. Its options will open in this same message."
    markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        try: await target.edit_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            msg = await target.reply_text(text, parse_mode="Markdown", reply_markup=markup)
            track_msg(uid, msg.message_id)
    else:
        msg = await target.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        track_msg(uid, msg.message_id)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_admin = uid == ADMIN_ID
    target = update.callback_query.message if update.callback_query else update.effective_message

    cats = set()
    for q in quizzes.values():
        if str(q.get("owner")) == str(uid) or is_admin: cats.add(q.get("subject", "Uncategorized")[:40])

    cats = sorted(list(cats))
    if not cats:
        text = "ðŸ“‚ *BROWSE BY CATEGORY*\n\nâŒ You haven't created any quizzes yet."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Main Menu", callback_data="mainmenu")]])
        await target.edit_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    buttons = [[InlineKeyboardButton(f"ðŸ“ {cat}", callback_data=f"catview|{cat}")] for cat in cats]
    buttons.append([InlineKeyboardButton("ðŸ”™ Main Menu", callback_data="mainmenu")])

    text = "ðŸ“‚ *BROWSE BY CATEGORY*\n\nðŸ‘‡ Select a Subject/Category to view its quizzes:"
    await target.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global needs_save, system_data
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if await is_banned(uid): return
    data = query.data or ""

    if data == "mainmenu":
        await query.edit_message_text("ðŸŒ± *Horticulture Master Quiz Bot v25.0 ULTRA PRO*\n\nðŸ‘‡ Select an option:", parse_mode="Markdown", reply_markup=main_menu())
        return

    if data == "cancel":
        await query.edit_message_text("âŒ Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Main Menu", callback_data="mainmenu")]]))
        return

    if data == "clearchat_main":
        await clear_chat_action(uid, query.message.chat_id, context)
        msg = await context.bot.send_message(
            query.message.chat_id,
            "ðŸŒ± Horticulture Master Quiz Bot v25.0 ULTRA PRO\n\nâœ… Auto-Scheduler Engine\nâœ… MS Word Downloads\nâœ… Forward Messages To Groups!\n\nðŸ‘‡ Select an option:",
            parse_mode="Markdown", reply_markup=main_menu()
        )
        track_msg(uid, msg.message_id)
        return

    # ðŸ“¢ BROADCAST TO GROUPS SETUP
    if data == "broadcast_setup":
        if uid != ADMIN_ID: return
        creation[uid] = {"mode": "wait_broadcast"}
        await query.edit_message_text(
            "ðŸ“¢ *Broadcast Mode*\n\nPlease send any message, text, photo, or poll here.\nAfter you send it, you'll get a button to forward it to all registered groups.",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data="mainmenu")]])
        )
        return

    # ðŸ“¢ EXECUTE BROADCAST
    if data.startswith("fw_bcast|"):
        if uid != ADMIN_ID: return
        msg_id = int(data.split("|")[1])
        sent = 0
        failed = 0
        for gid in saved_groups:
            try:
                await context.bot.copy_message(chat_id=gid, from_chat_id=query.message.chat_id, message_id=msg_id)
                sent += 1
                await asyncio.sleep(0.5)
            except Exception:
                failed += 1
        await query.edit_message_text(f"âœ… **Broadcast Complete!**\n\nðŸ“¤ Sent to: {sent} groups\nâŒ Failed: {failed} groups", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Back to Main Menu", callback_data="mainmenu")]]))
        return

    # ðŸ“¢ FORWARD DOC TO GROUPS
    if data.startswith("fw_doc|"):
        if uid != ADMIN_ID: return
        sent = 0
        for gid in saved_groups:
            try:
                await context.bot.copy_message(chat_id=gid, from_chat_id=query.message.chat_id, message_id=query.message.message_id)
                sent += 1
                await asyncio.sleep(0.5)
            except Exception: pass
        await query.answer(f"âœ… Document shared with {sent} groups!", show_alert=True)
        return

    if data == "autoschedule_start":
        buttons = [[InlineKeyboardButton(f"ðŸ“¢ {info.get('title', gid)[:20]}", callback_data=f"autosched_g|{gid}")] for gid, info in saved_groups.items() if uid == ADMIN_ID or info.get("registered_by") == uid]
        buttons.append([InlineKeyboardButton("ðŸ”™ Back", callback_data="mainmenu")])
        if len(buttons) == 1: await query.edit_message_text("âŒ No registered groups found. Register a group first with /register")
        else: await query.edit_message_text("ðŸ“… *Auto-Scheduler Engine*\n\nFirst, select which group to schedule the automatic quiz in:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("autosched_g|"):
        gid = data.split("|")[1]
        group = saved_groups.get(gid)
        if not group: return

        cats = set()
        for q in quizzes.values():
            if str(q.get("owner")) == str(uid) or uid == ADMIN_ID: cats.add(q.get("subject", "Uncategorized")[:40])

        buttons = [[InlineKeyboardButton("ðŸŽ² Pure Random (All Quizzes)", callback_data=f"autosched_c|{gid}|Random")]]
        for cat in sorted(list(cats)):
            buttons.append([InlineKeyboardButton(f"ðŸ“ {cat}", callback_data=f"autosched_c|{gid}|{cat}")])
        buttons.append([InlineKeyboardButton("ðŸ”™ Cancel", callback_data="mainmenu")])

        await query.edit_message_text(f"ðŸ“… *Selected Group: {group.get('title')}*\n\nSelect the source category for the scheduled questions:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("autosched_c|"):
        _, gid, cat = data.split("|", 2)
        group = saved_groups.get(gid)
        creation[uid] = {"mode": "wait_auto_count", "auto_gid": gid, "auto_gname": group.get("title"), "auto_cat": cat}
        await query.edit_message_text(f"ðŸ“… *Category: {cat}*\n\nPlease reply with the *number of questions* you want in this scheduled quiz (e.g., 10, 20, 50, 100).", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data="mainmenu")]]))
        return

    if data == "newquiz":
        creation[uid] = {"mode": "wait_subject", "start_time": time.time(), "subject": "", "topic": "", "questions": [], "timer": 30, "mark_correct": 4, "mark_wrong": -1, "shuffle": "none", "quiz_mode": "live", "auto_delete": 0, "chat_msgs": []}
        m = await context.bot.send_message(query.message.chat_id, "ðŸ“ *Please send the Category/Subject:* (e.g., Vegetable Science)", parse_mode="Markdown")
        creation[uid]["chat_msgs"].append(m.message_id)
        track_msg(uid, m.message_id)
        return

    if data == "myquizzes":
        await show_history(update, context)
        return

    if data == "categories":
        await show_categories(update, context)
        return

    if data.startswith("catview|"):
        cat_name = data.split("|", 1)[1]
        await show_history(update, context, page=0, filter_cat=cat_name)
        return

    if data.startswith("catpage|"):
        parts = data.split("|", 2)
        try: page = int(parts[1])
        except Exception: page = 0
        cat_name = parts[2] if len(parts) > 2 else None
        await show_history(update, context, page=page, filter_cat=cat_name)
        return

    if data == "show_rank":
        await rank_cmd(update, context)
        return

    if data.startswith("histpage|"):
        try: page = int(data.split("|", 1)[1])
        except Exception: page = 0
        await show_history(update, context, page)
        return

    if data == "groups":
        visible = {gid: info for gid, info in saved_groups.items() if uid == ADMIN_ID or info.get("registered_by") == uid}
        text = "ðŸ‘¥ *REGISTERED GROUPS*\n\n"
        if visible:
            for i, (gid, info) in enumerate(visible.items(), 1): text += f"{i}. {escape_markdown(info.get('title', gid))}\n"
        else: text += "âŒ No registered groups found."
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Main Menu", callback_data="mainmenu")]]))
        return

    if data == "addmore":
        st = creation.get(uid)
        if st:
            st["mode"] = "questions"
            m = await context.bot.send_message(query.message.chat_id, "âš¡ *Send the questions (Or upload PDF/DOCX/TXT file/Photo).* \n\n*Note for Matching Questions:* Make sure to write the word 'Options:' right above your choices so they don't break!", parse_mode="Markdown", reply_markup=question_menu())
            st.setdefault("chat_msgs", []).append(m.message_id)
            track_msg(uid, m.message_id)
        return

    if data == "editlast":
        st = creation.get(uid)
        if not st or not st["questions"]:
            await query.answer("âŒ No questions found.", show_alert=True)
            return
        st["mode"] = "edit"
        m = await context.bot.send_message(query.message.chat_id, "âœï¸ *Send the corrected version of the last question.*", parse_mode="Markdown")
        st.setdefault("chat_msgs", []).append(m.message_id)
        track_msg(uid, m.message_id)
        return

    if data == "undolast":
        st = creation.get(uid)
        if st and st["questions"]:
            st["questions"].pop()
            await query.edit_message_text(f"â†©ï¸ Last question removed.\n\nTotal: {len(st['questions'])}", reply_markup=question_menu())
        return

    if data == "clearchat_qs":
        st = creation.get(uid)
        if st and "chat_msgs" in st:
            for mid in st["chat_msgs"]:
                try: await context.bot.delete_message(chat_id=query.message.chat_id, message_id=mid)
                except BadRequest: pass
                except Exception: pass
            st["chat_msgs"] = []
            await query.answer("ðŸ§¹ Chat space cleared! Your questions are saved inside the bot.", show_alert=True)
            m = await context.bot.send_message(query.message.chat_id, f"ðŸ§¹ Chat view cleared.\n\nðŸ“š Total saved: {len(st.get('questions', []))}", reply_markup=question_menu())
            st["chat_msgs"].append(m.message_id)
            track_msg(uid, m.message_id)
        return

    if data == "clearall":
        await query.edit_message_text(
            "âš ï¸ *Are you sure you want to completely clear all added questions?*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("âœ… OK (Clear)", callback_data="confirm_clearall"), InlineKeyboardButton("âŒ Cancel", callback_data="cancel_clearall")]
            ])
        )
        return

    if data == "confirm_clearall":
        st = creation.get(uid)
        if st:
            st["questions"] = []
            await query.edit_message_text("ðŸ—‘ï¸ï¸ All questions have been cleared.", reply_markup=question_menu())
        return

    if data == "cancel_clearall":
        st = creation.get(uid)
        if st:
            await query.edit_message_text(f"âœ… Cancelled. Your questions are safe.\n\nðŸ“š Total Questions: {len(st.get('questions', []))}", reply_markup=question_menu())
        return

    if data == "done":
        st = creation.get(uid)
        if not st or not st["questions"]:
            await query.answer("âŒ At least 1 question is required.", show_alert=True)
            return
        await query.edit_message_text("â±ï¸ *Select Timer:*", parse_mode="Markdown", reply_markup=timer_menu())
        return

    if data == "timer_custom":
        st = creation.get(uid)
        if not st: return
        st["mode"] = "wait_custom_timer"
        await query.edit_message_text("âœï¸ *Send the custom timer in seconds* (e.g., `15`, `90`):", parse_mode="Markdown")
        return

    if data.startswith("timer_"):
        st = creation.get(uid)
        if not st: return
        try: st["timer"] = int(data.split("_")[1])
        except Exception: st["timer"] = 30
        await query.edit_message_text(f"â±ï¸ Timer: *{st['timer']} seconds*\n\nðŸ“Š Select marking scheme:", parse_mode="Markdown", reply_markup=marking_menu())
        return

    if data.startswith("mark_"):
        st = creation.get(uid)
        if not st: return
        parts = data.split("_")
        st["mark_correct"] = float(parts[1])
        st["mark_wrong"] = float(parts[2])
        await query.edit_message_text(f"âœ… Marking: +{st['mark_correct']:g} / {st['mark_wrong']:g}\n\nðŸ”€ Select Shuffle Mode:", reply_markup=shuffle_menu())
        return

    if data.startswith("shuffle_"):
        st = creation.get(uid)
        if not st: return
        st["shuffle"] = data.replace("shuffle_", "")
        await query.edit_message_text("ðŸ”€ Shuffle selected.\n\nSelect Quiz Mode:", reply_markup=mode_menu())
        return

    if data.startswith("mode_"):
        st = creation.get(uid)
        if not st: return
        st["quiz_mode"] = data.replace("mode_", "")
        await query.edit_message_text("ðŸ—‘ï¸ *Auto-Delete feature:*\n\nShould the bot automatically delete the quiz polls after the quiz finishes? (Only Leaderboard will remain)", parse_mode="Markdown", reply_markup=autodel_menu())
        return

    if data.startswith("autodel_"):
        st = creation.get(uid)
        if not st: return
        st["auto_delete"] = int(data.replace("autodel_", ""))
        st["mode"] = "wait_schedule"
        await query.edit_message_text(
            "ðŸ•¤ *Scheduled Start Option:*\n\nIf you want this quiz to automatically start at a specific time, send the time now (e.g., `09:30 PM` or `21:30`).\n\nOtherwise, click 'Skip'.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("âŒ Skip / Manual Start", callback_data="skip_schedule")]])
        )
        return

    if data == "skip_schedule":
        st = creation.get(uid)
        if not st: return
        st["schedule_time"] = "Off"
        st["mode"] = "wait_end_msg"
        await query.edit_message_text(
            "ðŸ“ *Final Text Message Option:*\n\nSend a message you want to be delivered at the very end of the quiz (after the Word Report). Example: 'Join our Telegram for more!'\n\nOtherwise, click 'Skip'.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("âŒ Skip", callback_data="skip_end_msg")]])
        )
        return

    if data == "skip_end_msg":
        st = creation.get(uid)
        if not st: return
        st["end_message"] = ""
        await finalize_quiz(uid, context, query.message)
        return

    if data.startswith("ready|"):
        sid = data.split("|",1)[1]
        session = group_sessions.get(sid)
        if not session or session.get("state") != "lobby": return
        if uid not in session["ready_users"]: session["ready_users"].append(uid)
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"âœ… I'M READY â€” {len(session['ready_users'])}", callback_data=f"ready|{sid}")],
            [InlineKeyboardButton("ðŸš€ START QUIZ (ADMIN)", callback_data=f"startquiz|{sid}")]
        ])
        try: await query.edit_message_reply_markup(reply_markup=markup)
        except Exception: pass
        return

    if data.startswith("startquiz|"):
        sid = data.split("|",1)[1]
        session = group_sessions.get(sid)
        if not session or session.get("state") != "lobby": return
        if uid != session["owner"] and uid != ADMIN_ID: return
        await start_quiz_from_lobby(sid, context, query.message)
        return

    if data.startswith("sendgroup|"):
        parts = data.split("|")
        if len(parts) != 3: return
        quiz_id, gid = parts[1], parts[2]
        quiz, group = quizzes.get(quiz_id), saved_groups.get(gid)

        if not quiz or not group:
            await query.edit_message_text("âŒ Quiz or group not found.")
            return
        if uid != ADMIN_ID and group.get("registered_by") != uid:
            await query.edit_message_text("âŒ You are not authorized.")
            return

        chat_id = int(gid)
        if quiz.get("mode") == "direct":
            asyncio.create_task(send_direct_polls_task(chat_id, quiz_id, context))
            await query.edit_message_text(f"ðŸš€ *Direct quiz started in:*\nðŸ“¢ {escape_markdown(group.get('title', gid))}", parse_mode="Markdown")
            return

        sid = f"s_{int(time.time()*1000)}_{random.randint(100,999)}"
        group_sessions[sid] = {
            "chat_id": chat_id,
            "quiz_id": quiz_id,
            "questions": prepare_quiz_for_run(quiz),
            "index": 0,
            "players": {},
            "answered": {},
            "running": False,
            "state": "lobby",
            "ready_users": [],
            "owner": uid,
            "timer": quiz.get("timer",30),
            "mark_correct": quiz.get("mark_correct",4),
            "mark_wrong": quiz.get("mark_wrong",-1),
            "question_start": 0
        }
        needs_save = True

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("âœ… I'M READY â€” 0", callback_data=f"ready|{sid}")],
            [InlineKeyboardButton("ðŸš€ START QUIZ (ADMIN)", callback_data=f"startquiz|{sid}")]
        ])
        try:
            msg = await context.bot.send_message(chat_id, get_lobby_text(quiz,0), parse_mode="Markdown", reply_markup=markup)
            group_sessions[sid]["lobby_msg_id"] = msg.message_id
        except Exception as e:
            logger.error("Group send error: %s", e)
            group_sessions.pop(sid,None)
            await query.edit_message_text("âŒ Bot cannot send messages to this group. Check admin permission.")
            return

        await query.edit_message_text(f"ðŸš€ *Lobby Created!*\n\nðŸ“¢ {escape_markdown(group.get('title',gid))}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Quiz", callback_data=f"quizview|{quiz_id}")]]))
        return

    if data.startswith("quizview|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if not quiz:
            await query.edit_message_text("âŒ Quiz not found.")
            return
        if uid != ADMIN_ID and str(quiz.get("owner")) != str(uid):
            await query.edit_message_text("âŒ This quiz doesn't belong to you.")
            return

        buttons = [
            [InlineKeyboardButton("ðŸ“¢ Share Quiz", callback_data=f"share|{quiz_id}")],
            [InlineKeyboardButton("âš™ï¸ Edit Settings & Qs", callback_data=f"editquiz|{quiz_id}")],
            [InlineKeyboardButton("ðŸ—‘ï¸ Delete Quiz", callback_data=f"delquiz|{quiz_id}")],
            [InlineKeyboardButton("ðŸ”™ Back to My Quizzes", callback_data="myquizzes")]
        ]

        del_val = int(quiz.get("auto_delete", 0))
        del_str = "OFF" if del_val == 0 else f"{del_val//60} mins"

        text = (f"ðŸ“š Category: *{escape_markdown(quiz.get('subject','Uncategorized'))}*\n"
                f"ðŸ“Œ Topic: *{escape_markdown(quiz.get('topic','General'))}*\n\n"
                f"ðŸ“ Total Questions: {len(quiz['questions'])}\n"
                f"â±ï¸ Timer: {quiz.get('timer',30)} sec\n"
                f"ðŸ“Š Marking: *+{quiz.get('mark_correct',4):g} / {quiz.get('mark_wrong',-1):g}*\n"
                f"ðŸ”€ Shuffle: {quiz.get('shuffle','none')}\n"
                f"ðŸ”„ Mode: {quiz.get('mode', 'live').title()}\n"
                f"ðŸ•¤ Schedule: {quiz.get('schedule_time', 'Off')}\n"
                f"ðŸ—‘ï¸ Auto-Delete: {del_str}\n\n"
                f"ðŸ‘‡ *Options are opened in this same message.*")
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("editquiz|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if not quiz or (uid != ADMIN_ID and str(quiz.get("owner")) != str(uid)):
            await query.answer("âŒ Access Denied.", show_alert=True)
            return

        buttons = [
            [InlineKeyboardButton("âž• Add Qs", callback_data=f"q_add|{quiz_id}"), InlineKeyboardButton("ðŸŽ² Random Qs", callback_data=f"eq_auto_rand|{quiz_id}")],
            [InlineKeyboardButton("ðŸ—‘ï¸ Delete Qs (Bulk)", callback_data=f"q_bulk|{quiz_id}"), InlineKeyboardButton("âœï¸ Specific Q", callback_data=f"eq_spec_q|{quiz_id}")],
            [InlineKeyboardButton("âœï¸ Category", callback_data=f"eq_menu_sub|{quiz_id}"), InlineKeyboardButton("âœï¸ Topic", callback_data=f"eq_menu_top|{quiz_id}")],
            [InlineKeyboardButton("â±ï¸ Timer", callback_data=f"eq_menu_timer|{quiz_id}"), InlineKeyboardButton("ðŸ“Š Marking", callback_data=f"eq_menu_mark|{quiz_id}")],
            [InlineKeyboardButton("ðŸ”€ Shuffle", callback_data=f"eq_menu_shuf|{quiz_id}"), InlineKeyboardButton("ðŸ”„ Mode", callback_data=f"eq_menu_mode|{quiz_id}")],
            [InlineKeyboardButton("ðŸ•¤ Schedule Time", callback_data=f"eq_menu_sch|{quiz_id}"), InlineKeyboardButton("ðŸ—‘ï¸ Auto-Delete", callback_data=f"eq_menu_autodel|{quiz_id}")],
            [InlineKeyboardButton("ðŸ End Message", callback_data=f"eq_menu_end|{quiz_id}")],
            [InlineKeyboardButton("ðŸ“„ MS Word Report", callback_data=f"eq_dl_word|{quiz_id}")],
            [InlineKeyboardButton("ðŸ”™ Back to Quiz", callback_data=f"quizview|{quiz_id}")]
        ]

        auto_del_val_edit = int(quiz.get('auto_delete', 0))
        auto_del_str_edit = 'OFF' if auto_del_val_edit == 0 else f"{auto_del_val_edit//60} mins"

        await query.edit_message_text(
            f"âš™ï¸ *Edit Quiz Settings & Questions*\n\n"
            f"ðŸ“– Category: *{escape_markdown(quiz.get('subject','Uncategorized'))}*\n"
            f"ðŸ“Œ Topic: *{escape_markdown(quiz.get('topic','General'))}*\n\n"
            f"ðŸ“ Total Qs: {len(quiz['questions'])}\n"
            f"â±ï¸ Timer: {quiz.get('timer', 30)}s\n"
            f"ðŸ“Š Marking: +{quiz.get('mark_correct', 4):g} / {quiz.get('mark_wrong', -1):g}\n"
            f"ðŸ”€ Shuffle: {quiz.get('shuffle', 'none')}\n"
            f"ðŸ”„ Mode: {quiz.get('mode', 'live').title()}\n"
            f"ðŸ•¤ Schedule: {quiz.get('schedule_time', 'Off')}\n"
            f"ðŸ—‘ï¸ Auto-Delete: {auto_del_str_edit}\n\n"
            "ðŸ‘‡ Choose what you want to edit or download:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("eq_auto_rand|"):
        quiz_id = data.split("|", 1)[1]
        buttons = [
            [InlineKeyboardButton("ðŸ”„ Reset & Replace All", callback_data=f"eq_ar_mode|{quiz_id}|replace")],
            [InlineKeyboardButton("âž• Append to Existing", callback_data=f"eq_ar_mode|{quiz_id}|append")],
            [InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]
        ]
        await query.edit_message_text(
            "ðŸŽ² *Add Questions Randomly*\n\nDo you want to clear the current questions and start fresh, or add the random questions to the existing ones?",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("eq_ar_mode|"):
        _, quiz_id, rand_mode = data.split("|")
        creation[uid] = {"mode": "wait_auto_rand_count", "qid": quiz_id, "rand_mode": rand_mode}
        await query.edit_message_text(
            "ðŸŽ² *Add Questions Randomly*\n\nPlease reply with the *number* of random questions you want to pull from the database (e.g., `10`, `50`).",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]])
        )
        return

    if data.startswith("eq_dl_word|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if quiz: asyncio.create_task(generate_word_doc(quiz, context, query.message.chat_id))
        return

    if data.startswith("eq_menu_timer|"):
        quiz_id = data.split("|",1)[1]
        buttons = [
            [InlineKeyboardButton("20 sec", callback_data=f"eq_val_timer|{quiz_id}|20"), InlineKeyboardButton("30 sec", callback_data=f"eq_val_timer|{quiz_id}|30")],
            [InlineKeyboardButton("40 sec", callback_data=f"eq_val_timer|{quiz_id}|40"), InlineKeyboardButton("45 sec", callback_data=f"eq_val_timer|{quiz_id}|45")],
            [InlineKeyboardButton("60 sec", callback_data=f"eq_val_timer|{quiz_id}|60"), InlineKeyboardButton("âœï¸ Custom", callback_data=f"eq_val_timer|{quiz_id}|custom")],
            [InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]
        ]
        await query.edit_message_text("â±ï¸ *Select New Default Timer:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("eq_menu_mark|"):
        quiz_id = data.split("|",1)[1]
        buttons = [
            [InlineKeyboardButton("âž•4 / âž–1", callback_data=f"eq_val_mark|{quiz_id}|4|-1")],
            [InlineKeyboardButton("âž•1 / âž–0.25", callback_data=f"eq_val_mark|{quiz_id}|1|-0.25")],
            [InlineKeyboardButton("âž•1 / 0", callback_data=f"eq_val_mark|{quiz_id}|1|0")],
            [InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]
        ]
        await query.edit_message_text("ðŸ“Š *Select New Marking Scheme:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("eq_menu_shuf|"):
        quiz_id = data.split("|",1)[1]
        buttons = [
            [InlineKeyboardButton("âŒ No Shuffle", callback_data=f"eq_val_shuf|{quiz_id}|none")],
            [InlineKeyboardButton("ðŸ”€ Questions", callback_data=f"eq_val_shuf|{quiz_id}|questions")],
            [InlineKeyboardButton("ðŸ”€ Answers", callback_data=f"eq_val_shuf|{quiz_id}|answers")],
            [InlineKeyboardButton("ðŸ”€ All", callback_data=f"eq_val_shuf|{quiz_id}|all")],
            [InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]
        ]
        await query.edit_message_text("ðŸ”€ *Select New Shuffle Mode:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("eq_menu_mode|"):
        quiz_id = data.split("|",1)[1]
        buttons = [
            [InlineKeyboardButton("ðŸ† Live Quiz", callback_data=f"eq_val_mode|{quiz_id}|live")],
            [InlineKeyboardButton("ðŸ“ Direct Polls", callback_data=f"eq_val_mode|{quiz_id}|direct")],
            [InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]
        ]
        await query.edit_message_text("ðŸ”„ *Select New Quiz Mode:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("eq_menu_autodel|"):
        quiz_id = data.split("|",1)[1]
        buttons = [
            [InlineKeyboardButton("1 min", callback_data=f"eq_val_autodel|{quiz_id}|60")],
            [InlineKeyboardButton("5 min", callback_data=f"eq_val_autodel|{quiz_id}|300")],
            [InlineKeyboardButton("15 min", callback_data=f"eq_val_autodel|{quiz_id}|900")],
            [InlineKeyboardButton("30 min", callback_data=f"eq_val_autodel|{quiz_id}|1800")],
            [InlineKeyboardButton("50 min", callback_data=f"eq_val_autodel|{quiz_id}|3000")],
            [InlineKeyboardButton("120 min", callback_data=f"eq_val_autodel|{quiz_id}|7200")],
            [InlineKeyboardButton("âŒ OFF", callback_data=f"eq_val_autodel|{quiz_id}|0")],
            [InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]
        ]
        await query.edit_message_text("ðŸ—‘ï¸ *Select New Auto-Delete Time:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("eq_menu_sub|"):
        quiz_id = data.split("|",1)[1]
        creation[uid] = {"mode": "eq_spec_sub", "qid": quiz_id}
        await query.edit_message_text("ðŸ“ Send the new *Category (Subject)* for this quiz:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("eq_menu_top|"):
        quiz_id = data.split("|",1)[1]
        creation[uid] = {"mode": "eq_spec_top", "qid": quiz_id}
        await query.edit_message_text("ðŸ“Œ Send the new *Topic* for this quiz:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("eq_menu_sch|"):
        quiz_id = data.split("|",1)[1]
        creation[uid] = {"mode": "eq_spec_sch", "qid": quiz_id}
        await query.edit_message_text("ðŸ•¤ Send the new *Scheduled Time* (e.g. `25/08/2026 09:30 PM` or just `09:30 PM`) or type `Off` to disable:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("eq_menu_end|"):
        quiz_id = data.split("|",1)[1]
        creation[uid] = {"mode": "eq_spec_end", "qid": quiz_id}
        await query.edit_message_text("ðŸ Send the new *End Message* to be sent after the quiz (or type `Skip` to disable):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("eq_val_timer|"):
        _, quiz_id, val = data.split("|")
        if val == "custom":
            creation[uid] = {"mode": "eq_wait_custom_timer", "qid": quiz_id}
            await query.edit_message_text("âœï¸ *Send the custom timer in seconds* (e.g., `15`, `90`):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
            return
        if quiz_id in quizzes: quizzes[quiz_id]["timer"] = int(val); needs_save = True
        await query.answer("âœ… Timer Updated!", show_alert=False)
        query.data = f"editquiz|{quiz_id}"
        await callback_handler(update, context)
        return

    if data.startswith("eq_val_mark|"):
        _, quiz_id, c, w = data.split("|")
        if quiz_id in quizzes: quizzes[quiz_id]["mark_correct"] = float(c); quizzes[quiz_id]["mark_wrong"] = float(w); needs_save = True
        await query.answer("âœ… Marking Updated!", show_alert=False)
        query.data = f"editquiz|{quiz_id}"
        await callback_handler(update, context)
        return

    if data.startswith("eq_val_shuf|"):
        _, quiz_id, val = data.split("|")
        if quiz_id in quizzes: quizzes[quiz_id]["shuffle"] = val; needs_save = True
        await query.answer("âœ… Shuffle Mode Updated!", show_alert=False)
        query.data = f"editquiz|{quiz_id}"
        await callback_handler(update, context)
        return

    if data.startswith("eq_val_mode|"):
        _, quiz_id, val = data.split("|")
        if quiz_id in quizzes: quizzes[quiz_id]["mode"] = val; needs_save = True
        await query.answer("âœ… Mode Updated!", show_alert=False)
        query.data = f"editquiz|{quiz_id}"
        await callback_handler(update, context)
        return

    if data.startswith("eq_val_autodel|"):
        _, quiz_id, val = data.split("|")
        if quiz_id in quizzes: quizzes[quiz_id]["auto_delete"] = int(val); needs_save = True
        await query.answer("âœ… Auto-Delete Updated!", show_alert=False)
        query.data = f"editquiz|{quiz_id}"
        await callback_handler(update, context)
        return

    if data.startswith("eq_spec_q|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if not quiz: return
        creation[uid] = {"mode": "wait_eq_num", "qid": quiz_id}
        await query.edit_message_text("âœï¸ *Edit Specific Question*\n\n" f"This quiz has {len(quiz['questions'])} questions.\n" "ðŸ‘‰ Send the *Question Number* you want to edit (e.g., `5`).", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("q_bulk|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if not quiz or (uid != ADMIN_ID and str(quiz.get("owner")) != str(uid)): return
        creation[uid] = {"mode":"bulk_rem_q", "qid":quiz_id}
        await query.edit_message_text("ðŸ—‘ï¸ *Bulk Delete Questions*\n\nPlease send the question numbers you want to delete, separated by commas or dashes.\n\nðŸ‘‰ *Example:* `1, 4, 5`\nðŸ‘‰ *Example:* `2-6`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("q_add|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if not quiz or (uid != ADMIN_ID and str(quiz.get("owner")) != str(uid)): return
        creation[uid] = {"mode":"append_q", "qid":quiz_id}
        await query.edit_message_text("âš¡ *Send the questions (Or upload PDF/DOCX/TXT file).*\n\nThey will be saved to this quiz.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ Cancel", callback_data=f"editquiz|{quiz_id}")]]))
        return

    if data.startswith("delquiz|"):
        quiz_id = data.split("|",1)[1]
        await query.edit_message_text("âš ï¸ *ARE YOU SURE?*\n\nDo you really want to permanently delete this quiz?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("âœ… Yes, Delete", callback_data=f"confirmdel|{quiz_id}")],[InlineKeyboardButton("âŒ Cancel", callback_data=f"quizview|{quiz_id}")]]))
        return

    if data.startswith("confirmdel|"):
        quiz_id = data.split("|",1)[1]
        quiz = quizzes.get(quiz_id)
        if not quiz or (uid != ADMIN_ID and str(quiz.get("owner")) != str(uid)): return
        quizzes.pop(quiz_id,None)
        needs_save=True
        await query.edit_message_text("ðŸ—‘ï¸ *Quiz Deleted Successfully.*",parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ”™ My Quizzes",callback_data="myquizzes")]]))
        return

    if data.startswith("share|"):
        quiz_id=data.split("|",1)[1]
        buttons = [[InlineKeyboardButton(f"ðŸ“¢ Share in {info.get('title', gid)[:20]}", callback_data=f"sendgroup|{quiz_id}|{gid}")] for gid, info in saved_groups.items() if uid == ADMIN_ID or info.get("registered_by") == uid]
        buttons.append([InlineKeyboardButton("ðŸ”™ Back", callback_data=f"quizview|{quiz_id}")])
        if len(buttons) == 1: await query.edit_message_text("âŒ No registered groups found. Register a group first with /register")
        else: await query.edit_message_text("ðŸ“¢ *Select Group to Publish*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

async def error_handler(update, context):
    if isinstance(context.error, BadRequest) and "Message is not modified" in str(context.error): return
    logger.error("BOT ERROR: %r", context.error)

# =========================================================
# â± BACKGROUND SCHEDULER (CHECKS FOR SCHEDULED STARTS)
# =========================================================

async def schedule_checker(app: Application):
    while True:
        await asyncio.sleep(20)
        try:
            now_ist = datetime.datetime.now(IST_TZ)
            curr_time_str = now_ist.strftime("%I:%M %p").upper()
            curr_full_str = now_ist.strftime("%d/%m/%Y %I:%M %p").upper()

            for sid, session in list(group_sessions.items()):
                if session.get("state") == "lobby" and not session.get("running"):
                    quiz = quizzes.get(session.get("quiz_id"))
                    if not quiz: continue
                    stime = str(quiz.get("schedule_time", "Off")).upper()
                    if curr_time_str == stime or curr_full_str == stime:
                        logger.info(f"Triggering scheduled quiz {sid} at {stime}")
                        await start_quiz_from_lobby(sid, app, None)

            to_remove_auto = []
            if "auto_schedules" not in system_data: system_data["auto_schedules"] = []

            for i, sched in enumerate(system_data["auto_schedules"]):
                stime = sched.get("trigger_time", "").upper()
                if curr_time_str == stime or curr_full_str == stime:
                    logger.info(f"Triggering Auto-Schedule Quiz for Group {sched['group_id']}")

                    quiz_id = sched["quiz_id"]
                    quiz = quizzes.get(quiz_id)
                    chat_id = int(sched["group_id"])

                    if quiz and str(chat_id) in saved_groups:
                        sid = f"s_{int(time.time()*1000)}_{random.randint(100,999)}"
                        group_sessions[sid] = {
                            "chat_id": chat_id,
                            "quiz_id": quiz_id,
                            "questions": prepare_quiz_for_run(quiz),
                            "index": 0,
                            "players": {},
                            "answered": {},
                            "running": False,
                            "state": "lobby",
                            "ready_users": [],
                            "owner": sched["owner"],
                            "timer": quiz.get("timer",30),
                            "mark_correct": quiz.get("mark_correct",4),
                            "mark_wrong": quiz.get("mark_wrong",-1),
                            "question_start": 0
                        }

                        try:
                            msg = await app.bot.send_message(chat_id, get_lobby_text(quiz,0), parse_mode="Markdown")
                            group_sessions[sid]["lobby_msg_id"] = msg.message_id

                            await start_quiz_from_lobby(sid, app, None)
                        except Exception as e:
                            logger.error(f"Failed to auto-start in group {chat_id}: {e}")

                    to_remove_auto.append(i)

            for i in reversed(to_remove_auto):
                system_data["auto_schedules"].pop(i)
                global needs_save
                needs_save = True

        except asyncio.CancelledError: break
        except Exception as e: logger.error(f"Schedule checker error: {e}")

# =========================================================
# ðŸš€ MAIN LOOP
# =========================================================

def main():
    async def post_init(application):
        await load_all_data()
        asyncio.create_task(auto_save_loop())
        asyncio.create_task(cleanup_stale_sessions())
        asyncio.create_task(schedule_checker(application))
        asyncio.create_task(resume_active_quizzes(application))

    t_request = HTTPXRequest(
        connection_pool_size=32,
        read_timeout=120.0,
        write_timeout=120.0,
        connect_timeout=120.0,
        pool_timeout=60.0
    )

    app = (Application.builder()
           .token(BOT_TOKEN)
           .request(t_request)
           .post_init(post_init)
           .build())

    app.add_handler(TypeHandler(Update, access_middleware), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("users", list_users_cmd))
    app.add_handler(CommandHandler("register", register_group))
    app.add_handler(CommandHandler("unregister", unregister_group))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("rank", rank_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("revoke", revoke_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(PollAnswerHandler(poll_answer_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)

    logger.info("ðŸŒ¿ Horticulture Master Bot v25.0 ULTRA PRO started!")

    app.run_polling(allowed_updates=Update.ALL_TYPES, timeout=60, drop_pending_updates=True)

if __name__ == "__main__":
    main()
