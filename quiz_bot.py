import asyncio
import io
import json
import os
import random
import re
import smtplib
import string
import threading
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from PIL import Image, ImageDraw, ImageFont
import firebase_admin
from firebase_admin import credentials, firestore

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    MessageHandler,
    filters,
    ContextTypes,
)


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1141231956"))
DB_FILE = os.environ.get("DB_FILE", "quizzes.json")
DEFAULT_CREATOR = "JB STUDY POINT"

# Gmail
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

# Firebase Service Account File (Path set via Environment Variable or local default)
FIREBASE_CRED_PATH = os.environ.get("FIREBASE_CRED_PATH", "firebase_credentials.json")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(CURRENT_DIR, "hindi.ttf")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is missing.")


# ============================================================
# FIREBASE INITIALIZATION
# ============================================================

db_firestore = None

if os.path.exists(FIREBASE_CRED_PATH):
    try:
        cred = credentials.Certificate(FIREBASE_CRED_PATH)
        firebase_admin.initialize_app(cred)
        db_firestore = firestore.client()
        print("🔥 Firebase Admin SDK Successfully Initialized!")
    except Exception as e:
        print(f"⚠️ Firebase Initialization Error: {e}")
else:
    print(f"⚠️ Service account file '{FIREBASE_CRED_PATH}' not found. Falling back to local JSON database.")


# ============================================================
# RUNTIME DATA
# ============================================================

creator_sessions = {}
pending_setups = {}
active_group_quizzes = {}
poll_mapping = {}  # {poll_id: {"chat_id": int, "q_index": int, "correct_id": int}}


# ============================================================
# DATABASE FUNCTIONS (LOCAL + FIREBASE SYNC)
# ============================================================

def get_all_quizzes():
    # Firebase Priority
    if db_firestore:
        try:
            docs = db_firestore.collection("quizzes").stream()
            quizzes = {doc.id: doc.to_dict() for doc in docs}
            if quizzes:
                return quizzes
        except Exception as e:
            print(f"Firestore Read Error: {e}")

    # Fallback to Local JSON
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Database read error: {e}")
        return {}


def save_all_quizzes(data):
    # Local JSON Save
    temp_file = DB_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DB_FILE)
    except OSError as e:
        print(f"Database save error: {e}")

    # Sync with Firebase Cloud Firestore
    if db_firestore:
        try:
            for quiz_id, quiz_data in data.items():
                db_firestore.collection("quizzes").document(quiz_id).set(quiz_data)
            print("☁️ Firebase Firestore Sync Completed.")
        except Exception as e:
            print(f"Firestore Save Error: {e}")


def save_quiz_result_firebase(quiz_id, result_data):
    """Save student attempts and results to Firestore"""
    if db_firestore:
        try:
            db_firestore.collection("results").add({
                "quiz_id": quiz_id,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "scores": result_data
            })
            print(f"📊 Results saved to Firestore for Quiz: {quiz_id}")
        except Exception as e:
            print(f"Firestore Result Save Error: {e}")


# ============================================================
# UTILS & HELPERS
# ============================================================

def generate_quiz_id():
    return "GGN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def clean_question_text(raw_text):
    if not raw_text:
        return ""
    text = str(raw_text)
    patterns = [
        r"\[\s*\d+\s*/\s*\d+\s*\]", r"⏱\s*\d+s?", r"\d+s\s*\|",
        r"\[\s*\d+s\s*\]", r"\[.*?s.*?\]", r"^\s*\[\s*\d+\s*/\s*\d+\s*\]\s*",
        r"^\s*(?:Q|q|प्रश्न)?\s*\d+[\.\)\-:]\s*", r"^\s*\[\s*\d+\s*\]\s*", r"^\s*\(\s*\d+\s*\)\s*"
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return text.strip()


def validate_quiz(quiz):
    questions = quiz.get("questions", [])
    if not questions:
        return False, "कम-से-कम 1 प्रश्न होना चाहिए।"

    for number, question in enumerate(questions, 1):
        question_text = question.get("question", "").strip()
        options = question.get("options", [])
        correct_id = question.get("correct_id")

        if not question_text:
            return False, f"प्रश्न {number} खाली है।"
        if not isinstance(options, list) or not 2 <= len(options) <= 10:
            return False, f"प्रश्न {number} में 2 से 10 options होने चाहिए।"
        if not isinstance(correct_id, int) or correct_id < 0 or correct_id >= len(options):
            return False, f"प्रश्न {number} का correct option invalid है।"

    return True, ""


# ============================================================
# GMAIL BACKUP
# ============================================================

def send_quiz_email_backup(quiz_title, quiz_id, quiz_dict):
    if not GMAIL_USER or not GMAIL_PASS:
        print("Email backup skipped. GMAIL credentials missing.")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = GMAIL_USER
        msg["Subject"] = f"JB STUDY POINT Backup: {quiz_title} ({quiz_id})"

        body = f"JB STUDY POINT\n\nQuiz Backup\n\nQuiz Title: {quiz_title}\nQuiz ID: {quiz_id}\n"
        msg.attach(MIMEText(body, "plain", "utf-8"))

        json_data = json.dumps(quiz_dict, ensure_ascii=False, indent=2).encode("utf-8")
        attachment = MIMEApplication(json_data, _subtype="json")
        attachment.add_header("Content-Disposition", "attachment", filename=f"{quiz_id}.json")
        msg.attach(attachment)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)
        print(f"Email backup sent successfully: {quiz_id}")
    except Exception as e:
        print(f"Email backup error: {e}")


# ============================================================
# FONT & PDF GENERATION
# ============================================================

def get_font(size):
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception as e:
            print(f"Font loading error: {e}")
    return ImageFont.load_default()


def generate_pdf_bytes(quiz_data):
    PAGE_W, PAGE_H = 2480, 3508
    MARGIN_X, COL_GAP = 140, 90
    COL_W = (PAGE_W - (2 * MARGIN_X) - COL_GAP) // 2

    f_sub, f_title = get_font(24), get_font(40)
    f_meta, f_instr = get_font(22), get_font(20)
    f_q, f_opt = get_font(26), get_font(24)
    f_ans_title, f_key = get_font(50), get_font(28)

    title = str(quiz_data.get("title", "MOCK TEST"))
    questions = quiz_data.get("questions", [])

    def wrap_text(text, font, max_width, draw):
        words = str(text).split()
        if not words: return [""]
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = candidate
            else:
                if current: lines.append(current)
                current = word
        if current: lines.append(current)
        return lines

    dummy_img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
    dummy_draw = ImageDraw.Draw(dummy_img)
    option_labels = ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)", "(g)", "(h)", "(i)", "(j)"]

    question_blocks, answer_keys = [], []

    for number, question in enumerate(questions, 1):
        clean_q = clean_question_text(question.get("question", ""))
        q_lines = wrap_text(f"{number}. {clean_q}", f_q, COL_W, dummy_draw)
        opt_items = []

        for idx, option in enumerate(question.get("options", [])):
            lbl = option_labels[idx] if idx < len(option_labels) else f"({idx + 1})"
            clean_opt = clean_question_text(option)
            opt_lines = wrap_text(f"{lbl} {clean_opt}", f_opt, COL_W - 30, dummy_draw)
            opt_items.append(opt_lines)

        c_id = int(question.get("correct_id", 0))
        c_lbl = option_labels[c_id] if c_id < len(option_labels) else f"({c_id + 1})"
        answer_keys.append((str(number), c_lbl))

        tot_opt_lines = sum(len(l) for l in opt_items)
        block_h = len(q_lines) * 40 + tot_opt_lines * 34 + 55
        question_blocks.append({"q_lines": q_lines, "opt_items": opt_items, "block_h": block_h})

    def create_page(later=False):
        img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
        draw = ImageDraw.Draw(img)
        draw.rectangle([80, 80, PAGE_W - 80, PAGE_H - 80], outline="#8B0000", width=6)
        draw.rectangle([95, 95, PAGE_W - 95, PAGE_H - 95], outline="#DAA520", width=3)
        header_text = f"JB STUDY POINT | {title}" if later else "JB STUDY POINT YOUTUBE CHANNEL"
        draw.text((120, 105), header_text, font=f_sub, fill="#8B0000")
        draw.text((PAGE_W - 520, 105), "Mob: 8218345167", font=f_sub, fill="#000000")
        draw.line([(PAGE_W // 2, 140), (PAGE_W // 2, PAGE_H - 140)], fill="#B0C4DE", width=3)
        return img, draw

    current_img, current_draw = create_page(False)
    current_col, current_y = 0, 450
    page_limit = PAGE_H - 140

    current_draw.rectangle([120, 140, PAGE_W - 120, 215], fill="#8B0000")
    t_box = current_draw.textbbox((0, 0), title, font=f_title)
    current_draw.text(((PAGE_W - (t_box[2] - t_box[0])) // 2, 155), title, font=f_title, fill="#FFFFFF")

    pages = []
    for block in question_blocks:
        if current_y + block["block_h"] > page_limit:
            if current_col == 0:
                current_col, current_y = 1, 160
            else:
                pages.append(current_img)
                current_img, current_draw = create_page(True)
                current_col, current_y = 0, 160

        col_x = MARGIN_X if current_col == 0 else MARGIN_X + COL_W + COL_GAP
        q_box_h = len(block["q_lines"]) * 40 + 10
        current_draw.rectangle([col_x - 10, current_y - 4, col_x + COL_W + 10, current_y + q_box_h], fill="#EAE6FF", outline="#7B68EE", width=2)

        for line in block["q_lines"]:
            current_draw.text((col_x, current_y), line, font=f_q, fill="#000080")
            current_y += 40
        current_y += 6

        for opt_lines in block["opt_items"]:
            for line in opt_lines:
                current_draw.text((col_x + 15, current_y), line, font=f_opt, fill="#111111")
                current_y += 34
        current_y += 24

    pages.append(current_img)

    # Answer Key Page
    ans_img, ans_draw = create_page(True)
    ans_draw.text((800, 160), "ANSWER KEY / उत्तर तालिका", font=f_ans_title, fill="#8B0000")
    ans_x, ans_y = MARGIN_X + 40, 310
    col_w = (PAGE_W - (2 * MARGIN_X) - 80) // 5

    for idx, (q_num, ans_lbl) in enumerate(answer_keys):
        c, r = idx % 5, idx // 5
        x, y = ans_x + c * col_w, ans_y + r * 70
        ans_draw.rectangle([x, y, x + col_w - 25, y + 55], outline="#8B0000", fill="#FFFFFF", width=2)
        ans_draw.text((x + 12, y + 10), f"Q.{q_num}", font=f_key, fill="#000000")
        ans_draw.text((x + col_w - 80, y + 10), ans_lbl, font=f_key, fill="#8B0000")

    pages.append(ans_img)

    pdf_io = io.BytesIO()
    pdf_io.name = f"{title}_Exam_Booklet.pdf"
    pages[0].save(pdf_io, format="PDF", save_all=True, append_images=pages[1:], resolution=300.0)
    pdf_io.seek(0)
    return pdf_io


# ============================================================
# BOT COMMANDS
# ============================================================

async def post_init(application):
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("create", "Create quiz"),
        BotCommand("done", "Finish quiz creation"),
        BotCommand("cancel", "Cancel quiz creation"),
        BotCommand("myquizzes", "View quizzes"),
        BotCommand("play", "Play quiz"),
        BotCommand("pdf", "Download PDF"),
        BotCommand("backup", "Email backup"),
    ]
    await application.bot.set_my_commands(commands)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].upper().startswith("PLAY_"):
        quiz_id = args[0][5:].strip().upper()
        await prompt_quiz_settings(update.effective_chat.id, quiz_id, user.id, context)
        return

    await update.message.reply_text(
        f"🇮🇳 नमस्ते {user.first_name}!\n\n"
        "🎯 JB STUDY POINT Quiz Bot (Phase 3 Firebase Active)\n\n"
        "📝 नया टेस्ट: /create\n"
        "📚 टेस्ट सूची: /myquizzes\n"
        "▶️ टेस्ट खेलें: /play QUIZ_ID\n"
        "📄 PDF: /pdf QUIZ_ID\n"
        "📧 Backup: /backup QUIZ_ID\n"
        "🛑 Cancel: /cancel"
    )


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ यह command केवल admin के लिए है।")
        return

    if context.args:
        title = " ".join(context.args).strip()
        quiz_id = generate_quiz_id()
        creator_sessions[user_id] = {
            "title": title, "questions": [], "id": quiz_id, "step": "POLLS", "creator": DEFAULT_CREATOR
        }
        await update.message.reply_text(
            f"✅ Test शुरू हो गया।\n\n📝 Title: {title}\n🆔 ID: {quiz_id}\n\n"
            "अब Telegram Quiz Polls forward करें।\nसभी questions के बाद /done भेजें।"
        )
        return

    creator_sessions[user_id] = {"step": "TITLE"}
    await update.message.reply_text("📝 कृपया Test का नाम भेजें:")


async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = creator_sessions.get(user_id)

    if not session or session.get("step") != "TITLE":
        return

    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("❌ Test title खाली नहीं हो सकता।")
        return

    quiz_id = generate_quiz_id()
    creator_sessions[user_id] = {
        "title": title, "questions": [], "id": quiz_id, "step": "POLLS", "creator": DEFAULT_CREATOR
    }
    await update.message.reply_text(
        f"✅ Test तैयार है।\n\n📝 {title}\n🆔 {quiz_id}\n\n"
        "अब Quiz Polls forward करें।\nसमाप्त होने पर /done भेजें।"
    )


async def handle_incoming_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = creator_sessions.get(user_id)

    if not session or session.get("step") != "POLLS":
        return

    poll = update.message.poll
    if not poll or poll.type != "quiz":
        await update.message.reply_text("❌ केवल Quiz Poll स्वीकार किया जाएगा।")
        return

    if poll.correct_option_id is None:
        await update.message.reply_text("❌ इस poll में correct answer नहीं मिला।")
        return

    options = [opt.text for opt in poll.options]
    question = clean_question_text(poll.question)

    session["questions"].append({
        "question": question, "options": options, "correct_id": int(poll.correct_option_id)
    })
    await update.message.reply_text(f"✅ Question saved: {len(session['questions'])}")


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    session = creator_sessions.get(user_id)
    if not session or session.get("step") != "POLLS":
        await update.message.reply_text("❌ Quiz creation अभी active नहीं है।")
        return

    valid, error = validate_quiz(session)
    if not valid:
        await update.message.reply_text(f"❌ {error}")
        return

    quiz_id = session["id"]
    all_quizzes = get_all_quizzes()
    all_quizzes[quiz_id] = session
    save_all_quizzes(all_quizzes)

    threading.Thread(target=send_quiz_email_backup, args=(session["title"], quiz_id, session.copy()), daemon=True).start()
    del creator_sessions[user_id]

    keyboard = [
        [InlineKeyboardButton("▶️ Start Quiz", callback_data=f"init_{quiz_id}")],
        [InlineKeyboardButton("📄 Download PDF", callback_data=f"pdf_{quiz_id}")]
    ]
    await update.message.reply_text(
        f"🎉 TEST SUCCESSFULLY CREATED!\n\n📝 {session['title']}\n🆔 {quiz_id}\n"
        f"❓ Questions: {len(session['questions'])}\n\nअब आप Quiz Start कर सकते हैं।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in creator_sessions:
        del creator_sessions[user_id]
        await update.message.reply_text("🛑 Quiz creation cancel कर दिया गया।")


async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    quizzes = get_all_quizzes()
    if not quizzes:
        await update.message.reply_text("📭 कोई quiz मौजूद नहीं है।")
        return

    lines = ["📚 JB STUDY POINT QUIZZES\n"]
    for q_id, q in quizzes.items():
        lines.append(f"📝 {q.get('title')}\n🆔 {q_id}\n❓ Qs: {len(q.get('questions', []))}\n▶️ /play {q_id}\n📄 /pdf {q_id}\n")
    await update.message.reply_text("\n".join(lines))


# ============================================================
# QUIZ EXECUTION & POLL ANSWER HANDLER
# ============================================================

async def prompt_quiz_settings(chat_id, quiz_id, host_id, context):
    all_quizzes = get_all_quizzes()
    quiz = all_quizzes.get(quiz_id)

    if not quiz:
        await context.bot.send_message(chat_id=chat_id, text="❌ Quiz नहीं मिला।")
        return

    if chat_id in active_group_quizzes:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ इस chat में एक quiz पहले से चल रहा है।")
        return

    pending_setups[chat_id] = {"quiz_id": quiz_id, "host_id": host_id, "timer": 20, "negative": 0.0}

    keyboard = [
        [InlineKeyboardButton("⏱ 15 सेकंड", callback_data=f"TIME:{chat_id}:15"),
         InlineKeyboardButton("⏱ 20 सेकंड", callback_data=f"TIME:{chat_id}:20")],
        [InlineKeyboardButton("⏱ 25 सेकंड", callback_data=f"TIME:{chat_id}:25"),
         InlineKeyboardButton("⏱ 30 सेकंड", callback_data=f"TIME:{chat_id}:30")]
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚙️ Quiz Settings\n\n📝 {quiz.get('title')}\n❓ Questions: {len(quiz.get('questions', []))}\n\n⏱ Timer चुनें:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("init_"):
        quiz_id = data.split("_")[1]
        await prompt_quiz_settings(query.message.chat_id, quiz_id, query.from_user.id, context)

    elif data.startswith("pdf_"):
        quiz_id = data.split("_")[1]
        quiz = get_all_quizzes().get(quiz_id)
        if quiz:
            pdf_bytes = generate_pdf_bytes(quiz)
            await query.message.reply_document(document=pdf_bytes, filename=f"{quiz_id}.pdf")

    elif data.startswith("TIME:"):
        _, chat_id_str, time_str = data.split(":")
        c_id = int(chat_id_str)
        if c_id in pending_setups:
            pending_setups[c_id]["timer"] = int(time_str)
            setup = pending_setups.pop(c_id)
            asyncio.create_task(run_group_quiz(c_id, setup["quiz_id"], setup["timer"], context))


async def run_group_quiz(chat_id, quiz_id, timer_sec, context):
    quiz = get_all_quizzes().get(quiz_id)
    if not quiz: return

    active_group_quizzes[chat_id] = {"scores": {}, "quiz_id": quiz_id}
    await context.bot.send_message(chat_id=chat_id, text=f"🚀 Quiz **{quiz['title']}** शुरू हो रहा है!\nसमय प्रति प्रश्न: {timer_sec} सेकंड।")

    for idx, q in enumerate(quiz["questions"]):
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"[{idx+1}/{len(quiz['questions'])}] {q['question']}",
            options=q["options"],
            type="quiz",
            correct_option_id=q["correct_id"],
            is_anonymous=False,
            open_period=timer_sec
        )
        poll_mapping[msg.poll.id] = {"chat_id": chat_id, "correct_id": q["correct_id"]}
        await asyncio.sleep(timer_sec + 2)

    # Leaderboard Processing
    scores = active_group_quizzes[chat_id]["scores"]
    del active_group_quizzes[chat_id]

    # Save to Firebase
    save_quiz_result_firebase(quiz_id, scores)

    if not scores:
        await context.bot.send_message(chat_id=chat_id, text="🏆 Quiz समाप्त! किसी छात्र ने उत्तर नहीं दिया।")
        return

    sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
    leaderboard = [f"🏆 **LEADERBOARD: {quiz['title']}**\n"]

    for rank, (u_id, data) in enumerate(sorted_scores, 1):
        leaderboard.append(f"{rank}. {data['name']} - **{data['score']} अंक**")

    await context.bot.send_message(chat_id=chat_id, text="\n".join(leaderboard), parse_mode="Markdown")


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id

    if poll_id not in poll_mapping:
        return

    p_data = poll_mapping[poll_id]
    chat_id = p_data["chat_id"]
    correct_id = p_data["correct_id"]

    if chat_id not in active_group_quizzes:
        return

    user = answer.user
    selected_option = answer.option_ids[0] if answer.option_ids else None

    scores = active_group_quizzes[chat_id]["scores"]
    if user.id not in scores:
        scores[user.id] = {"name": user.full_name, "score": 0}

    if selected_option == correct_id:
        scores[user.id]["score"] += 1


async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया ID दर्ज करें: /pdf QUIZ_ID")
        return
    q_id = context.args[0].upper().strip()
    quiz = get_all_quizzes().get(q_id)
    if not quiz:
        await update.message.reply_text("❌ Quiz नहीं मिला।")
        return
    pdf_bytes = generate_pdf_bytes(quiz)
    await update.message.reply_document(document=pdf_bytes, filename=f"{q_id}.pdf")


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया ID दर्ज करें: /play QUIZ_ID")
        return
    q_id = context.args[0].upper().strip()
    await prompt_quiz_settings(update.effective_chat.id, q_id, update.effective_user.id, context)


# ============================================================
# MAIN APPLICATION SETUP
# ============================================================

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("myquizzes", my_quizzes))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("pdf", pdf_command))

    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.add_handler(MessageHandler(filters.POLL, handle_incoming_poll))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("🤖 JB STUDY POINT Phase 3 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
