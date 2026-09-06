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

        body = (
            f"नमस्ते डॉ देव कुमार जी,\n\n"
            f"टेस्ट का बैकअप सुरक्षित कर लिया गया है:\n\n"
            f"• शीर्षक: {quiz_title}\n"
            f"• Quiz ID: {quiz_id}\n"
            f"• कुल प्रश्न: {total_q}\n"
            f"• Telegram Play: /play {quiz_id}\n\n"
            f"JSON डेटा सुरक्षित है।"
        )
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
<html lang="hi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JB STUDY POINT - Quiz Creator</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }
.box { max-width: 650px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
h2 { color: #8B0000; text-align: center; margin: 0 0 15px 0; }
.field { margin-bottom: 15px; }
label { font-weight: 600; font-size: 13px; display: block; margin-bottom: 5px; }
input[type="text"], select { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #ccd0d5; border-radius: 6px; }
.card-q { background: #fafafa; border: 1px solid #e4e6eb; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.btn { display: block; width: 100%; background: #8B0000; color: #fff; border: none; padding: 12px; font-weight: bold; border-radius: 6px; cursor: pointer; }
.btn-add { background: #0D47A1; margin-bottom: 12px; }
.opt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
</style>
<script>
let qCount = 1;
function addQuestion() {
  qCount++;
  const div = document.createElement('div');
  div.className = 'card-q';
  div.innerHTML = `
    <b>प्रश्न ` + qCount + `</b>
    <input type="text" name="q_text_` + qCount + `" placeholder="यहाँ प्रश्न लिखें..." required style="margin-top:5px;">
    <div class="opt-grid">
      <input type="text" name="q_optA_` + qCount + `" placeholder="विकल्प A" required>
      <input type="text" name="q_optB_` + qCount + `" placeholder="विकल्प B" required>
      <input type="text" name="q_optC_` + qCount + `" placeholder="विकल्प C" required>
      <input type="text" name="q_optD_` + qCount + `" placeholder="विकल्प D" required>
    </div>
    <div style="margin-top:8px;">
      <label>सही उत्तर:</label>
      <select name="q_ans_` + qCount + `" style="width: auto;">
        <option value="0">विकल्प A</option><option value="1">विकल्प B</option>
        <option value="2">विकल्प C</option><option value="3">विकल्प D</option>
      </select>
    </div>
  `;
  document.getElementById('q-list').appendChild(div);
  document.getElementById('total_q').value = qCount;
}
</script></head><body>
<div class="box">
  <h2>JB STUDY POINT - Quiz Creator</h2>
  <form action="/save_quiz" method="POST">
    <input type="hidden" name="total_questions" id="total_q" value="1">
    <div class="field"><label>टेस्ट का नाम (शीर्षक):</label><input type="text" name="title" placeholder="यहाँ टेस्ट का नाम लिखें..." required></div>
    <div class="field"><label>क्रिएटर / संस्थान:</label><input type="text" name="creator" value="Dr. Dev Kumar | JB STUDY POINT" required></div>
    <div id="q-list">
      <div class="card-q">
        <b>प्रश्न 1</b>
        <input type="text" name="q_text_1" placeholder="यहाँ प्रश्न लिखें..." required style="margin-top:5px;">
        <div class="opt-grid">
          <input type="text" name="q_optA_1" placeholder="विकल्प A" required>
          <input type="text" name="q_optB_1" placeholder="विकल्प B" required>
          <input type="text" name="q_optC_1" placeholder="विकल्प C" required>
          <input type="text" name="q_optD_1" placeholder="विकल्प D" required>
        </div>
        <div style="margin-top:8px;">
          <label>सही उत्तर:</label>
          <select name="q_ans_1" style="width: auto;">
            <option value="0">विकल्प A</option><option value="1">विकल्प B</option>
            <option value="2">विकल्प C</option><option value="3">विकल्प D</option>
          </select>
        </div>
      </div>
    </div>
    <button type="button" class="btn btn-add" onclick="addQuestion()">➕ अगला प्रश्न जोड़ें</button>
    <button type="submit" class="btn">💾 टेस्ट पब्लिश करें</button>
  </form>
</div></body></html>"""

class QuizCreatorServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

    def do_POST(self):
        if self.path == "/save_quiz":
            c_len = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(c_len).decode('utf-8')
            parsed = parse_qs(post_data)

            title = parsed.get("title", ["नया टेस्ट"])[0].strip() or "नया टेस्ट"
            creator = parsed.get("creator", [DEFAULT_CREATOR])[0].strip() or DEFAULT_CREATOR
            total = int(parsed.get("total_questions", [1])[0])

            questions = []
            for idx in range(1, total + 1):
                qt = clean_question_text(parsed.get(f"q_text_{idx}", [""])[0])
                if not qt:
                    continue
                oa = parsed.get(f"q_optA_{idx}", [""])[0].strip()
                ob = parsed.get(f"q_optB_{idx}", [""])[0].strip()
                oc = parsed.get(f"q_optC_{idx}", [""])[0].strip()
                od = parsed.get(f"q_optD_{idx}", [""])[0].strip()
                ans = int(parsed.get(f"q_ans_{idx}", [0])[0])

                questions.append({
                    "question": qt,
                    "options": [oa, ob, oc, od],
                    "correct_id": ans,
                    "explanation": ""
                })

            if questions:
                q_id = generate_quiz_id()
                all_q = get_all_quizzes()
                q_obj = {
                    "id": q_id,
                    "title": title,
                    "creator": creator,
                    "type": "free",
                    "promo": "None",
                    "timer": "20s",
                    "questions": questions
                }
                all_q[q_id] = q_obj
                save_all_quizzes(all_q)
                threading.Thread(target=send_quiz_email_backup, args=(title, q_id, len(questions), q_obj)).start()

                resp = f"<html><body style='text-align:center;font-family:sans-serif;padding:40px;'><h2>✅ टेस्ट '{title}' बना दिया गया!</h2><p>Quiz ID: <b>{q_id}</b></p><p>📧 बैकअप ईमेल पर भेजा गया।</p><p>Telegram में भेजें: <code>/play {q_id}</code></p><a href='/'>वापस जाएँ</a></body></html>"
            else:
                resp = "<html><body><h3>कोई सवाल नहीं मिला।</h3><a href='/'>वापस</a></body></html>"

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(resp.encode("utf-8"))

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

# --- BOT LOGIC ---
async def post_init(application):
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("create", "Create quiz"),
        BotCommand("myquizzes", "View quizzes"),
        BotCommand("pdf", "Download PDF booklet"),
        BotCommand("omr", "Download OMR Sheet"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"नमस्ते {update.effective_user.first_name}! JB STUDY POINT बॉट सक्रिय है।")

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.args:
        title = " ".join(context.args).strip()
        q_id = generate_quiz_id()
        creator_sessions[update.effective_user.id] = {"title": title, "questions": [], "id": q_id}
        await update.message.reply_text(f"टेस्ट '{title}' शुरू हुआ। अब पोल (@QuizBot से) भेजें और अंत में /done लिखें।")
    else:
        await update.message.reply_text("कृपया नाम लिखें, जैसे: `/create History Test 1`")

async def handle_incoming_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions:
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
    await update.message.reply_text(f"प्रश्न सुरक्षित ({len(creator_sessions[user_id]['questions'])})")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions:
        return
    session = creator_sessions[user_id]
    q_id = session["id"]
    all_q = get_all_quizzes()
    all_q[q_id] = session
    save_all_quizzes(all_q)
    del creator_sessions[user_id]
    await update.message.reply_text(f"✅ टेस्ट सफलताપूर्वक बन गया! ID: `{q_id}`\nPDF के लिए भेजें: `/pdf {q_id}`", parse_mode="Markdown")

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    all_q = get_all_quizzes()
    if not all_q:
        await update.message.reply_text("कोई क्विज़ मौजूद नहीं है।")
        return
    lines = ["🧩 आपके टेस्ट्स:\n"]
    for q_id, data in all_q.items():
        lines.append(f"• *{data.get('title')}* (ID: `{q_id}`) — PDF: `/pdf {q_id}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ क्विज़ आईडी लिखें। उदाहरण: `/pdf GGN80C50L`")
        return
    quiz_id = context.args[0].strip().upper()
    all_q = get_all_quizzes()
    if quiz_id not in all_q:
        await update.message.reply_text("❌ क्विज़ नहीं मिला।")
        return
    await update.message.reply_text("⏳ PDF तैयार हो रही है...")
    try:
        buf = generate_pdf_bytes(all_q[quiz_id])
        await context.bot.send_document(chat_id=update.effective_chat.id, document=buf, filename="Exam_Booklet.pdf")
    except Exception as e:
        await update.message.reply_text(f"त्रुटि: {e}")

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("myquizzes", my_quizzes))
    app.add_handler(CommandHandler("pdf", pdf_command))
    app.add_handler(MessageHandler(filters.POLL, handle_incoming_poll))
    app.run_polling()

if __name__ == "__main__":
    main()
