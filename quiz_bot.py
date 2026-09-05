import json
import os
import random
import string
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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

def load_quizzes():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_quizzes(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

QUIZZES = load_quizzes()
user_states = {}
active_creators = {}  # {user_id: {"title": str, "questions": list, "id": str}}

def generate_quiz_id():
    return "GGN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def generate_pdf_bytes(quiz_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1a237e"),
        alignment=1,
        spaceAfter=15
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.dimgrey,
        alignment=1,
        spaceAfter=20
    )
    q_style = ParagraphStyle(
        'QStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=15,
        textColor=colors.black,
        spaceBefore=10,
        spaceAfter=5
    )
    opt_style = ParagraphStyle(
        'OptStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#333333"),
        leftIndent=15,
        spaceAfter=3
    )
    ans_style = ParagraphStyle(
        'AnsStyle',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2e7d32"),
        leftIndent=15,
        spaceAfter=8
    )

    story = []
    story.append(Paragraph(f"<b>{quiz_data['title']}</b>", title_style))
    story.append(Paragraph(f"Created by: {quiz_data.get('creator', 'Admin')} | Total Questions: {len(quiz_data['questions'])}", meta_style))
    story.append(Spacer(1, 10))

    for i, q in enumerate(quiz_data['questions'], 1):
        story.append(Paragraph(f"<b>Q{i}. {q['question']}</b>", q_style))
        opt_labels = ["(A)", "(B)", "(C)", "(D)", "(E)"]
        for o_idx, opt in enumerate(q['options']):
            lbl = opt_labels[o_idx] if o_idx < len(opt_labels) else f"({o_idx+1})"
            story.append(Paragraph(f"{lbl} {opt}", opt_style))
        
        correct_idx = q.get('correct_id', 0)
        corr_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        correct_text = q['options'][correct_idx] if correct_idx < len(q['options']) else ""
        story.append(Paragraph(f"<b>Correct Answer:</b> {corr_lbl} {correct_text}", ans_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

async def post_init(application):
    commands = [
        BotCommand("start", "Start the bot / check status"),
        BotCommand("create", "Create a new quiz"),
        BotCommand("done", "Finish quiz and get card/PDF"),
        BotCommand("myquizzes", "View all quizzes"),
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
        "• नया क्विज़ बनाने के लिए: `/create क्विज़ का नाम`\n"
        "  *(उदाहरण: `/create इतिहास टेस्ट-1`)*\n"
        "• सारे प्रश्न फ़ॉरवर्ड करने के बाद: `/done`\n"
        "• सभी क्विज़ देखने के लिए: `/myquizzes`\n"
        "• सीधे PDF डाउनलोड करने के लिए: `/pdf QUIZ_ID`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ केवल एडमिन ही नया क्विज़ बना सकते हैं।")
        return

    title = " ".join(context.args).strip() if context.args else "इतिहास टेस्ट"
    q_id = generate_quiz_id()
    active_creators[user_id] = {
        "title": title,
        "creator": update.effective_user.first_name,
        "type": "Free",
        "plays": 0,
        "questions": [],
        "id": q_id
    }

    msg = (
        f"✅ नया क्विज़ सत्र शुरू हुआ: *'{title}'*\n"
        f"🆔 ID: `{q_id}`\n\n"
        "👉 अब **@QuizBot** से जितने चाहे पोल सीधे फ़ॉरवर्ड करें।\n"
        "सारे फ़ॉरवर्ड करने के बाद अंत में **/done** भेजें।"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_incoming_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in active_creators:
        # अगर बिना /create के भी पोल फ़ॉरवर्ड किया गया तो ऑटो-स्टार्ट कर देगा
        q_id = generate_quiz_id()
        active_creators[user_id] = {
            "title": "History Quiz",
            "creator": update.effective_user.first_name,
            "type": "Free",
            "plays": 0,
            "questions": [],
            "id": q_id
        }

    poll = update.message.poll
    if not poll:
        return

    options = [opt.text for opt in poll.options]
    correct_id = poll.correct_option_id if poll.correct_option_id is not None else 0

    active_creators[user_id]["questions"].append({
        "question": poll.question,
        "options": options,
        "correct_id": correct_id
    })

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in active_creators or not active_creators[user_id]["questions"]:
        await update.message.reply_text("❌ कोई प्रश्न नहीं मिला। कृपया पहले पोल फ़ॉरवर्ड करें या `/create नाम` भेजें।", parse_mode="Markdown")
        return

    quiz_data = active_creators[user_id]
    q_id = quiz_data["id"]
    QUIZZES[q_id] = quiz_data
    save_quizzes(QUIZZES)
    del active_creators[user_id]

    total_q = len(quiz_data["questions"])
    card_text = (
        f"🇮🇳 *Advance Quiz Bot*\n"
        f"🆔 **ID:** `{q_id}`\n"
        f"🏷 **Type:** Free\n"
        f"📢 **Promo:** None\n"
        f"👤 **Creator:** {quiz_data['creator']}\n"
        f"📚 **Total Questions:** {total_q}\n"
        f"📝 **Name:** {quiz_data['title']}"
    )

    bot_info = await context.bot.get_me()
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=PLAY_{q_id}&text={quiz_data['title']}"
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

    if not QUIZZES:
        await update.message.reply_text("कोई क्विज़ मौजूद नहीं है। `/create नाम` दबाकर नया बनाएं।", parse_mode="Markdown")
        return

    lines = [f"🧩 *Your Quizzes (Page 1)*\nTotal: {len(QUIZZES)}\n"]
    for idx, (q_id, q_data) in enumerate(QUIZZES.items(), 1):
        lines.append(
            f"*{idx}. {q_data['title']}*\n"
            f"🆔 ID: `{q_id}`\n"
            f"📚 Questions: {len(q_data['questions'])}\n"
            f"🎯 Play: `/play {q_id}`\n"
            f"📄 PDF: `/pdf {q_id}`\n"
            "--------------------------------"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया क्विज़ आईडी भी लिखें। उदाहरण: `/pdf GGN12345`", parse_mode="Markdown")
        return
    quiz_id = context.args[0].strip().upper()
    await send_quiz_pdf(update.effective_chat.id, quiz_id, context)

async def send_quiz_pdf(chat_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    if quiz_id not in QUIZZES or not QUIZZES[quiz_id]["questions"]:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` में कोई प्रश्न नहीं मिला।", parse_mode="Markdown")
        return

    await context.bot.send_message(chat_id=chat_id, text="⏳ पीडीएफ तैयार की जा रही है...")
    pdf_buffer = generate_pdf_bytes(QUIZZES[quiz_id])
    safe_filename = f"{QUIZZES[quiz_id]['title'].replace(' ', '_')}.pdf"
    
    await context.bot.send_document(
        chat_id=chat_id,
        document=pdf_buffer,
        filename=safe_filename,
        caption=f"📄 *{QUIZZES[quiz_id]['title']}*\n🆔 ID: `{quiz_id}`",
        parse_mode="Markdown"
    )

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया क्विज़ आईडी लिखें। उदाहरण: `/play GGN12345`", parse_mode="Markdown")
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
    if quiz_id not in QUIZZES or not QUIZZES[quiz_id]["questions"]:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` में कोई प्रश्न नहीं हैं।", parse_mode="Markdown")
        return

    QUIZZES[quiz_id]["plays"] = QUIZZES[quiz_id].get("plays", 0) + 1
    save_quizzes(QUIZZES)

    user_states[user_id] = {
        "quiz_id": quiz_id,
        "index": 0,
        "score": 0,
        "chat_id": chat_id
    }
    await send_quiz_poll(user_id, context)

async def send_quiz_poll(user_id, context: ContextTypes.DEFAULT_TYPE):
    state = user_states[user_id]
    quiz = QUIZZES[state["quiz_id"]]
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
            text=f"🏁 *टेस्ट समाप्त!*\n\n📝 क्विज़: *{quiz['title']}*\n🏆 आपका स्कोर: *{score} / {total}*\n\nधन्यवाद!",
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
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    app.run_polling()

if __name__ == "__main__":
    main()
    
