import json
import os
import random
import re
import string
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageDraw, ImageFont

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

# Keep-Alive Server for Render
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

def clean_question_text(raw_text):
    # पोल में आने वाले [117/200] या 1. जैसे पुराने नंबर हटाना
    text = re.sub(r"^\s*\[\d+/\d+\]\s*", "", raw_text)
    text = re.sub(r"^\s*(Q|q)?\d+[\.\)\-:]\s*", "", text)
    return text.strip()

# प्रीमियम कलरफुल व अंतिम पेज Answer Key वाली PDF
def generate_pdf_bytes(quiz_data):
    title = str(quiz_data.get('title', 'इतिहास टेस्ट'))
    creator = str(quiz_data.get('creator', DEFAULT_CREATOR))
    questions = quiz_data.get('questions', [])

    PAGE_WIDTH = 1240
    PAGE_HEIGHT = 1754
    MARGIN = 65
    CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)
    BG_COLOR = "#F8FAFC"  # प्रीमियम हल्का बैकग्राउंड

    font_title = ImageFont.truetype(FONT_PATH, 38)
    font_meta = ImageFont.truetype(FONT_PATH, 23)
    font_q = ImageFont.truetype(FONT_PATH, 26)
    font_opt = ImageFont.truetype(FONT_PATH, 23)
    font_ans_title = ImageFont.truetype(FONT_PATH, 32)
    font_key = ImageFont.truetype(FONT_PATH, 22)

    def wrap_text(text, font, max_w, draw):
        words = text.split()
        lines = []
        cur_line = ""
        for word in words:
            test = f"{cur_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_w:
                cur_line = test
            else:
                if cur_line:
                    lines.append(cur_line)
                cur_line = word
        if cur_line:
            lines.append(cur_line)
        return lines

    pages = []

    def new_page():
        img = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), BG_COLOR)
        return img, ImageDraw.Draw(img)

    cur_img, cur_draw = new_page()
    y = MARGIN

    # Top Header
    t_bbox = cur_draw.textbbox((0, 0), title, font=font_title)
    cur_draw.text(((PAGE_WIDTH - (t_bbox[2] - t_bbox[0])) // 2, y), title, font=font_title, fill="#0D47A1")
    y += 52

    meta = f"Creator: {creator}  |  Total Questions: {len(questions)}  |  Timer: 20s"
    m_bbox = cur_draw.textbbox((0, 0), meta, font=font_meta)
    cur_draw.text(((PAGE_WIDTH - (m_bbox[2] - m_bbox[0])) // 2, y), meta, font=font_meta, fill="#546E7A")
    y += 42
    cur_draw.line([(MARGIN, y), (PAGE_WIDTH - MARGIN, y)], fill="#0D47A1", width=3)
    y += 30

    opt_labels = ["(A)", "(B)", "(C)", "(D)", "(E)", "(F)", "(G)", "(H)"]
    answer_keys = []

    for i, q in enumerate(questions, 1):
        clean_q = clean_question_text(q.get('question', ''))
        q_lines = wrap_text(f"Q{i}. {clean_q}", font_q, CONTENT_WIDTH, cur_draw)

        opt_lines_list = []
        for o_idx, opt in enumerate(q.get('options', [])):
            lbl = opt_labels[o_idx] if o_idx < len(opt_labels) else f"({o_idx+1})"
            # विकल्प से पहले के डुप्लिकेट A/B/C हटाना
            cleaned_opt = re.sub(r"^\s*[A-Ha-h1-9][\.\)\-:]\s*", "", opt)
            wrapped = wrap_text(f"{lbl} {cleaned_opt}", font_opt, CONTENT_WIDTH - 40, cur_draw)
            opt_lines_list.append(wrapped)

        correct_idx = q.get('correct_id', 0)
        corr_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        answer_keys.append((f"Q{i}", corr_lbl))

        total_opt_lines = sum(len(l) for l in opt_lines_list)
        needed_height = (len(q_lines) * 38) + (total_opt_lines * 34) + 26

        if y + needed_height > (PAGE_HEIGHT - MARGIN):
            pages.append(cur_img)
            cur_img, cur_draw = new_page()
            y = MARGIN

        # रंगीन प्रश्न (Indigo / Royal Blue)
        for line in q_lines:
            cur_draw.text((MARGIN, y), line, font=font_q, fill="#1A237E")
            y += 38

        # रंगीन विकल्प (Dark Slate)
        for item_lines in opt_lines_list:
            for line in item_lines:
                cur_draw.text((MARGIN + 32, y), line, font=font_opt, fill="#263238")
                y += 34

        y += 20

    pages.append(cur_img)

    # ----------------- अंतिम पेज: ANSWER KEY -----------------
    ans_img, ans_draw = new_page()
    ay = MARGIN + 20

    ans_title = "— उत्तर तालिका (ANSWER KEY) —"
    abbox = ans_draw.textbbox((0, 0), ans_title, font=font_ans_title)
    ans_draw.text(((PAGE_WIDTH - (abbox[2] - abbox[0])) // 2, ay), ans_title, font=font_ans_title, fill="#B71C1C")
    ay += 55

    sub = f"परीक्षा: {title}  |  कुल प्रश्न: {len(questions)}"
    sbbox = ans_draw.textbbox((0, 0), sub, font=font_meta)
    ans_draw.text(((PAGE_WIDTH - (sbbox[2] - sbbox[0])) // 2, ay), sub, font=font_meta, fill="#546E7A")
    ay += 40
    ans_draw.line([(MARGIN + 80, ay), (PAGE_WIDTH - MARGIN - 80, ay)], fill="#B71C1C", width=2)
    ay += 45

    # 4-कॉलम सुंदर ग्रिड
    cols = 4
    col_w = (CONTENT_WIDTH - 60) // cols
    start_x = MARGIN + 30
    grid_y = ay

    for idx, (qn, ans) in enumerate(answer_keys):
        c = idx % cols
        r = idx // cols
        item_x = start_x + (c * col_w)
        item_y = grid_y + (r * 42)

        # प्रत्येक बॉक्स कार्ड
        ans_draw.rectangle([item_x, item_y, item_x + col_w - 20, item_y + 36], fill="#FFFFFF", outline="#CFD8DC", width=1)
        ans_draw.text((item_x + 12, item_y + 6), f"{qn}:", font=font_key, fill="#0D47A1")
        ans_draw.text((item_x + 85, item_y + 6), f"{ans}", font=font_key, fill="#2E7D32")

    pages.append(ans_img)

    pdf_io = io.BytesIO()
    if pages:
        pages[0].save(pdf_io, format="PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    pdf_io.seek(0)
    return pdf_io

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
        "• PDF डाउनलोड करें: `/pdf QUIZ_ID`"
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

    await context.bot.send_message(chat_id=chat_id, text="⏳ रंगीन हिंदी पीडीएफ व उत्तर तालिका तैयार की जा रही है...")
    try:
        pdf_buffer = generate_pdf_bytes(all_q[quiz_id])
        safe_filename = f"{all_q[quiz_id].get('title', 'Quiz')}.pdf".replace(" ", "_")

        await context.bot.send_document(
            chat_id=chat_id,
            document=pdf_buffer,
            filename=safe_filename,
            caption=f"📄 *{all_q[quiz_id]['title']}*\n👤 Creator: {all_q[quiz_id].get('creator', DEFAULT_CREATOR)}\n🆔 ID: `{quiz_id}`\n📌 *उत्तर तालिका अंतिम पेज पर है।*",
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
            question=clean_question_text(q["question"]),
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
    
