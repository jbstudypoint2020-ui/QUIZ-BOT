import json
import os
import random
import re
import string
import io
import asyncio
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
DEFAULT_CREATOR = "JB STUDY POINT"

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

creator_sessions = {}
active_group_quizzes = {}
pending_setups = {}

def generate_quiz_id():
    return "GGN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def clean_question_text(raw_text):
    text = re.sub(r"^\s*\[\d+/\d+\]\s*", "", raw_text)
    text = re.sub(r"^\s*(Q|q)?\d+[\.\)\-:]\s*", "", text)
    return text.strip()

# 2-Column Professional Exam Booklet PDF
def generate_pdf_bytes(quiz_data):
    PAGE_W = 1240
    PAGE_H = 1754
    MARGIN_X = 50
    MARGIN_Y = 40
    COL_GAP = 30
    COL_W = (PAGE_W - (2 * MARGIN_X) - COL_GAP) // 2

    f_brand = ImageFont.truetype(FONT_PATH, 24)
    f_sub = ImageFont.truetype(FONT_PATH, 13)
    f_title = ImageFont.truetype(FONT_PATH, 22)
    f_tbl_head = ImageFont.truetype(FONT_PATH, 11)
    f_tbl_val = ImageFont.truetype(FONT_PATH, 12)
    f_inst_title = ImageFont.truetype(FONT_PATH, 12)
    f_inst = ImageFont.truetype(FONT_PATH, 11)
    f_bar = ImageFont.truetype(FONT_PATH, 13)
    f_q = ImageFont.truetype(FONT_PATH, 14)
    f_opt = ImageFont.truetype(FONT_PATH, 13)
    f_ans_title = ImageFont.truetype(FONT_PATH, 24)
    f_key = ImageFont.truetype(FONT_PATH, 15)

    title = str(quiz_data.get('title', 'MOCK TEST'))
    creator = str(quiz_data.get('creator', DEFAULT_CREATOR))
    questions = quiz_data.get('questions', [])
    total_q = len(questions)

    def wrap_text(text, font, max_w, draw):
        words = text.split()
        lines = []
        cur = ""
        for w in words:
            test = f"{cur} {w}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    pages = []

    def create_new_page(is_first=False):
        img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFFFF")
        draw = ImageDraw.Draw(img)

        draw.text((MARGIN_X, 22), f"{creator.upper()} — MOCK TEST SERIES", font=f_sub, fill="#777777")
        draw.text((PAGE_W - MARGIN_X - 220, 22), "FOR PRACTICE PURPOSE ONLY", font=f_sub, fill="#777777")
        draw.line([(MARGIN_X, 36), (PAGE_W - MARGIN_X, 36)], fill="#DDDDDD", width=1)

        y_offset = MARGIN_Y + 10

        if is_first:
            draw.ellipse([MARGIN_X, y_offset, MARGIN_X + 48, y_offset + 48], outline="#8B0000", width=2)
            draw.text((MARGIN_X + 11, y_offset + 12), "JB", font=f_brand, fill="#8B0000")
            draw.text((MARGIN_X + 58, y_offset + 5), creator, font=f_brand, fill="#111111")
            draw.text((MARGIN_X + 60, y_offset + 32), "TEST SERIES & ACADEMIC CELL", font=f_sub, fill="#666666")
            draw.line([(MARGIN_X, y_offset + 54), (PAGE_W - MARGIN_X, y_offset + 54)], fill="#8B0000", width=2)
            y_offset += 65

            t_bbox = draw.textbbox((0, 0), title.upper(), font=f_title)
            draw.text(((PAGE_W - (t_bbox[2] - t_bbox[0])) // 2, y_offset), title.upper(), font=f_title, fill="#000000")
            y_offset += 30

            sub_b = draw.textbbox((0, 0), "Paper - II : History / Practice Paper", font=f_sub)
            draw.text(((PAGE_W - (sub_b[2] - sub_b[0])) // 2, y_offset), "Paper - II : History / Practice Paper", font=f_sub, fill="#555555")
            y_offset += 25

            draw.rectangle([MARGIN_X, y_offset, PAGE_W - MARGIN_X, y_offset + 75], outline="#333333", width=1)
            draw.line([(MARGIN_X + 220, y_offset), (MARGIN_X + 220, y_offset + 75)], fill="#333333", width=1)
            draw.line([(PAGE_W - MARGIN_X - 320, y_offset), (PAGE_W - MARGIN_X - 320, y_offset + 75)], fill="#333333", width=1)
            draw.line([(MARGIN_X, y_offset + 45), (PAGE_W - MARGIN_X, y_offset + 45)], fill="#333333", width=1)

            draw.text((MARGIN_X + 10, y_offset + 6), "TEST NO.", font=f_tbl_head, fill="#444444")
            draw.text((MARGIN_X + 10, y_offset + 22), "01", font=f_tbl_val, fill="#000000")

            draw.text((MARGIN_X + 230, y_offset + 6), "ROLL NO.", font=f_tbl_head, fill="#444444")
            rx = MARGIN_X + 230
            for _ in range(8):
                draw.rectangle([rx, y_offset + 20, rx + 16, y_offset + 38], outline="#666666", width=1)
                rx += 20

            draw.text((PAGE_W - MARGIN_X - 310, y_offset + 6), "BOOKLET SERIES", font=f_tbl_head, fill="#444444")
            bx = PAGE_W - MARGIN_X - 310
            for char, active in [("A", True), ("B", False), ("C", False), ("D", False)]:
                if active:
                    draw.ellipse([bx, y_offset + 22, bx + 16, y_offset + 38], fill="#8B0000")
                    draw.text((bx + 4, y_offset + 23), char, font=f_tbl_val, fill="#FFFFFF")
                else:
                    draw.ellipse([bx, y_offset + 22, bx + 16, y_offset + 38], outline="#666666", width=1)
                    draw.text((bx + 4, y_offset + 23), char, font=f_tbl_val, fill="#000000")
                bx += 24

            draw.text((MARGIN_X + 10, y_offset + 52), "Time: 2 Hours", font=f_tbl_val, fill="#111111")
            draw.text((MARGIN_X + 230, y_offset + 52), f"Total Questions: {total_q}", font=f_tbl_val, fill="#111111")
            draw.text((PAGE_W - MARGIN_X - 310, y_offset + 52), f"Max. Marks: {total_q * 2}", font=f_tbl_val, fill="#111111")
            y_offset += 85

            draw.rectangle([MARGIN_X, y_offset, PAGE_W - MARGIN_X, y_offset + 95], outline="#CCCCCC", width=1)
            draw.text((MARGIN_X + 20, y_offset + 8), "INSTRUCTIONS / निर्देश", font=f_inst_title, fill="#8B0000")
            draw.text((MARGIN_X + 20, y_offset + 26), "1. इस पुस्तिका में कुल बहुविकल्पीय प्रश्न हैं। प्रत्येक प्रश्न 2 अंक का है।", font=f_inst, fill="#333333")
            draw.text((MARGIN_X + 20, y_offset + 42), "2. ओएमआर उत्तर पत्रक पर केवल नीले/काले बॉल-पॉइंट पेन से गोलों को पूर्ण रूप से गहरा करें।", font=f_inst, fill="#333333")
            draw.text((MARGIN_X + 20, y_offset + 58), "3. परीक्षा कक्ष में मोबाइल फोन या किसी भी इलेक्ट्रॉनिक उपकरण का प्रयोग वर्जित है।", font=f_inst, fill="#333333")
            draw.text((MARGIN_X + 20, y_offset + 74), "4. उत्तर तालिका अंतिम पृष्ठ पर प्रदान की गई है।", font=f_inst, fill="#333333")
            y_offset += 105

            draw.rectangle([MARGIN_X, y_offset, PAGE_W - MARGIN_X, y_offset + 26], fill="#8B0000")
            r_box = draw.textbbox((0, 0), "GENERAL PAPER & SUBJECT SECTION", font=f_bar)
            draw.text(((PAGE_W - (r_box[2] - r_box[0])) // 2, y_offset + 6), "GENERAL PAPER & SUBJECT SECTION", font=f_bar, fill="#FFFFFF")
            y_offset += 36
        else:
            y_offset = 60

        return img, draw, y_offset

    cur_img, cur_draw, start_y = create_new_page(is_first=True)
    cur_col = 0
    cur_y = start_y
    col_tops = [start_y, start_y]

    opt_labels = ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)"]
    answer_keys = []

    for i, q in enumerate(questions, 1):
        clean_q = clean_question_text(q.get('question', ''))
        q_lines = wrap_text(f"{i}. {clean_q}", f_q, COL_W, cur_draw)

        opt_items = []
        for o_idx, opt in enumerate(q.get('options', [])):
            lbl = opt_labels[o_idx] if o_idx < len(opt_labels) else f"({o_idx+1})"
            c_opt = re.sub(r"^\s*[A-Ha-h1-9][\.\)\-:]\s*", "", opt)
            wrapped = wrap_text(f"{lbl} {c_opt}", f_opt, COL_W - 15, cur_draw)
            opt_items.append(wrapped)

        correct_idx = q.get('correct_id', 0)
        c_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        answer_keys.append((f"{i}", c_lbl))

        tot_opt_lines = sum(len(x) for x in opt_items)
        block_h = (len(q_lines) * 22) + (tot_opt_lines * 19) + 14

        if cur_y + block_h > (PAGE_H - MARGIN_Y):
            if cur_col == 0:
                cur_col = 1
                cur_y = col_tops[1]
            else:
                pages.append(cur_img)
                cur_img, cur_draw, start_y = create_new_page(is_first=False)
                cur_col = 0
                col_tops = [start_y, start_y]
                cur_y = start_y

        col_x = MARGIN_X if cur_col == 0 else MARGIN_X + COL_W + COL_GAP

        for line in q_lines:
            cur_draw.text((col_x, cur_y), line, font=f_q, fill="#000000")
            cur_y += 22

        for item in opt_items:
            for line in item:
                cur_draw.text((col_x + 12, cur_y), line, font=f_opt, fill="#222222")
                cur_y += 19

        cur_y += 10

    pages.append(cur_img)

    # Last Page Answer Key
    ans_img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFFFF")
    ans_draw = ImageDraw.Draw(ans_img)

    ans_draw.text((MARGIN_X, 22), f"{creator.upper()} — ANSWER KEY & EVALUATION", font=f_sub, fill="#777777")
    ans_draw.line([(MARGIN_X, 36), (PAGE_W - MARGIN_X, 36)], fill="#8B0000", width=2)

    ay = 60
    t_box = ans_draw.textbbox((0, 0), "ANSWER KEY / उत्तर तालिका", font=f_ans_title)
    ans_draw.text(((PAGE_W - (t_box[2] - t_box[0])) // 2, ay), "ANSWER KEY / उत्तर तालिका", font=f_ans_title, fill="#8B0000")
    ay += 40

    sub_txt = f"{title}  |  Total Questions: {len(questions)}  |  Booklet Series: A"
    s_box = ans_draw.textbbox((0, 0), sub_txt, font=f_sub)
    ans_draw.text(((PAGE_W - (s_box[2] - s_box[0])) // 2, ay), sub_txt, font=f_sub, fill="#555555")
    ay += 35
    ans_draw.line([(MARGIN_X + 100, ay), (PAGE_W - MARGIN_X - 100, ay)], fill="#8B0000", width=1)
    ay += 35

    cols = 5
    usable_w = PAGE_W - (2 * MARGIN_X) - 40
    cw = usable_w // cols
    sx = MARGIN_X + 20

    for idx, (qn, ans) in enumerate(answer_keys):
        c = idx % cols
        r = idx // cols
        ix = sx + (c * cw)
        iy = ay + (r * 34)

        ans_draw.rectangle([ix, iy, ix + cw - 15, iy + 28], outline="#CCCCCC", fill="#FDFDFD", width=1)
        ans_draw.text((ix + 8, iy + 6), f"Q.{qn}", font=f_key, fill="#000000")
        ans_draw.text((ix + cw - 45, iy + 6), ans, font=f_key, fill="#8B0000")

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
    chat_id = update.effective_chat.id
    args = context.args

    if args and args[0].startswith("PLAY_"):
        quiz_id = args[0].replace("PLAY_", "")
        await prompt_quiz_settings(chat_id, quiz_id, user.id, context)
        return

    text = (
        f"🇮🇳 *नमस्ते {user.first_name}!*\n\n"
        "• नया टेस्ट बनाने के लिए: `/create टेस्ट का नाम`\n"
        "• प्रश्न फ़ॉरवर्ड करने के बाद: `/done`\n"
        "• टेस्ट सूची देखने के लिए: `/myquizzes`\n"
        "• टेस्ट शुरू करने के लिए: `/play QUIZ_ID`"
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
    explanation = poll.explanation if hasattr(poll, "explanation") and poll.explanation else ""

    session = creator_sessions[user_id]
    session["questions"].append({
        "question": poll.question,
        "options": options,
        "correct_id": correct_id,
        "explanation": explanation
    })

    count = len(session["questions"])
    if count == 1 or count % 5 == 0:
        await update.message.reply_text(f"✅ {count} question(s) saved from polls! ➡️\nSend more or /done")

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
        session["promo"] = "None" if text.lower() in ["no", "skip", "none"] else text
        session["step"] = "ASK_TYPE"
        await update.message.reply_text("🏷 Type (free/paid)")
        return

    elif step == "ASK_TYPE":
        session["type"] = "paid" if "paid" in text.lower() else "free"
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
            f"🆔 *ID:* `{q_id}`\n"
            f"🏷 *Type:* {session['type']}\n"
            f"📣 *Promo:* {session['promo']}\n"
            f"👤 *Creator:* {session['creator']}"
        )

        bot_info = await context.bot.get_me()
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=PLAY_{q_id}&text={session['title']}"
        add_group_url = f"https://t.me/{bot_info.username}?startgroup=PLAY_{q_id}"

        keyboard = [
            [InlineKeyboardButton("▶️ Start Quiz", callback_data=f"init_{q_id}")],
            [InlineKeyboardButton("📄 Download Booklet PDF", callback_data=f"pdf_{q_id}")],
            [InlineKeyboardButton("➕ Add to Group", url=add_group_url)],
            [InlineKeyboardButton("📩 Share", url=share_url)]
        ]

        await update.message.reply_text(card_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ कृपया क्विज़ आईडी लिखें। उदाहरण: `/play GGN80C50L`")
        return
    quiz_id = context.args[0].strip().upper()
    await prompt_quiz_settings(update.effective_chat.id, quiz_id, update.effective_user.id, context)

# ----------------- टाइमर और एक्सप्लेनेशन परमिशन प्रॉम्ट्स -----------------

async def prompt_quiz_settings(chat_id, quiz_id, host_user_id, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    if quiz_id not in all_q or not all_q[quiz_id].get("questions"):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` उपलब्ध नहीं है।")
        return

    pending_setups[chat_id] = {
        "quiz_id": quiz_id,
        "host_id": host_user_id,
        "timer": 20,
        "show_exp": False
    }

    keyboard = [
        [
            InlineKeyboardButton("⏱ 15s", callback_data=f"set_time_{chat_id}_15"),
            InlineKeyboardButton("⏱ 20s", callback_data=f"set_time_{chat_id}_20")
        ],
        [
            InlineKeyboardButton("⏱ 25s", callback_data=f"set_time_{chat_id}_25"),
            InlineKeyboardButton("⏱ 30s", callback_data=f"set_time_{chat_id}_30")
        ]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚙️ *टेस्ट सेटअप:* `{all_q[quiz_id]['title']}`\n\nकृपया प्रत्येक प्रश्न के लिए **समय सीमा (Timer)** चुनें:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("init_"):
        quiz_id = data.replace("init_", "")
        await prompt_quiz_settings(query.message.chat_id, quiz_id, user_id, context)

    elif data.startswith("set_time_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        timer_val = int(parts[3])

        if chat_id in pending_setups:
            if user_id != pending_setups[chat_id]["host_id"] and user_id != ADMIN_ID:
                await query.answer("❌ केवल टेस्ट शुरू करने वाले एडमिन ही यह चुन सकते हैं।", show_alert=True)
                return

            pending_setups[chat_id]["timer"] = timer_val

            exp_keyboard = [
                [
                    InlineKeyboardButton("✅ हाँ (Show)", callback_data=f"set_exp_{chat_id}_yes"),
                    InlineKey
