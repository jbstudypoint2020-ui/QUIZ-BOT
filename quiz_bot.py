import json
import os
import random
import re
import string
import io
import asyncio
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
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

TOKEN = "5096262921:AAFPAc7i8BgJIP4Yx3fUy6g8sKksy2PVM1I"
ADMIN_ID = 1141231956
DB_FILE = "quizzes.json"
DEFAULT_CREATOR = "JB STUDY POINT"

GMAIL_USER = "jbstudypoint2020@gmail.com"
GMAIL_PASS = "oqxsihlmuxmsztqw"

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
    if not raw_text:
        return ""
    text = str(raw_text)
    text = re.sub(r"\[\s*\d+\s*/\s*\d+\s*\]", "", text)
    text = re.sub(r"⏱\s*\d+s?", "", text)
    text = re.sub(r"\d+s\s*\|", "", text)
    text = re.sub(r"\[\s*\d+s\s*\]", "", text)
    text = re.sub(r"\[.*?s.*?\]", "", text)
    text = re.sub(r"^\s*\[\s*\d+\s*/\s*\d+\s*\]\s*", "", text)
    text = re.sub(r"^\s*(?:Q|q|प्रश्न)?\s*\d+[\.\)\-:]\s*", "", text)
    text = re.sub(r"^\s*\[\s*\d+\s*\]\s*", "", text)
    text = re.sub(r"^\s*\(\s*\d+\s*\)\s*", "", text)
    return text.strip()

def send_quiz_email_backup(quiz_title, quiz_id, total_q, quiz_dict):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER
        msg['Subject'] = f"📚 Test Backup: {quiz_title} ({quiz_id})"
        body = f"नमस्ते डॉ देव कुमार जी,\n\nटेस्ट बैकअप सुरक्षित है: {quiz_title} ({quiz_id})"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        json_str = json.dumps(quiz_dict, ensure_ascii=False, indent=2)
        part = MIMEText(json_str, 'plain', 'utf-8')
        part.add_header('Content-Disposition', f'attachment; filename="{quiz_id}.json"')
        msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS.strip())
            server.send_message(msg)
    except Exception as e:
        print(f"Email error: {e}")

# --- WEB DASHBOARD ---
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="hi"><head><meta charset="UTF-8"><title>JB STUDY POINT - Quiz Creator</title>
<style>
body { font-family: sans-serif; background: #f0f2f5; padding: 20px; }
.box { max-width: 600px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
h2 { color: #8B0000; text-align: center; }
</style></head>
<body><div class="box"><h2>JB STUDY POINT - Quiz Creator Web</h2><p>बॉट और वेब सर्वर सुचारू रूप से कार्य कर रहा है।</p></div></body></html>"""

class QuizCreatorServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), QuizCreatorServer)
    server.serve_forever()

# --- PROFESSIONAL EXAM PAPER PDF GENERATOR ---
def generate_pdf_bytes(quiz_data):
    PAGE_W = 2480
    PAGE_H = 3508
    MARGIN_X = 140
    COL_GAP = 90
    COL_W = (PAGE_W - (2 * MARGIN_X) - COL_GAP) // 2

    f_sub = ImageFont.truetype(FONT_PATH, 24)
    f_title = ImageFont.truetype(FONT_PATH, 40)
    f_meta = ImageFont.truetype(FONT_PATH, 22)
    f_instr = ImageFont.truetype(FONT_PATH, 20)
    f_q = ImageFont.truetype(FONT_PATH, 26)
    f_opt = ImageFont.truetype(FONT_PATH, 24)
    f_ans_title = ImageFont.truetype(FONT_PATH, 50)
    f_key = ImageFont.truetype(FONT_PATH, 28)

    title = str(quiz_data.get('title', 'MOCK TEST'))
    questions = quiz_data.get('questions', [])

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

    dummy_img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
    dummy_draw = ImageDraw.Draw(dummy_img)

    q_blocks = []
    <br>
    opt_labels = ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)"]
    answer_keys = []

    for i, q in enumerate(questions, 1):
        clean_q = clean_question_text(q.get('question', ''))
        q_lines = wrap_text(f"{i}. {clean_q}", f_q, COL_W, dummy_draw)

        opt_items = []
        for o_idx, opt in enumerate(q.get('options', [])):
            lbl = opt_labels[o_idx] if o_idx < len(opt_labels) else f"({o_idx+1})"
            c_opt = clean_question_text(opt)
            wrapped = wrap_text(f"{lbl} {c_opt}", f_opt, COL_W - 30, dummy_draw)
            opt_items.append(wrapped)

        correct_idx = q.get('correct_id', 0)
        c_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        answer_keys.append((f"{i}", c_lbl))

        tot_opt_lines = sum(len(x) for x in opt_items)
        block_h = (len(q_lines) * 40) + (tot_opt_lines * 34) + 30
        q_blocks.append({
            "q_lines": q_lines,
            "opt_items": opt_items,
            "block_h": block_h
        })

    pages = []

    def create_first_page():
        img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
        draw = ImageDraw.Draw(img)

        draw.rectangle([80, 80, PAGE_W - 80, PAGE_H - 80], outline="#8B0000", width=6)
        draw.rectangle([95, 95, PAGE_W - 95, PAGE_H - 95], outline="#DAA520", width=3)
        draw.text((120, 105), "JB STUDY POINT YOUTUBE CHANNEL", font=f_sub, fill="#8B0000")
        draw.text((PAGE_W - 520, 105), "Mob: 8218345167", font=f_sub, fill="#000000")

        draw.rectangle([120, 140, PAGE_W - 120, 215], fill="#8B0000", outline="#8B0000")
        t_bbox = draw.textbbox((0, 0), title, font=f_title)
        draw.text(((PAGE_W - (t_bbox[2] - t_bbox[0])) // 2, 155), title, font=f_title, fill="#FFFFFF")

        draw.rectangle([120, 230, PAGE_W - 120, 310], outline="#444444", width=2)
        draw.text((140, 245), "TEST NO.: 01", font=f_meta, fill="#000000")
        draw.text((450, 245), "CANDIDATE NAME: ____________________________", font=f_meta, fill="#000000")
        draw.text((1350, 245), "ROLL NO.: ____________________", font=f_meta, fill="#000000")
        draw.text((1850, 245), "BOOKLET: A B C D", font=f_meta, fill="#8B0000")

        draw.rectangle([120, 325, PAGE_W - 120, 420], fill="#F9F9F9", outline="#B0C4DE", width=2)
        draw.text((140, 335), "INSTRUCTIONS / निर्देश:", font=f_meta, fill="#8B0000")
        draw.text((140, 365), "1. इस परीक्षा पुस्तिका में सभी प्रश्न अनिवार्य हैं। प्रत्येक प्रश्न 1 अंक का है।", font=f_instr, fill="#333333")
        draw.text((140, 390), "2. ओएमआर शीट या ऑनलाइन टेस्ट में सही विकल्प का चयन करें।", font=f_instr, fill="#333333")

        mid_x = PAGE_W // 2
        draw.line([(mid_x, 440), (mid_x, PAGE_H - 140)], fill="#B0C4DE", width=3)

        txt_img = Image.new("RGBA", (PAGE_W, PAGE_H), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        wm_font = ImageFont.truetype(FONT_PATH, 150)
        txt_draw.text((PAGE_W // 2 - 580, PAGE_H // 2 - 90), "JB STUDY POINT", font=wm_font, fill=(220, 180, 180, 75))
        rotated_wm = txt_img.rotate(30, resample=Image.Resampling.BICUBIC, center=(PAGE_W // 2, PAGE_H // 2))
        img.paste(Image.alpha_composite(img.convert("RGBA"), rotated_wm).convert("RGB"))

        return img, draw

    def create_later_page():
        img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
        draw = ImageDraw.Draw(img)

        draw.rectangle([80, 80, PAGE_W - 80, PAGE_H - 80], outline="#8B0000", width=6)
        draw.rectangle([95, 95, PAGE_W - 95, PAGE_H - 95], outline="#DAA520", width=3)
        mid_x = PAGE_W // 2
        draw.line([(mid_x, 140), (mid_x, PAGE_H - 140)], fill="#B0C4DE", width=3)

        draw.text((120, 105), f"JB STUDY POINT | {title}", font=f_sub, fill="#8B0000")
        draw.text((PAGE_W - 520, 105), "Mob: 8218345167", font=f_sub, fill="#000000")

        txt_img = Image.new("RGBA", (PAGE_W, PAGE_H), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        wm_font = ImageFont.truetype(FONT_PATH, 150)
        txt_draw.text((PAGE_W // 2 - 580, PAGE_H // 2 - 90), "JB STUDY POINT", font=wm_font, fill=(220, 180, 180, 75))
        rotated_wm = txt_img.rotate(30, resample=Image.Resampling.BICUBIC, center=(PAGE_W // 2, PAGE_H // 2))
        img.paste(Image.alpha_composite(img.convert("RGBA"), rotated_wm).convert("RGB"))

        return img, draw

    cur_img, cur_draw = create_first_page()
    cur_col = 0
    cur_y = 450
    page_limit = PAGE_H - 140

    for block in q_blocks:
        b_height = block["block_h"]
        if cur_y + b_height > page_limit:
            if cur_col == 0:
                cur_col = 1
                cur_y = 160
            else:
                pages.append(cur_img)
                cur_img, cur_draw = create_later_page()
                cur_col = 0
                cur_y = 160

        col_x = MARGIN_X if cur_col == 0 else MARGIN_X + COL_W + COL_GAP
        q_box_h = (len(block["q_lines"]) * 40) + 8
        cur_draw.rectangle([col_x - 10, cur_y - 4, col_x + COL_W + 10, cur_y + q_box_h], fill="#EAE6FF", outline="#7B68EE", width=2)

        for line in block["q_lines"]:
            cur_draw.text((col_x, cur_y), line, font=f_q, fill="#000080")
            cur_y += 40

        cur_y += 6
        for item in block["opt_items"]:
            for line in item:
                cur_draw.text((col_x + 15, cur_y), line, font=f_opt, fill="#111111")
                cur_y += 34

        cur_y += 24

    pages.append(cur_img)

    ans_img, ans_draw = create_later_page()
    ay = 160
    ans_draw.text(((PAGE_W - 600) // 2, ay), "ANSWER KEY / उत्तर तालिका", font=f_ans_title, fill="#8B0000")
    ay += 70
    sub_txt = f"{title} | Total: {len(questions)} Questions"
    ans_draw.text(((PAGE_W - 500) // 2, ay), sub_txt, font=f_sub, fill="#333333")
    ay += 60

    cols = 5
    usable_w = PAGE_W - (2 * MARGIN_X) - 80
    cw = usable_w // cols
    sx = MARGIN_X + 40

    for idx, (qn, ans) in enumerate(answer_keys):
        c = idx % cols
        r = idx // cols
        ix = sx + (c * cw)
        iy = ay + (r * 65)
        ans_draw.rectangle([ix, iy, ix + cw - 25, iy + 52], outline="#8B0000", fill="#FFFFFF", width=2)
        ans_draw.text((ix + 12, iy + 10), f"Q.{qn}", font=f_key, fill="#000000")
        ans_draw.text((ix + cw - 75, iy + 10), ans, font=f_key, fill="#8B0000")

    pages.append(ans_img)
    pdf_io = io.BytesIO()
    pages[0].save(pdf_io, format="PDF", save_all=True, append_images=pages[1:], resolution=300.0)
    pdf_io.seek(0)
    return pdf_io

# --- ADVANCED BOT & GAME ENGINE ---
async def post_init(application):
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("create", "Create quiz"),
        BotCommand("myquizzes", "View quizzes"),
        BotCommand("play", "Play quiz in group"),
        BotCommand("pdf", "Download PDF booklet"),
        BotCommand("backup", "Email backup"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    if args and args[0].startswith("PLAY_"):
        quiz_id = args[0].replace("PLAY_", "")
        await prompt_quiz_settings(update.effective_chat.id, quiz_id, user.id, context)
        return

    text = (
        f"🇮🇳 *नमस्ते {user.first_name}!*\n\n"
        "🎯 **JB STUDY POINT Quiz Bot** में आपका स्वागत है।\n\n"
        "• नया टेस्ट बनाएँ: `/create`\n"
        "• टेस्ट सूची देखें: `/myquizzes`\n"
        "• ग्रुप में टेस्ट खेलें: `/play QUIZ_ID`\n"
        "• PDF बुकलेट डाउनलोड करें: `/pdf QUIZ_ID`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.args:
        title = " ".join(context.args).strip()
        q_id = generate_quiz_id()
        creator_sessions[update.effective_user.id] = {"title": title, "questions": [], "id": q_id, "step": "POLLS"}
        await update.message.reply_text(f"✅ टेस्ट '{title}' शुरू हुआ!\n👉 अब `@QuizBot` से पोल फ़ॉरवर्ड करना शुरू करें।\nसभी प्रश्न भेजने के बाद **/done** लिखें।")
    else:
        creator_sessions[update.effective_user.id] = {"step": "TITLE"}
        await update.message.reply_text("📝 कृपया इस टेस्ट का **नाम (शीर्षक)** लिखकर भेजें:")

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions:
        return
    session = creator_sessions[user_id]
    if session.get("step") == "TITLE":
        title = update.message.text.strip()
        q_id = generate_quiz_id()
        creator_sessions[user_id] = {"title": title, "questions": [], "id": q_id, "step": "POLLS"}
        await update.message.reply_text(f"✅ टेस्ट का नाम तय हुआ: *'{title}'*\n👉 अब `@QuizBot` से पोल फ़ॉरवर्ड करें।\nसमाप्त होने पर **/done** भेजें।", parse_mode="Markdown")

async def handle_incoming_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions or creator_sessions[user_id].get("step") != "POLLS":
        return
    poll = update.message.poll
    if not poll:
        return
    options = [opt.text for opt in poll.options]
    correct_id = poll.correct_option_id if poll.correct_option_id is not None else 0
    creator_sessions[user_id]["questions"].append({
        "question": clean_question_text(poll.question),
        "options": options,
        "correct_id": correct_id
    })
    count = len(creator_sessions[user_id]["questions"])
    await update.message.reply_text(f"✅ प्रश्न सुरक्षित ({count})")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions:
        return
    session = creator_sessions[user_id]
    q_id = session["id"]
    all_q = get_all_quizzes()
    all_q[q_id] = session
    save_all_quizzes(all_q)
    threading.Thread(target=send_quiz_email_backup, args=(session["title"], q_id, len(session["questions"]), session)).start()
    del creator_sessions[user_id]

    keyboard = [
        [InlineKeyboardButton("▶️ Start Quiz", callback_data=f"init_{q_id}")],
        [InlineKeyboardButton("📄 Download PDF Booklet", callback_data=f"pdf_{q_id}")]
    ]
    await update.message.reply_text(
        f"🎉 टेस्ट सफलताપूर्वक बन गया!\n🆔 ID: `{q_id}`\n📧 बैकअप ईमेल पर भेज दिया गया है।",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    all_q = get_all_quizzes()
    if not all_q:
        await update.message.reply_text("कोई क्विज़ मौजूद नहीं है।")
        return
    lines = ["🧩 आपके टेस्ट्स:\n"]
    for q_id, data in all_q.items():
        lines.append(f"• *{data.get('title')}* (ID: `{q_id}`) — PDF: `/pdf {q_id}` | Play: `/play {q_id}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def prompt_quiz_settings(chat_id, quiz_id, host_id, context):
    all_q = get_all_quizzes()
    if quiz_id not in all_q:
        await context.bot.send_message(chat_id=chat_id, text="❌ क्विज़ नहीं मिला।")
        return
    pending_setups[chat_id] = {"quiz_id": quiz_id, "host_id": host_id, "timer": 20, "negative": 0.0}
    keyboard = [
        [InlineKeyboardButton("⏱ 15s", callback_data=f"set_time_{chat_id}_15"), InlineKeyboardButton("⏱ 20s", callback_data=f"set_time_{chat_id}_20")],
        [InlineKeyboardButton("⏱ 25s", callback_data=f"set_time_{chat_id}_25"), InlineKeyboardButton("⏱ 30s", callback_data=f"set_time_{chat_id}_30")]
    ]
    await context.bot.send_message(chat_id=chat_id, text="⚙️ **समय (टाइमर) चुनें:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
        chat_id, timer_val = int(parts[2]), int(parts[3])
        if chat_id in pending_setups:
            pending_setups[chat_id]["timer"] = timer_val
            neg_keyboard = [
                [InlineKeyboardButton("0.0 (No Negative)", callback_data=f"set_neg_{chat_id}_0"), InlineKeyboardButton("-0.33 (1/3rd)", callback_data=f"set_neg_{chat_id}_33")],
                [InlineKeyboardButton("-0.50 (1/2)", callback_data=f"set_neg_{chat_id}_50"), InlineKeyboardButton("-0.25 (1/4th)", callback_data=f"set_neg_{chat_id}_25")]
            ]
            await query.edit_message_text(text=f"⏱ समय: *{timer_val}s*\n\n⚠️ **निगेटिव मार्किंग चुनें:**", reply_markup=InlineKeyboardMarkup(neg_keyboard), parse_mode="Markdown")

    elif data.startswith("set_neg_"):
        parts = data.split("_")
        chat_id, neg_code = int(parts[2]), parts[3]
        neg_map = {"0": 0.0, "33": 0.33, "50": 0.50, "25": 0.25}
        neg_val = neg_map.get(neg_code, 0.0)
        if chat_id in pending_setups:
            pending_setups[chat_id]["negative"] = neg_val
            setup = pending_setups[chat_id]
            del pending_setups[chat_id]
            await query.edit_message_text(f"✅ सेटअप पूर्ण! टेस्ट शुरू हो रहा है...")
            await start_group_quiz(chat_id, setup["quiz_id"], setup["timer"], setup["negative"], (query.message.chat.type == "private"), context)

    elif data.startswith("pdf_"):
        quiz_id = data.replace("pdf_", "")
        await send_quiz_pdf(query.message.chat_id, quiz_id, context)

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ क्विज़ आईडी लिखें। उदाहरण: `/play GGN80C50L`")
        return
    quiz_id = context.args[0].strip().upper()
    await prompt_quiz_settings(update.effective_chat.id, quiz_id, update.effective_user.id, context)

async def send_quiz_pdf(chat_id, quiz_id, context):
    all_q = get_all_quizzes()
    if quiz_id not in all_q:
        await context.bot.send_message(chat_id=chat_id, text="❌ क्विज़ नहीं मिला।")
        return
    await context.bot.send_message(chat_id=chat_id, text="⏳ असली परीक्षा जैसी PDF तैयार हो रही है...")
    try:
        buf = generate_pdf_bytes(all_q[quiz_id])
        await context.bot.send_document(chat_id=chat_id, document=buf, filename="Exam_Booklet.pdf")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"त्रुटि: {e}")

async def start_group_quiz(chat_id, quiz_id, timer_sec, neg_val, is_private, context):
    all_q = get_all_quizzes()
    quiz = all_q[quiz_id]
    total = len(quiz["questions"])
    active_group_quizzes[chat_id] = {
        "quiz_id": quiz_id, "index": 0, "timer": int(timer_sec), "negative": neg_val,
        "is_private": is_private, "users": {}, "current_msg_id": None, "total_q": total, "timer_task": None
    }
    banner = f"🎯 *टेस्ट शुरू हो रहा है!*\n📝 टेस्ट: *{quiz['title']}*\n❓ कुल प्रश्न: *{total}*\n⏱ समय: *{timer_sec}s*"
    await context.bot.send_message(chat_id=chat_id, text=banner, parse_mode="Markdown")
    await asyncio.sleep(2)
    await send_next_question(chat_id, context)

async def auto_timer_countdown(chat_id, msg_id, duration, context):
    try:
        await asyncio.sleep(duration)
        if chat_id in active_group_quizzes and active_group_quizzes[chat_id].get("current_msg_id") == msg_id:
            try:
                await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            await send_next_question(chat_id, context)
    except asyncio.CancelledError:
        pass

async def send_next_question(chat_id, context):
    if chat_id not in active_group_quizzes:
        return
    sess = active_group_quizzes[chat_id]
    quiz = get_all_quizzes()[sess["quiz_id"]]
    idx = sess["index"]
    if idx < len(quiz["questions"]):
        q = quiz["questions"][idx]
        sess["index"] += 1
        header_q = f"[{idx+1}/{len(quiz['questions'])}] ⏱ {sess['timer']}s | {q['question']}"
        poll_msg = await context.bot.send_poll(
            chat_id=chat_id, question=header_q[:300], options=q["options"],
            type="quiz", correct_option_id=int(q["correct_id"]), is_anonymous=False, open_period=sess["timer"]
        )
        sess["current_msg_id"] = poll_msg.message_id
        context.bot_data[poll_msg.poll.id] = (chat_id, int(q["correct_id"]), idx)
        sess["timer_task"] = asyncio.create_task(auto_timer_countdown(chat_id, poll_msg.message_id, sess["timer"], context))
    else:
        await finish_quiz_and_show_ranks(chat_id, context)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p_ans = update.poll_answer
    poll_id = p_ans.poll_id
    user = p_ans.user
    if poll_id in context.bot_data:
        chat_id, correct_id, q_idx = context.bot_data[poll_id]
        if chat_id in active_group_quizzes:
            sess = active_group_quizzes[chat_id]
            uid, name = user.id, user.first_name or "Participant"
            if uid not in sess["users"]:
                sess["users"][uid] = {"name": name, "correct": 0, "wrong": 0, "score": 0.0}
            if p_ans.option_ids:
                if p_ans.option_ids[0] == correct_id:
                    sess["users"][uid]["correct"] += 1
                    sess["users"][uid]["score"] += 1.0
                else:
                    sess["users"][uid]["wrong"] += 1
                    sess["users"][uid]["score"] -= sess["negative"]

async def finish_quiz_and_show_ranks(chat_id, context):
    if chat_id not in active_group_quizzes:
        return
    sess = active_group_quizzes[chat_id]
    quiz = get_all_quizzes()[sess["quiz_id"]]
    participants = sess["users"]
    del active_group_quizzes[chat_id]

    if not participants:
        await context.bot.send_message(chat_id=chat_id, text=f"🏁 टेस्ट समाप्त! किसी ने उत्तर नहीं दिया।")
        return

    sorted_users = sorted(participants.items(), key=lambda x: x[1]["score"], reverse=True)
    lines = []
    for rank, (uid, p) in enumerate(sorted_users, 1):
        lines.append(f"{rank}. *{p['name']}* — {max(0.0, round(p['score'], 2))}/{sess['total_q']} अंक")

    final_msg = f"🏁 *टेस्ट परिणाम (Final Result)*\n📝 *{quiz['title']}*\n\n🏆 *रैंक व लीडरबोर्ड:*\n\n" + "\n".join(lines)
    await context.bot.send_message(chat_id=chat_id, text=final_msg, parse_mode="Markdown")

async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ क्विज़ आईडी लिखें। उदाहरण: `/pdf GGN80C50L`")
        return
    quiz_id = context.args[0].strip().upper()
    await send_quiz_pdf(update.effective_chat.id, quiz_id, context)

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("myquizzes", my_quizzes))
    app.add_handler(CommandHandler("pdf", pdf_command))
    app.add_handler(MessageHandler(filters.POLL, handle_incoming_poll))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.run_polling()

if __name__ == "__main__":
    main()
