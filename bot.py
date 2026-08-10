import os
import re
import json
import time
import asyncio
import random
import csv
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
    filters,
)

# =========================================================
# 🌿 HORTICULTURE MASTER BOT v6.9
# =========================================================

ADMIN_ID = 5183668353

# IMPORTANT:
# Termux me token environment variable se set karein:
# export BOT_TOKEN="YOUR_NEW_BOT_TOKEN"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DATA_FILE = "quizzes.json"
GROUPS_FILE = "groups.json"
USERS_FILE = "users.json"
BANNED_FILE = "banned.json"

LOGO_FILE = "horticulture_master.png"

MAX_QUESTIONS = 1000
TOP_N = 20

MIN_READY = 3
SPEED_BONUS_TIME = 5.0

quizzes = {}
creation = {}
group_sessions = {}
saved_groups = {}
users_data = {}
banned_users = []

# poll_id -> information
active_polls = {}

needs_save = False


# =========================================================
# FILE FUNCTIONS
# =========================================================

def load_json(filename, default_type=dict):
    if not os.path.exists(filename):
        return default_type()

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Load error {filename}: {e}")
        return default_type()


def save_json_sync(data, filename):
    try:
        tmp = filename + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(tmp, filename)

    except Exception as e:
        print(f"Save error {filename}: {e}")


async def save_all_data_async():
    await asyncio.to_thread(
        save_json_sync, quizzes, DATA_FILE
    )

    await asyncio.to_thread(
        save_json_sync, saved_groups, GROUPS_FILE
    )

    await asyncio.to_thread(
        save_json_sync, users_data, USERS_FILE
    )

    await asyncio.to_thread(
        save_json_sync, banned_users, BANNED_FILE
    )


async def auto_save_loop():
    global needs_save

    while True:
        try:
            await asyncio.sleep(15)

            if needs_save:
                await save_all_data_async()
                needs_save = False

        except asyncio.CancelledError:
            break

        except Exception as e:
            print("Auto save error:", e)


def load_all_data():
    global quizzes
    global saved_groups
    global users_data
    global banned_users

    quizzes = load_json(DATA_FILE)
    saved_groups = load_json(GROUPS_FILE)
    users_data = load_json(USERS_FILE)
    banned_users = load_json(BANNED_FILE, list)


# =========================================================
# MENUS
# =========================================================

def main_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Create New Quiz",
                callback_data="newquiz"
            )
        ],
        [
            InlineKeyboardButton(
                "📚 My Quizzes",
                callback_data="myquizzes"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 Global Rank",
                callback_data="show_rank"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Registered Groups",
                callback_data="groups"
            )
        ]
    ])


def question_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚡ Add More Questions",
                callback_data="addmore"
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ Edit Last",
                callback_data="editlast"
            ),
            InlineKeyboardButton(
                "↩️ Undo Last",
                callback_data="undolast"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑️ Clear All",
                callback_data="clearall"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Done & Publish",
                callback_data="done"
            )
        ]
    ])


def timer_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "20 sec",
                callback_data="timer_20"
            ),
            InlineKeyboardButton(
                "30 sec",
                callback_data="timer_30"
            )
        ],
        [
            InlineKeyboardButton(
                "40 sec",
                callback_data="timer_40"
            ),
            InlineKeyboardButton(
                "45 sec",
                callback_data="timer_45"
            )
        ],
        [
            InlineKeyboardButton(
                "60 sec",
                callback_data="timer_60"
            )
        ]
    ])


def marking_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕4 / ➖1",
                callback_data="mark_4_-1"
            )
        ],
        [
            InlineKeyboardButton(
                "➕1 / ➖0.25",
                callback_data="mark_1_-0.25"
            )
        ],
        [
            InlineKeyboardButton(
                "➕1 / 0",
                callback_data="mark_1_0"
            )
        ]
    ])


def shuffle_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❌ No Shuffle",
                callback_data="shuffle_none"
            )
        ],
        [
            InlineKeyboardButton(
                "🔀 Questions",
                callback_data="shuffle_questions"
            )
        ],
        [
            InlineKeyboardButton(
                "🔀 Answers",
                callback_data="shuffle_answers"
            )
        ],
        [
            InlineKeyboardButton(
                "🔀 All",
                callback_data="shuffle_all"
            )
        ]
    ])


def mode_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏆 Live Quiz",
                callback_data="mode_live"
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Direct Polls",
                callback_data="mode_direct"
            )
        ]
    ])


# =========================================================
# HELPERS
# =========================================================

def normalize(text):

    return re.sub(
        r"\r\n?",
        "\n",
        text or ""
    ).strip()


def parse_answer(value):

    value = (
        value
        .strip()
        .lower()
        .replace(".", "")
        .replace(")", "")
        .replace(":", "")
        .strip()
    )

    return {
        "a": 0,
        "b": 1,
        "c": 2,
        "d": 3,
        "1": 0,
        "2": 1,
        "3": 2,
        "4": 3
    }.get(value, -1)


def parse_question(block):

    lines = [
        x.strip()
        for x in normalize(block).split("\n")
        if x.strip()
    ]

    if not lines:
        return None

    q_lines = []
    options = []
    answer = -1
    explanation_lines = []

    mode = "question"

    for line in lines:

        low = line.lower().strip()

        # -------------------------------------------------
        # ANSWER
        # -------------------------------------------------

        if re.match(
            r"^(correct\s*answer|correct\s*option|answer|ans|correct)\s*:",
            low
        ):

            value = re.split(
                r":",
                line,
                maxsplit=1
            )[1].strip()

            answer = parse_answer(value)
            mode = "after_answer"
            continue

        # -------------------------------------------------
        # EXPLANATION
        # -------------------------------------------------

        if re.match(
            r"^(explanation|exp|solution|reason)\s*:",
            low
        ):

            value = re.split(
                r":",
                line,
                maxsplit=1
            )[1].strip()

            if value:
                explanation_lines.append(value)

            mode = "explanation"
            continue

        if mode == "explanation":

            explanation_lines.append(line)
            continue

        # -------------------------------------------------
        # OPTIONS
        # -------------------------------------------------

        option_match = re.match(
            r"^(?:option\s*)?([a-d]|[1-4])[\s\.\):\-]+\s*(.+)$",
            line,
            re.I
        )

        if option_match and mode in (
            "question",
            "options"
        ):

            options.append(
                option_match.group(2).strip()
            )

            mode = "options"
            continue

        # -------------------------------------------------
        # QUESTION
        # -------------------------------------------------

        if mode == "question":

            q_lines.append(line)

        elif mode == "after_answer":

            # Ignore accidental text after answer
            pass

    question = "\n".join(q_lines).strip()

    question = re.sub(
        r"^(question|q\d*)\s*[:.)\-]\s*",
        "",
        question,
        flags=re.I
    ).strip()

    explanation = "\n".join(
        explanation_lines
    ).strip()

    if not explanation:
        explanation = "No explanation provided."

    # -----------------------------------------------
    # BASIC VALIDATION
    # -----------------------------------------------

    if not question:
        return None

    if len(options) < 2:
        return None

    if len(options) > 4:
        options = options[:4]

    if answer < 0:
        return None

    if answer >= len(options):
        return None

    return {
        "question": question,
        "options": options,
        "correct": answer,
        "explanation": explanation
    }


def parse_many(text):

    text = normalize(text)

    if not text:
        return []

    # Q1, Q2, Q3...
    parts = re.split(
        r"(?=^\s*(?:Q|Question)\s*\d*\s*[:.)\-])",
        text,
        flags=re.I | re.M
    )

    if len(parts) == 1:

        parts = re.split(
            r"\n\s*\n+",
            text
        )

    result = []

    for part in parts:

        q = parse_question(part)

        if q:
            result.append(q)

    return result


def clean_markdown_name(name):

    if not name:
        return "Unknown"

    return (
        str(name)
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
    )


def is_banned_sync(uid):

    return uid in banned_users


async def is_banned(uid):

    return is_banned_sync(uid)


# =========================================================
# USER REGISTRATION
# =========================================================

async def register_user(update):

    global needs_save

    user = update.effective_user

    if not user:
        return

    uid = str(user.id)

    if uid not in users_data:

        users_data[uid] = {
            "name": user.full_name,
            "xp": 0,
            "played": 0
        }

        needs_save = True


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    uid = update.effective_user.id

    if await is_banned(uid):
        return

    creation.pop(uid, None)

    await register_user(update)

    text = (
        "🌱 *Horticulture Master Quiz Bot v6.9*\n\n"
        "⚡ Ultra Fast Quiz System\n"
        "📝 Flexible Question Parser\n"
        "🗳️ Telegram Quiz Poll Support\n"
        "🏆 Live Top 20 Leaderboard\n"
        "📊 Complete Excel Report\n"
        "🔀 Multiple Shuffle Modes\n\n"
        "👇 Select an option:"
    )

    await update.effective_message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


# =========================================================
# HELP
# =========================================================

async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "🌿 *HORTICULTURE MASTER BOT v6.9*\n\n"
        "*/start* — Main Menu\n"
        "*/history* — All quizzes\n"
        "*/stats* — Admin statistics\n"
        "*/register* — Register current group\n"
        "*/rank* — Global ranking\n"
        "*/stop* — Stop active quiz\n"
        "*/ban ID* — Admin ban\n"
        "*/unban ID* — Admin unban\n\n"
        "Question format:\n"
        "Question\n"
        "A) Option 1\n"
        "B) Option 2\n"
        "C) Option 3\n"
        "D) Option 4\n"
        "Correct Answer: C\n"
        "Explanation: optional"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown"
    )


# =========================================================
# GROUP REGISTER
# =========================================================

async def register_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global needs_save

    chat = update.effective_chat

    if not chat:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):

        await update.effective_message.reply_text(
            "⚠️ Ye command group ke andar use karein."
        )

        return

    saved_groups[str(chat.id)] = {
        "title": chat.title or str(chat.id),
        "type": chat.type
    }

    needs_save = True

    await update.effective_message.reply_text(
        "✅ *Group Registered!*\n\n"
        f"📢 {chat.title}\n"
        f"🆔 `{chat.id}`\n\n"
        "Ab private chat se quiz ko is group me share kar sakte hain.",
        parse_mode="Markdown"
    )


# =========================================================
# ADMIN
# =========================================================

async def ban_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global needs_save

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /ban USER_ID"
        )
        return

    try:

        target = int(context.args[0])

        if target not in banned_users:
            banned_users.append(target)

        needs_save = True

        await update.effective_message.reply_text(
            f"✅ User `{target}` banned.",
            parse_mode="Markdown"
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Invalid User ID."
        )


async def unban_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global needs_save

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /unban USER_ID"
        )
        return

    try:

        target = int(context.args[0])

        if target in banned_users:
            banned_users.remove(target)

        needs_save = True

        await update.effective_message.reply_text(
            f"✅ User `{target}` unbanned.",
            parse_mode="Markdown"
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Invalid User ID."
        )


async def stats_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    players = sorted(
        users_data.values(),
        key=lambda x: x.get("xp", 0),
        reverse=True
    )

    text = (
        "📊 *BOT ANALYTICS*\n\n"
        f"👥 Users: *{len(users_data)}*\n"
        f"📢 Groups: *{len(saved_groups)}*\n"
        f"📚 Quizzes: *{len(quizzes)}*\n\n"
        "🏆 *TOP 5*\n"
    )

    for i, p in enumerate(players[:5], 1):

        text += (
            f"{i}. "
            f"{clean_markdown_name(p.get('name'))} "
            f"— {p.get('xp', 0):g} XP\n"
        )

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown"
    )


# =========================================================
# GLOBAL RANK
# =========================================================

async def rank_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    uid = str(update.effective_user.id)

    if await is_banned(update.effective_user.id):
        return

    user = users_data.get(
        uid,
        {
            "xp": 0,
            "played": 0
        }
    )

    lb = sorted(
        users_data.values(),
        key=lambda x: x.get("xp", 0),
        reverse=True
    )

    text = (
        "🌍 *GLOBAL TOURNAMENT RANK*\n\n"
        f"✨ Your XP: *{user.get('xp', 0):g}*\n"
        f"📝 Played: *{user.get('played', 0)}*\n\n"
        "🏆 *TOP 20*\n"
    )

    for i, p in enumerate(lb[:20], 1):

        medal = (
            "🥇" if i == 1
            else "🥈" if i == 2
            else "🥉" if i == 3
            else f"{i}."
        )

        text += (
            f"{medal} "
            f"{clean_markdown_name(p.get('name'))} "
            f"— *{p.get('xp', 0):g} XP*\n"
        )

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown"
    )


# =========================================================
# CREATION
# =========================================================

async def begin_creation(
    update,
    context
):

    uid = update.effective_user.id

    creation[uid] = {
        "mode": "title",
        "title": "",
        "questions": [],
        "timer": 30,
        "mark_correct": 4,
        "mark_wrong": -1,
        "shuffle": "none",
        "quiz_mode": "live"
    }

    await update.effective_message.reply_text(
        "📝 *Quiz Title bhejiye:*",
        parse_mode="Markdown"
    )


# =========================================================
# MESSAGE UPLOAD
# =========================================================

async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    uid = update.effective_user.id

    if await is_banned(uid):
        return

    st = creation.get(uid)

    if not st:
        return

    message = update.effective_message

    # -----------------------------------------------------
    # POLL FORWARD
    # -----------------------------------------------------

    if message.poll:

        if st["mode"] == "title":

            await message.reply_text(
                "❌ Pehle Quiz Title bhejiye."
            )

            return

        poll = message.poll

        if poll.type != "quiz":

            await message.reply_text(
                "❌ Sirf Telegram Quiz Poll forward karein."
            )

            return

        question = {
            "question": poll.question,
            "options": [
                x.text
                for x in poll.options
            ],
            "correct": poll.correct_option_id,
            "explanation": (
                poll.explanation
                or "No explanation provided."
            )
        }

        st["questions"].append(question)

        await message.reply_text(
            f"🗳️ *Poll Added!*\n\n"
            f"📚 Total Questions: "
            f"*{len(st['questions'])}*",
            parse_mode="Markdown",
            reply_markup=question_menu()
        )

        return

    # -----------------------------------------------------
    # TEXT / CAPTION
    # -----------------------------------------------------

    text = normalize(
        message.text
        or message.caption
        or ""
    )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    if st["mode"] == "title":

        if not text:

            await message.reply_text(
                "❌ Title text me bhejiye."
            )

            return

        st["title"] = text
        st["mode"] = "questions"

        await message.reply_text(
            "✅ *Title Saved!*\n\n"
            "Ab questions bhejiye.\n\n"
            "📝 Text format\n"
            "🗳️ Forward Telegram Quiz Poll\n"
            "📸 Photo + question bhi supported hai.\n\n"
            "Question + Options + Correct Answer compulsory.\n"
            "Explanation optional.",
            parse_mode="Markdown",
            reply_markup=question_menu()
        )

        return

    # -----------------------------------------------------
    # EDIT MODE
    # -----------------------------------------------------

    if st["mode"] == "edit":

        qs = parse_many(text)

        if not qs:

            await message.reply_text(
                "❌ Question parse nahi hua."
            )

            return

        st["questions"][-1] = qs[0]
        st["mode"] = "questions"

        await message.reply_text(
            "✏️ *Last Question Updated!*\n\n"
            f"Total: {len(st['questions'])}",
            parse_mode="Markdown",
            reply_markup=question_menu()
        )

        return

    # -----------------------------------------------------
    # QUESTIONS
    # -----------------------------------------------------

    if st["mode"] == "questions":

        qs = parse_many(text)

        if not qs:

            await message.reply_text(
                "❌ *Invalid format.*\n\n"
                "Question + Options + Correct Answer "
                "hona compulsory hai.\n\n"
                "Example:\n\n"
                "Which is a fruit crop?\n"
                "A) Wheat\n"
                "B) Mango\n"
                "C) Rice\n"
                "D) Maize\n"
                "Correct Answer: B\n"
                "Explanation: Mango is a fruit crop.",
                parse_mode="Markdown"
            )

            return

        room = MAX_QUESTIONS - len(
            st["questions"]
        )

        qs = qs[:room]

        st["questions"].extend(qs)

        await message.reply_text(
            "⚡ *Questions Added!*\n\n"
            f"➕ Added: {len(qs)}\n"
            f"📚 Total: {len(st['questions'])}",
            parse_mode="Markdown",
            reply_markup=question_menu()
        )


# =========================================================
# GROUP SELECTION
# =========================================================

async def show_group_selection(
    query,
    quiz_id
):

    if not saved_groups:

        await query.message.reply_text(
            "❌ Koi registered group nahi hai.\n\n"
            "Pehle group me /register command chalayein."
        )

        return

    buttons = []

    for gid, info in saved_groups.items():

        buttons.append([
            InlineKeyboardButton(
                f"📢 {info.get('title', gid)}",
                callback_data=f"sendgroup|{quiz_id}|{gid}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "❌ Cancel",
            callback_data="cancel"
        )
    ])

    await query.message.reply_text(
        "📢 *Select Group*\n\n"
        "Neeche jitne groups registered hain "
        "sab dikh rahe hain.\n\n"
        "👉 Jis group ko select karoge, "
        "quiz usi group me open hogi.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# SHUFFLE
# =========================================================

def prepare_quiz_for_run(quiz):

    questions = []

    for original in quiz["questions"]:

        q = dict(original)

        q["options"] = list(
            original["options"]
        )

        q["correct"] = int(
            original["correct"]
        )

        questions.append(q)

    mode = quiz.get(
        "shuffle",
        "none"
    )

    if mode in (
        "questions",
        "all"
    ):

        random.shuffle(questions)

    if mode in (
        "answers",
        "all"
    ):

        for q in questions:

            correct_text = q["options"][
                q["correct"]
            ]

            random.shuffle(
                q["options"]
            )

            q["correct"] = q["options"].index(
                correct_text
            )

    return questions


# =========================================================
# SEND LIVE QUESTION
# =========================================================

async def send_group_question(
    sid,
    context
):

    session = group_sessions.get(sid)

    if not session:
        return

    if not session.get("running"):
        return

    questions = session["questions"]

    idx = session["index"]

    if idx >= len(questions):

        await finish_group(
            sid,
            context
        )

        return

    q = questions[idx]

    full_question = (
        f"📝 *Q{idx + 1}/{len(questions)}*\n\n"
        f"{q['question']}"
    )

    if q.get("photo"):

        try:

            await context.bot.send_photo(
                chat_id=session["chat_id"],
                photo=q["photo"],
                caption=full_question[:1024],
                parse_mode="Markdown"
            )

        except Exception:
            pass

    elif len(q["question"]) > 280:

        try:

            await context.bot.send_message(
                chat_id=session["chat_id"],
                text=full_question,
                parse_mode="Markdown"
            )

        except Exception:
            pass

    poll_question = (
        f"Q{idx + 1}: "
        f"{q['question']}"
    )

    if len(poll_question) > 300:

        poll_question = (
            f"Q{idx + 1}: "
            "Select the correct option."
        )

    options = [
        str(x)[:100]
        for x in q["options"]
    ]

    explanation = q.get(
        "explanation",
        "Correct Answer!"
    )

    explanation = explanation[:200]

    try:

        poll = await context.bot.send_poll(

            chat_id=session["chat_id"],

            question=poll_question,

            options=options,

            type="quiz",

            correct_option_id=q["correct"],

            explanation=explanation,

            open_period=int(
                session["timer"]
            ),

            is_anonymous=False
        )

        active_polls[poll.poll.id] = {
            "sid": sid,
            "index": idx
        }

        session["active_poll"] = poll.poll.id
        session["question_start"] = time.time()

        session["timer_task"] = asyncio.create_task(
            group_timer(
                sid,
                context,
                session["timer"]
            )
        )

    except Exception as e:

        print(
            "Poll Send Error:",
            e
        )


# =========================================================
# TIMER
# =========================================================

async def group_timer(
    sid,
    context,
    seconds
):

    try:

        await asyncio.sleep(
            seconds + 1
        )

        session = group_sessions.get(sid)

        if not session:
            return

        if not session.get("running"):
            return

        q = session["questions"][
            session["index"]
        ]

        explanation = q.get(
            "explanation",
            ""
        )

        if (
            explanation
            and explanation !=
            "No explanation provided."
        ):

            try:

                await context.bot.send_message(

                    chat_id=session["chat_id"],

                    text=(
                        f"💡 *Explanation "
                        f"Q{session['index'] + 1}:*\n"
                        f"{explanation}"
                    ),

                    parse_mode="Markdown"
                )

            except Exception:
                pass

        await asyncio.sleep(3)

        session["index"] += 1

        await send_group_question(
            sid,
            context
        )

    except asyncio.CancelledError:
        pass

    except Exception as e:
        print(
            "Timer Error:",
            e
        )


# =========================================================
# POLL ANSWERS
# =========================================================

async def poll_answer_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    answer = update.poll_answer

    poll_id = answer.poll_id

    info = active_polls.get(
        poll_id
    )

    if not info:
        return

    sid = info.get("sid")

    session = group_sessions.get(
        sid
    )

    if not session:
        return

    uid = answer.user.id

    idx = info.get(
        "index",
        session["index"]
    )

    if idx >= len(
        session["questions"]
    ):
        return

    q = session["questions"][idx]

    # Prevent duplicate scoring
    answered = session.setdefault(
        "answered",
        {}
    )

    poll_users = answered.setdefault(
        poll_id,
        set()
    )

    if uid in poll_users:
        return

    poll_users.add(uid)

    # -----------------------------------------------------
    # PLAYER
    # -----------------------------------------------------

    player = session["players"].setdefault(
        str(uid),
        {
            "name": answer.user.full_name,
            "score": 0,
            "correct": 0,
            "wrong": 0,
            "fast_count": 0,
            "answered": 0
        }
    )

    player["name"] = (
        answer.user.full_name
    )

    player["answered"] += 1

    selected = (
        answer.option_ids[0]
        if answer.option_ids
        else -1
    )

    if selected == q["correct"]:

        player["correct"] += 1

        player["score"] += session[
            "mark_correct"
        ]

        elapsed = (
            time.time()
            - session.get(
                "question_start",
                time.time()
            )
        )

        if elapsed <= SPEED_BONUS_TIME:

            player["fast_count"] += 1

    else:

        player["wrong"] += 1

        player["score"] += session[
            "mark_wrong"
        ]

    # Register global user
    uid_str = str(uid)

    if uid_str not in users_data:

        users_data[uid_str] = {
            "name": answer.user.full_name,
            "xp": 0,
            "played": 0
        }

    users_data[uid_str]["name"] = (
        answer.user.full_name
    )

    global needs_save
    needs_save = True


# =========================================================
# FINISH GROUP
# =========================================================

async def finish_group(
    sid,
    context
):

    global needs_save

    session = group_sessions.get(
        sid
    )

    if not session:
        return

    if not session.get("running"):
        return

    session["running"] = False

    # Cancel timer
    task = session.get(
        "timer_task"
    )

    if task:

        try:
            task.cancel()
        except Exception:
            pass

    quiz = quizzes.get(
        session["quiz_id"]
    )

    if not quiz:
        return

    players = session.get(
        "players",
        {}
    )

    # -----------------------------------------------------
    # GLOBAL XP + QUIZ LEADERBOARD
    # -----------------------------------------------------

    quiz_lb = quiz.setdefault(
        "leaderboard",
        []
    )

    for uid, p in players.items():

        if str(uid) not in users_data:

            users_data[str(uid)] = {
                "name": p["name"],
                "xp": 0,
                "played": 0
            }

        users_data[str(uid)]["xp"] += (
            p["score"]
        )

        users_data[str(uid)]["played"] += 1

        existing = next(
            (
                x
                for x in quiz_lb
                if str(x.get("user")) ==
                str(uid)
            ),
            None
        )

        if existing:

            if p["score"] > existing["score"]:
                existing["score"] = p["score"]

            existing["name"] = p["name"]

        else:

            quiz_lb.append({
                "user": int(uid),
                "name": p["name"],
                "score": p["score"]
            })

    quiz_lb.sort(
        key=lambda x: x.get(
            "score",
            0
        ),
        reverse=True
    )

    needs_save = True

    # -----------------------------------------------------
    # CURRENT QUIZ RANK
    # -----------------------------------------------------

    ranking = []

    for uid, p in players.items():

        ranking.append({
            "uid": uid,
            "name": p["name"],
            "score": p["score"],
            "correct": p.get(
                "correct",
                0
            ),
            "wrong": p.get(
                "wrong",
                0
            ),
            "fast": p.get(
                "fast_count",
                0
            )
        })

    ranking.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # -----------------------------------------------------
    # TELEGRAM TOP 20
    # -----------------------------------------------------

    lines = [
        "🏁 *QUIZ FINISHED!*",
        "",
        f"📚 *{quiz['title']}*",
        f"👥 Participants: *{len(ranking)}*",
        "",
        "🏆 *FINAL TOP 20*",
        ""
    ]

    for rank, p in enumerate(
        ranking[:20],
        1
    ):

        medal = (
            "🥇" if rank == 1
            else "🥈" if rank == 2
            else "🥉" if rank == 3
            else f"{rank}."
        )

        lines.append(
            f"{medal} "
            f"{p['name']} — "
            f"*{p['score']:g} pts*"
        )

    try:

        await context.bot.send_message(
            chat_id=session["chat_id"],
            text="\n".join(lines),
            parse_mode="Markdown"
        )

    except Exception as e:

        print(
            "Leaderboard error:",
            e
        )

    # -----------------------------------------------------
    # EXCEL
    # ALL PARTICIPANTS
    # -----------------------------------------------------

    await create_excel_report(
        session,
        quiz,
        ranking,
        context
    )

    group_sessions.pop(
        sid,
        None
    )


# =========================================================
# EXCEL REPORT
# =========================================================

async def create_excel_report(
    session,
    quiz,
    ranking,
    context
):

    try:

        from openpyxl import Workbook
        from openpyxl.styles import (
            Font,
            Alignment,
            PatternFill,
            Border,
            Side
        )
        from openpyxl.drawing.image import Image as XLImage

    except ImportError:

        await context.bot.send_message(
            chat_id=session["chat_id"],
            text=(
                "⚠️ Excel report nahi ban saka.\n\n"
                "Termux me run karein:\n"
                "`pip install openpyxl pillow`"
            ),
            parse_mode="Markdown"
        )

        return

    wb = Workbook()

    ws = wb.active

    ws.title = "Horticulture Master"

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    ws.merge_cells(
        "A1:H1"
    )

    ws["A1"] = "HORTICULTURE MASTER"

    ws["A1"].font = Font(
        bold=True,
        size=24
    )

    ws["A1"].alignment = Alignment(
        horizontal="center",
        vertical="center"
    )

    ws.row_dimensions[1].height = 40

    # -----------------------------------------------------
    # LOGO
    # -----------------------------------------------------

    if os.path.exists(
        LOGO_FILE
    ):

        try:

            img = XLImage(
                LOGO_FILE
            )

            img.width = 130
            img.height = 130

            ws.add_image(
                img,
                "J2"
            )

        except Exception as e:

            print(
                "Logo error:",
                e
            )

    # -----------------------------------------------------
    # QUIZ DETAILS
    # -----------------------------------------------------

    ws["A3"] = "Quiz"
    ws["B3"] = quiz["title"]

    ws["A4"] = "Participants"
    ws["B4"] = len(ranking)

    ws["A5"] = "Conducted By"
    ws["B5"] = "Akash Dwivedi"

    ws["A6"] = "Report"
    ws["B6"] = "Complete Participant Report"

    for cell in (
        "A3",
        "A4",
        "A5",
        "A6"
    ):

        ws[cell].font = Font(
            bold=True
        )

    # -----------------------------------------------------
    # TABLE
    # -----------------------------------------------------

    headers = [
        "Rank",
        "Name",
        "User ID",
        "Score",
        "Correct",
        "Wrong",
        "Fast Answers",
        "Percentage"
    ]

    start_row = 8

    for col, header in enumerate(
        headers,
        1
    ):

        cell = ws.cell(
            start_row,
            col,
            header
        )

        cell.font = Font(
            bold=True
        )

        cell.alignment = Alignment(
            horizontal="center"
        )

    # -----------------------------------------------------
    # ALL PARTICIPANTS
    # -----------------------------------------------------

    total_questions = max(
        len(session["questions"]),
        1
    )

    for rank, p in enumerate(
        ranking,
        1
    ):

        row = start_row + rank

        score = p["score"]

        correct = p["correct"]

        percentage = (
            correct /
            total_questions
        ) * 100

        values = [
            rank,
            p["name"],
            p["uid"],
            score,
            correct,
            p["wrong"],
            p["fast"],
            round(
                percentage,
                2
            )
        ]

        for col, value in enumerate(
            values,
            1
        ):

            cell = ws.cell(
                row,
                col,
                value
            )

            cell.alignment = Alignment(
                vertical="center"
            )

    # -----------------------------------------------------
    # WIDTH
    # -----------------------------------------------------

    widths = {
        "A": 10,
        "B": 28,
        "C": 18,
        "D": 14,
        "E": 12,
        "F": 12,
        "G": 16,
        "H": 15,
        "J": 20
    }

    for col, width in widths.items():

        ws.column_dimensions[
            col
        ].width = width

    # -----------------------------------------------------
    # BORDERS
    # -----------------------------------------------------

    thin = Side(
        style="thin"
    )

    border = Border(
        left=thin,
        right=thin,
        top=thin,
        bottom=thin
    )

    for row in ws.iter_rows(
        min_row=start_row,
        max_row=start_row + len(ranking),
        min_col=1,
        max_col=8
    ):

        for cell in row:

            cell.border = border

    # -----------------------------------------------------
    # FREEZE
    # -----------------------------------------------------

    ws.freeze_panes = "A9"

    # -----------------------------------------------------
    # SAVE MEMORY
    # -----------------------------------------------------

    output = BytesIO()

    wb.save(
        output
    )

    output.seek(0)

    output.name = (
        "Horticulture_Master_"
        f"{int(time.time())}.xlsx"
    )

    # -----------------------------------------------------
    # SEND
    # -----------------------------------------------------

    try:

        await context.bot.send_document(
            chat_id=session["chat_id"],
            document=output,
            caption=(
                "📊 *Horticulture Master — "
                "Complete Report*\n\n"
                f"👥 Participants: "
                f"{len(ranking)}\n"
                "🏆 Telegram Leaderboard: "
                "Top 20\n"
                "📋 Excel: ALL Participants\n\n"
                "Conducted by Akash Dwivedi"
            ),
            parse_mode="Markdown"
        )

    except Exception as e:

        print(
            "Excel send error:",
            e
        )


# =========================================================
# DIRECT POLL MODE
# =========================================================

async def send_direct_polls_task(
    chat_id,
    quiz_id,
    context
):

    quiz = quizzes.get(
        quiz_id
    )

    if not quiz:
        return

    questions = prepare_quiz_for_run(
        quiz
    )

    try:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"📚 *{quiz['title']}*\n\n"
                "👇 Quiz Started\n"
                "Complete all questions."
            ),
            parse_mode="Markdown"
        )

    except Exception:
        return

    # Direct mode session
    sid = (
        f"direct_{chat_id}_"
        f"{int(time.time())}"
    )

    group_sessions[sid] = {
        "chat_id": chat_id,
        "quiz_id": quiz_id,
        "questions": questions,
        "index": 0,
        "players": {},
        "running": True,
        "timer": 3600,
        "mark_correct": quiz.get(
            "mark_correct",
            1
        ),
        "mark_wrong": quiz.get(
            "mark_wrong",
            0
        ),
        "direct": True
    }

    session = group_sessions[sid]

    for idx, q in enumerate(
        questions
    ):

        if not session["running"]:
            break

        poll_question = (
            f"Q{idx + 1}: "
            f"{q['question']}"
        )

        if len(poll_question) > 300:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"📝 *Q{idx + 1}*\n\n"
                    f"{q['question']}"
                ),
                parse_mode="Markdown"
            )

            poll_question = (
                f"Q{idx + 1}: "
                "Select correct option."
            )

        options = [
            str(x)[:100]
            for x in q["options"]
        ]

        try:

            poll = await context.bot.send_poll(
                chat_id=chat_id,
                question=poll_question,
                options=options,
                type="quiz",
                correct_option_id=q["correct"],
                explanation=q.get(
                    "explanation",
                    "Correct Answer!"
                )[:200],
                is_anonymous=False
            )

            active_polls[poll.poll.id] = {
                "sid": sid,
                "index": idx
            }

        except Exception as e:

            print(
                "Direct poll error:",
                e
            )

        await asyncio.sleep(
            2
        )

    # Wait a little for final answers
    await asyncio.sleep(
        5
    )

    await finish_group(
        sid,
        context
    )


# =========================================================
# HISTORY
# =========================================================

async def show_history(
    update,
    context
):

    uid = update.effective_user.id

    mine = [
        (qid, q)
        for qid, q in quizzes.items()
        if str(
            q.get("owner")
        ) == str(uid)
        or uid == ADMIN_ID
    ]

    if not mine:

        await update.effective_message.reply_text(
            "📚 No quizzes found."
        )

        return

    buttons = []

    for qid, q in reversed(
        mine
    ):

        title = q.get(
            "title",
            "Untitled"
        )

        buttons.append([
            InlineKeyboardButton(
                f"📚 {title[:35]}",
                callback_data=f"quizview|{qid}"
            )
        ])

    await update.effective_message.reply_text(
        "📚 *QUIZ HISTORY*\n\n"
        "Aapki saved quizzes yahan hain:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )


# =========================================================
# PUBLISH QUIZ
# =========================================================

async def publish_quiz(
    query,
    quiz_id
):

    quiz = quizzes.get(
        quiz_id
    )

    if not quiz:
        return

    await show_group_selection(
        query,
        quiz_id
    )


# =========================================================
# CALLBACKS
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global needs_save

    query = update.callback_query

    await query.answer()

    uid = query.from_user.id

    if await is_banned(uid):
        return

    data = query.data or ""

    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

    if data == "cancel":

        await query.message.reply_text(
            "❌ Cancelled."
        )

        return

    # -----------------------------------------------------
    # NEW QUIZ
    # -----------------------------------------------------

    if data == "newquiz":

        await begin_creation(
            query,
            context
        )

        return

    # -----------------------------------------------------
    # MY QUIZZES
    # -----------------------------------------------------

    if data == "myquizzes":

        await show_history(
            query,
            context
        )

        return

    # -----------------------------------------------------
    # GLOBAL RANK
    # -----------------------------------------------------

    if data == "show_rank":

        await rank_cmd(
            query,
            context
        )

        return

    # -----------------------------------------------------
    # GROUPS
    # -----------------------------------------------------

    if data == "groups":

        if not saved_groups:

            await query.message.reply_text(
                "❌ No registered groups."
            )

            return

        text = (
            "👥 *REGISTERED GROUPS*\n\n"
        )

        for i, (gid, info) in enumerate(
            saved_groups.items(),
            1
        ):

            text += (
                f"{i}. "
                f"{info.get('title', gid)}\n"
            )

        await query.message.reply_text(
            text,
            parse_mode="Markdown"
        )

        return

    # -----------------------------------------------------
    # ADD MORE
    # -----------------------------------------------------

    if data == "addmore":

        st = creation.get(uid)

        if st:

            st["mode"] = "questions"

            await query.message.reply_text(
                "⚡ Questions bhejiye."
            )

        return

    # -----------------------------------------------------
    # EDIT LAST
    # -----------------------------------------------------

    if data == "editlast":

        st = creation.get(uid)

        if not st or not st["questions"]:

            await query.message.reply_text(
                "❌ Koi question nahi hai."
            )

            return

        st["mode"] = "edit"

        await query.message.reply_text(
            "✏️ Last question ka corrected "
            "version bhejiye."
        )

        return

    # -----------------------------------------------------
    # UNDO
    # -----------------------------------------------------

    if data == "undolast":

        st = creation.get(uid)

        if st and st["questions"]:

            st["questions"].pop()

            await query.message.reply_text(
                f"↩️ Last question removed.\n"
                f"Total: {len(st['questions'])}",
                reply_markup=question_menu()
            )

        return

    # -----------------------------------------------------
    # CLEAR
    # -----------------------------------------------------

    if data == "clearall":

        st = creation.get(uid)

        if st:

            st["questions"] = []

            await query.message.reply_text(
                "🗑️ All questions cleared.",
                reply_markup=question_menu()
            )

        return

    # -----------------------------------------------------
    # DONE
    # -----------------------------------------------------

    if data == "done":

        st = creation.get(uid)

        if not st:

            return

        if not st["questions"]:

            await query.message.reply_text(
                "❌ At least 1 question required."
            )

            return

        await query.message.reply_text(
            "⏱️ *Select Timer:*",
            parse_mode="Markdown",
            reply_markup=timer_menu()
        )

        return

    # -----------------------------------------------------
    # TIMER
    # -----------------------------------------------------

    if data.startswith(
        "timer_"
    ):

        st = creation.get(uid)

        if not st:
            return

        try:

            timer = int(
                data.split("_")[1]
            )

        except Exception:

            timer = 30

        st["timer"] = timer

        await query.message.reply_text(
            f"⏱️ Timer: *{timer} seconds*\n\n"
            "📊 Select marking:",
            parse_mode="Markdown",
            reply_markup=marking_menu()
        )

        return

    # -----------------------------------------------------
    # MARKING
    # -----------------------------------------------------

    if data.startswith(
        "mark_"
    ):

        st = creation.get(uid)

        if not st:
            return

        parts = data.split("_")

        st["mark_correct"] = float(
            parts[1]
        )

        st["mark_wrong"] = float(
            parts[2]
        )

        await query.message.reply_text(
            f"✅ Marking:\n"
            f"➕ {st['mark_correct']:g}\n"
            f"➖ {st['mark_wrong']:g}\n\n"
            "🔀 Select Shuffle Mode:",
            reply_markup=shuffle_menu()
        )

        return

    # -----------------------------------------------------
    # SHUFFLE
    # -----------------------------------------------------

    if data.startswith(
        "shuffle_"
    ):

        st = creation.get(uid)

        if not st:
            return

        st["shuffle"] = data.replace(
            "shuffle_",
            ""
        )

        await query.message.reply_text(
            "🔀 Shuffle selected.\n\n"
            "Select Quiz Mode:",
            reply_markup=mode_menu()
        )

        return

    # -----------------------------------------------------
    # MODE
    # -----------------------------------------------------

    if data.startswith(
        "mode_"
    ):

        st = creation.get(uid)

        if not st:
            return

        st["quiz_mode"] = data.replace(
            "mode_",
            ""
        )

        quiz_id = (
            f"{uid}_"
            f"{int(time.time() * 1000)}"
        )

        quizzes[quiz_id] = {
            "title": st["title"],
            "questions": st["questions"],
            "timer": st["timer"],
            "mark_correct": st[
                "mark_correct"
            ],
            "mark_wrong": st[
                "mark_wrong"
            ],
            "shuffle": st[
                "shuffle"
            ],
            "mode": st[
                "quiz_mode"
            ],
            "owner": uid,
            "created": time.time(),
            "leaderboard": []
        }

        needs_save = True

        creation.pop(
            uid,
            None
        )

        quiz = quizzes[quiz_id]

        await query.message.reply_text(
            f"📚 *Quiz Ready!*\n\n"
            f"Title: *{quiz['title']}*\n"
            f"Questions: *{len(quiz['questions'])}*\n"
            f"Timer: *{quiz['timer']} sec*\n"
            f"Marking: "
            f"*+{quiz['mark_correct']:g} / "
            f"{quiz['mark_wrong']:g}*\n"
            f"Shuffle: *{quiz['shuffle']}*\n"
            f"Mode: *{quiz['mode']}*",
            parse_mode="Markdown"
        )

        await show_group_selection(
            query,
            quiz_id
        )

        return

    # -----------------------------------------------------
    # SEND GROUP
    # -----------------------------------------------------

    if data.startswith(
        "sendgroup|"
    ):

        parts = data.split("|")

        if len(parts) != 3:
            return

        quiz_id = parts[1]
        gid = parts[2]

        quiz = quizzes.get(
            quiz_id
        )

        group = saved_groups.get(
            gid
        )

        if not quiz or not group:

            await query.message.reply_text(
                "❌ Quiz/group not found."
            )

            return

        chat_id = int(
            gid
        )

        if quiz.get(
            "mode"
        ) == "direct":

            asyncio.create_task(
                send_direct_polls_task(
                    chat_id,
                    quiz_id,
                    context
                )
            )

            await query.message.reply_text(
                f"🚀 Direct quiz started in:\n"
                f"📢 {group.get('title', gid)}"
            )

            return

        # -------------------------------------------------
        # LIVE SESSION
        # -------------------------------------------------

        sid = (
            f"{quiz_id}_"
            f"{gid}_"
            f"{int(time.time())}"
        )

        questions = prepare_quiz_for_run(
            quiz
        )

        group_sessions[sid] = {
            "chat_id": chat_id,
            "quiz_id": quiz_id,
            "questions": questions,
            "index": 0,
            "players": {},
            "answered": {},
            "running": True,
            "timer": quiz["timer"],
            "mark_correct": quiz[
                "mark_correct"
            ],
            "mark_wrong": quiz[
                "mark_wrong"
            ],
            "question_start": time.time()
        }

        try:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🌿 *HORTICULTURE MASTER*\n\n"
                    f"📚 *{quiz['title']}*\n\n"
                    f"📝 Questions: "
                    f"{len(questions)}\n"
                    f"⏱️ Timer: "
                    f"{quiz['timer']} sec\n\n"
                    "🟢 Quiz Starting..."
                ),
                parse_mode="Markdown"
            )

        except Exception as e:

            print(
                "Group send error:",
                e
            )

            group_sessions.pop(
                sid,
                None
            )

            await query.message.reply_text(
                "❌ Bot group me message nahi bhej pa raha.\n"
                "Check karein bot group me present/admin hai."
            )

            return

        await query.message.reply_text(
            f"🚀 *Quiz Started!*\n\n"
            f"📢 {group.get('title', gid)}",
            parse_mode="Markdown"
        )

        asyncio.create_task(
            send_group_question(
                sid,
                context
            )
        )

        return

    # -----------------------------------------------------
    # QUIZ VIEW
    # -----------------------------------------------------

    if data.startswith(
        "quizview|"
    ):

        quiz_id = data.split(
            "|",
            1
        )[1]

        quiz = quizzes.get(
            quiz_id
        )

        if not quiz:

            await query.message.reply_text(
                "❌ Quiz not found."
            )

            return

        buttons = [
            [
                InlineKeyboardButton(
                    "📢 Share",
                    callback_data=f"share|{quiz_id}"
                )
            ]
        ]

        await query.message.reply_text(
            f"📚 *{quiz['title']}*\n\n"
            f"📝 Questions: "
            f"{len(quiz['questions'])}\n"
            f"⏱️ Timer: "
            f"{quiz.get('timer', 30)} sec\n"
            f"🔀 Shuffle: "
            f"{quiz.get('shuffle', 'none')}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                buttons
            )
        )

        return

    # -----------------------------------------------------
    # SHARE
    # -----------------------------------------------------

    if data.startswith(
        "share|"
    ):

        quiz_id = data.split(
            "|",
            1
        )[1]

        await show_group_selection(
            query,
            quiz_id
        )

        return


# =========================================================
# STOP
# =========================================================

async def stop_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    stopped = 0

    for sid, session in list(
        group_sessions.items()
    ):

        if session.get(
            "running"
        ):

            session["running"] = False

            task = session.get(
                "timer_task"
            )

            if task:

                try:
                    task.cancel()
                except Exception:
                    pass

            stopped += 1

    await update.effective_message.reply_text(
        f"🛑 Active quizzes stopped: {stopped}"
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context
):

    print(
        "BOT ERROR:",
        repr(context.error)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN missing."
        )

        print(
            'Termux: export BOT_TOKEN="YOUR_TOKEN"'
        )

        return

    load_all_data()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "register",
            register_group
        )
    )

    app.add_handler(
        CommandHandler(
            "history",
            show_history
        )
    )

    app.add_handler(
        CommandHandler(
            "rank",
            rank_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            stats_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "ban",
            ban_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "unban",
            unban_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "stop",
            stop_cmd
        )
    )

    # Poll answers
    app.add_handler(
        PollAnswerHandler(
            poll_answer_handler
        )
    )

    # Buttons
    app.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # Text + polls
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            message_handler
        )
    )

    app.add_error_handler(
        error_handler
    )

    # Auto save
    async def post_init(
        application
    ):

        application.create_task(
            auto_save_loop()
        )

    app.post_init = post_init

    print(
        "🌿 Horticulture Master Bot v6.9 started"
    )

    print(
        f"👥 Registered groups: "
        f"{len(saved_groups)}"
    )

    print(
        f"📚 Saved quizzes: "
        f"{len(quizzes)}"
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
