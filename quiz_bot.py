import json
import os
import random
import string
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from fpdf import FPDF

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Render Keep-Alive Server
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Quiz Bot is Running Live!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

TOKEN = "5096262921:AAHDRkHesbzcUs6BvDduK3IUEfnrFr_K0dE"
ADMIN_ID = 1141231956
DB_FILE = "quizzes.json"

DEFAULT_CREATOR = "Dr. Dev Kumar | JB STUDY POINT"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(CURRENT_DIR, "hindi.ttf")

def get_all_quizzes():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_all_quizzes(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving DB: {e}")

user_states = {}
creator_sessions = {}

def generate_quiz_id():
    return "GGN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

# PDF Generator using hindi.ttf
def generate_pdf_bytes(quiz_data):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if os.path.exists(FONT_PATH):
        pdf.add_font("Devanagari", "", FONT_PATH)
        font_name = "Devanagari"
    else:
        font_name = "Helvetica"

    title = str(quiz_data.get('title', 'Quiz Test'))
    creator = str(quiz_data.get('creator', DEFAULT_CREATOR))
    questions = quiz_data.get('questions', [])

    pdf.set_font(font_name, size=16)
    pdf.set_text_color(26, 35, 126)
    pdf.cell(0, 10, text=title, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(font_name, size=10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, text=f"Creator: {creator}  |  Questions: {len(questions)}  |  Timer: {quiz_data.get('timer', '20s')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    opt_labels = ["(A)", "(B)", "(C)", "(D)", "(E)", "(F)", "(G)", "(H)"]

    for i, q in enumerate(questions, 1):
        pdf.set_font(font_name, size=11)
        pdf.set_text_color(0, 0, 0)
        q_text = f"Q{i}. {q.get('question', '')}"
        pdf.multi_cell(0, 6, text=q_text, new_x="LMARGIN", new_y="NEXT")

        options = q.get('options', [])
        pdf.set_font(font_name, size=10)
        pdf.set_text_color(40, 40, 40)
        for o_idx, opt in enumerate(options):
            lbl = opt_labels[o_idx] if o_idx < len(opt_labels) else f"({o_idx+1})"
            pdf.multi_cell(0, 5, text=f"   {lbl} {opt}", new_x="LMARGIN", new_y="NEXT")

        correct_idx = q.get('correct_id', 0)
        corr_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        correct_text = options[correct_idx] if correct_idx < len(options) else ""

        pdf.set_font(font_name, size=10)
        pdf.set_text_color(46, 125, 50)
        pdf.multi_cell(0, 6, text=f"   Correct Answer: {corr_lbl} {correct_text}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

async def post_init(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("create", "Create a new quiz"),
        BotCommand("done", "Complete quiz creation"),
        BotCommand("myquizzes", "View created quizzes"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("PLAY_"):
        quiz_id = args[0].replace("PLAY_", "")
        await start_quiz_session(update.effective_chat.id, user.id, quiz_id, context)
        return

    text = (
        f"🇮🇳 *नमस्ते {user.first_name}!*\n\n"
        "• नया क्विज़: `/create क्विज़ का नाम`\n"
        "• प्रश्न फ़ॉरवर्ड करने के बाद: `/done`\n"
        "• सभी क्विज़ देखें: `/myquizzes`\n"
        "• सीधे PDF पाएँ: `/pdf QUIZ_ID`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ केवल एडमिन ही नया क्विज़ बना सकते हैं।")
        return

    title = " ".join(context.args).strip() if context.args else "इतिहास टेस्ट"
    q_id = generate_quiz_id()

    creator_sessions[user_id] = {
        "step": "COLLECTING_POLLS",
        "title": title,
        "creator": DEFAULT_CREATOR,
        "type": "free",
        "promo": "None",
        "timer": "20s",
        "questions": [],
        "id": q_id
    }

    msg = (
        f"✅ नया क्विज़ सत्र शुरू हुआ: *'{title}'*\n"
        f"🆔 ID: `{q_id}`\n\n"
        "👉 अब **@QuizBot** से पोल फ़ॉरवर्ड करना शुरू करें।\n"
        "सारे फ़ॉरवर्ड हो जाने के बाद अंत में **/done** भेजें।"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_incoming_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions or creator_sessions[user_id]["step"] != "COLLECTING_POLLS":
        q_id = generate_quiz_id()
        creator_sessions[user_id] = {
            "step": "COLLECTING_POLLS",
            "title": "इतिहास टेस्ट",
            "creator": DEFAULT_CREATOR,
            "type": "free",
            "promo": "None",
            "timer": "20s",
            "questions": [],
            "id": q_id
        }

    poll = update.message.poll
    if not poll:
        return

    options = [opt.text for opt in poll.options]
    correct_id = poll.correct_option_id if poll.correct_option_id is not None else 0

    session = creator_sessions[user_id]
    session["questions"].append({
        "question": poll.question,
        "options": options,
        "correct_id": correct_id
    })

    count = len(session["questions"])
    status_text = f"✅ {count} question(s) saved from polls! ➡️\nSend more or /done"

    if count == 1 or count % 5 == 0:
        await update.message.reply_text(status_text)

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions or not creator_sessions[user_id]["questions"]:
        await update.message.reply_text("❌ कोई प्रश्न नहीं मिला। पहले पोल फ़ॉरवर्ड करें।")
        return

    creator_sessions[user_id]["step"] = "ASK_SECTION"
    await update.message.reply_text("📁 Section quiz? yes/no")

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in creator_sessions:
        return

    session = creator_sessions[user_id]
    step = session.get("step")

    if step == "ASK_SECTION":
        session["step"] = "ASK_PROMO"
        await update.message.reply_text("📣 Send your promo message (shown periodically). Send 'skip' or 'no' to leave empty.")
        return

    elif step == "ASK_PROMO":
        if text.lower() in ["no", "skip", "none"]:
            session["promo"] = "None"
        else:
            session["promo"] = text

        session["step"] = "ASK_TYPE"
        await update.message.reply_text("🏷 Type (free/paid)")
        return

    elif step == "ASK_TYPE":
        if "paid" in text.lower():
            session["type"] = "paid"
        else:
            session["type"] = "free"

        q_id = session["id"]
        all_q = get_all_quizzes()
        all_q[q_id] = session
        save_all_quizzes(all_q)

        total_q = len(session["questions"])
        del creator_sessions[user_id]

        card_text = (
            f"🎉 *Quiz Created!*\n\n"
            f"🏷 *Name:* {session['title']}\n"
            f"❓ *Questions:* {total_q}\n"
            f"⏱ *Timer:* {session['timer']}\n"
            f"🆔 *ID:* `{q_id}`\n"
            f"🏷 *Type:* {session['type']}\n"
            f"📣 *Promo:* {session['promo']}\n"
            f"👤 *Creator:* {session['creator']}"
        )

        bot_info = await context.bot.get_me()
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=PLAY_{q_id}&text={session['title']}"
        add_group_url = f"https://t.me/{bot_info.username}?startgroup=PLAY_{q_id}"

        keyboard = [
            [InlineKeyboardButton("▶️ Start", callback_data=f"play_{q_id}")],
            [InlineKeyboardButton("📄 Download PDF", callback_data=f"pdf_{q_id}")],
            [InlineKeyboardButton("➕ Add to Group", url=add_group_url)],
            [InlineKeyboardButton("📩 Share", url=share_url)],
            [
                InlineKeyboardButton("🎮 Play (Practice)", callback_data=f"play_{q_id}"),
                InlineKeyboardButton("🎯 Play (Exam)", callback_data=f"play_{q_id}")
            ]
        ]

        await update.message.reply_text(card_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    all_q = get_all_quizzes()
    if not all_q:
        await update.message.reply_text("कोई क्विज़ मौजूद नहीं है।")
        return

    lines = [f"🧩 *Your Quizzes*\nTotal: {len(all_q)}\n"]
    for idx, (q_id, q_data) in enumerate(all_q.items(), 1):
        lines.append(
            f"*{idx}. {q_data.get('title', 'Quiz')}*\n"
            f"🆔 ID: `{q_id}`\n"
            f"❓ Questions: {len(q_data.get('questions', []))}\n"
            f"🎯 Play: `/play {q_id}`\n"
            f"📄 PDF: `/pdf {q_id}`\n"
            "--------------------------------"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया क्विज़ आईडी लिखें। उदाहरण: `/pdf GGN80C50L`")
        return
    quiz_id = context.args[0].strip().upper()
    await send_quiz_pdf(update.effective_chat.id, quiz_id, context)

async def send_quiz_pdf(chat_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    if quiz_id not in all_q or not all_q[quiz_id].get("questions"):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` में कोई प्रश्न नहीं मिला।")
        return

    await context.bot.send_message(chat_id=chat_id, text="⏳ हिंदी पीडीएफ तैयार की जा रही है...")
    try:
        pdf_buffer = generate_pdf_bytes(all_q[quiz_id])
        safe_filename = f"{all_q[quiz_id].get('title', 'Quiz')}.pdf".replace(" ", "_")

        await context.bot.send_document(
            chat_id=chat_id,
            document=pdf_buffer,
            filename=safe_filename,
            caption=f"📄 *{all_q[quiz_id]['title']}*\n👤 Creator: {all_q[quiz_id].get('creator', DEFAULT_CREATOR)}\n🆔 ID: `{quiz_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ PDF त्रुटि: {str(e)}")

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया क्विज़ आईडी लिखें।")
        return
    quiz_id = context.args[0].strip().upper()
    await start_quiz_session(update.effective_chat.id, update.effective_user.id, quiz_id, context)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("play_"):
        quiz_id = data.replace("play_", "")
        await start_quiz_session(query.message.chat_id, query.from_user.id, quiz_id, context)
    elif data.startswith("pdf_"):
        quiz_id = data.replace("pdf_", "")
        await send_quiz_pdf(query.message.chat_id, quiz_id, context)

async def start_quiz_session(chat_id, user_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    if quiz_id not in all_q or not all_q[quiz_id].get("questions"):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` में कोई प्रश्न नहीं हैं।")
        return

    user_states[user_id] = {
        "quiz_id": quiz_id,
        "index": 0,
        "score": 0,
        "chat_id": chat_id
    }
    await send_quiz_poll(user_id, context)

async def send_quiz_poll(user_id, context: ContextTypes.DEFAULT_TYPE):
    state = user_states[user_id]
    all_q = get_all_quizzes()
    quiz = all_q[state["quiz_id"]]
    idx = state["index"]

    if idx < len(quiz["questions"]):
        q = quiz["questions"][idx]
        msg = await context.bot.send_poll(
            chat_id=state["chat_id"],
            question=q["question"],
            options=q["options"],
            type="quiz",
            correct_option_id=q["correct_id"],
            is_anonymous=False,
            explanation=""
        )
        context.bot_data[msg.poll.id] = (user_id, q["correct_id"])
    else:
        score = state["score"]
        total = len(quiz["questions"])
        await context.bot.send_message(
            chat_id=state["chat_id"],
            text=f"🏁 *टेस्ट समाप्त!*\n\n📝 क्विज़: *{quiz['title']}*\n👤 क्रिएटर: *{quiz.get('creator', DEFAULT_CREATOR)}*\n🏆 आपका स्कोर: *{score} / {total}*\n\nधन्यवाद!",
            parse_mode="Markdown"
        )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p_ans = update.poll_answer
    poll_id = p_ans.poll_id

    if poll_id in context.bot_data:
        user_id, correct_id = context.bot_data[poll_id]
        if user_id in user_states:
            selected = p_ans.option_ids[0]
            if selected == correct_id:
                user_states[user_id]["score"] += 1

            user_states[user_id]["index"] += 1
            await send_quiz_poll(user_id, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("myquizzes", my_quizzes))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("pdf", pdf_command))
    app.add_handler(MessageHandler(filters.POLL, handle_incoming_poll))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    app.run_polling()

if __name__ == "__main__":
    main()
    
