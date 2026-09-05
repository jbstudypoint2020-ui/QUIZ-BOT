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
    text = re.sub(r"^\s*\[\s*\d+\s*/\s*\d+\s*\]\s*", "", raw_text)
    text = re.sub(r"^\s*(?:Q|q|प्रश्न)?\s*\d+[\.\)\-:]\s*", "", text)
    text = re.sub(r"^\s*\[\s*\d+\s*\]\s*", "", text)
    text = re.sub(r"^\s*\(\s*\d+\s*\)\s*", "", text)
    return text.strip()

# --- EMAIL BACKUP SENDER ---
def send_quiz_email_backup(quiz_title, quiz_id, total_q, quiz_dict):
    sender = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_PASS")
    if not sender or not password:
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = sender
        msg['Subject'] = f"📚 Test Backup: {quiz_title} ({quiz_id})"

        body = (
            f"नमस्ते,\n\n"
            f"नया टेस्ट सफलतापूर्वक तैयार हो गया है और बैकअप सुरक्षित कर लिया गया है:\n\n"
            f"• टेस्ट का नाम: {quiz_title}\n"
            f"• Quiz ID: {quiz_id}\n"
            f"• कुल प्रश्न: {total_q}\n"
            f"• Telegram Play Command: /play {quiz_id}\n\n"
            f"JSON बैकअप फ़ाइल नीचे अटैच की गई है।"
        )
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        json_str = json.dumps(quiz_dict, ensure_ascii=False, indent=2)
        part = MIMEText(json_str, 'plain', 'utf-8')
        part.add_header('Content-Disposition', f'attachment; filename="{quiz_id}.json"')
        msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password.replace(" ", ""))
            server.send_message(msg)
        print(f"Backup email sent for {quiz_id}")
    except Exception as e:
        print(f"Failed to send email backup: {e}")

# --- WEB SERVER ---
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
    <div class="field"><label>टेस्ट का नाम:</label><input type="text" name="title" value="इतिहास टेस्ट" required></div>
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

            title = parsed.get("title", ["इतिहास टेस्ट"])[0]
            creator = parsed.get("creator", [DEFAULT_CREATOR])[0]
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

                resp = f"<html><body style='text-align:center;font-family:sans-serif;padding:40px;'><h2>✅ टेस्ट बना दिया गया!</h2><p>Quiz ID: <b>{q_id}</b></p><p>बैकअप आपकी ईमेल पर भेज दिया गया है।</p><p>Telegram में भेजें: <code>/play {q_id}</code></p><a href='/'>वापस जाएँ</a></body></html>"
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

# --- ULTRA HD 2-COLUMN BOOKLET PDF GENERATOR ---
def generate_pdf_bytes(quiz_data):
    PAGE_W = 2480
    PAGE_H = 3508
    MARGIN_X = 100
    MARGIN_Y = 80
    COL_GAP = 70
    COL_W = (PAGE_W - (2 * MARGIN_X) - COL_GAP) // 2

    f_brand = ImageFont.truetype(FONT_PATH, 48)
    f_sub = ImageFont.truetype(FONT_PATH, 26)
    f_title = ImageFont.truetype(FONT_PATH, 46)
    f_tbl_head = ImageFont.truetype(FONT_PATH, 22)
    f_tbl_val = ImageFont.truetype(FONT_PATH, 26)
    f_inst_title = ImageFont.truetype(FONT_PATH, 26)
    f_inst = ImageFont.truetype(FONT_PATH, 23)
    f_bar = ImageFont.truetype(FONT_PATH, 28)
    f_q = ImageFont.truetype(FONT_PATH, 28)
    f_opt = ImageFont.truetype(FONT_PATH, 26)
    f_ans_title = ImageFont.truetype(FONT_PATH, 50)
    f_key = ImageFont.truetype(FONT_PATH, 30)

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

        draw.text((MARGIN_X, 45), f"{creator.upper()} — MOCK TEST SERIES", font=f_sub, fill="#666666")
        draw.text((PAGE_W - MARGIN_X - 440, 45), "FOR PRACTICE PURPOSE ONLY", font=f_sub, fill="#666666")
        draw.line([(MARGIN_X, 75), (PAGE_W - MARGIN_X, 75)], fill="#CCCCCC", width=2)

        y_offset = MARGIN_Y + 25

        if is_first:
            draw.ellipse([MARGIN_X, y_offset, MARGIN_X + 96, y_offset + 96], outline="#8B0000", width=4)
            draw.text((MARGIN_X + 22, y_offset + 22), "JB", font=f_brand, fill="#8B0000")
            draw.text((MARGIN_X + 115, y_offset + 8), creator, font=f_brand, fill="#111111")
            draw.text((MARGIN_X + 118, y_offset + 60), "TEST SERIES & ACADEMIC CELL", font=f_sub, fill="#555555")
            draw.line([(MARGIN_X, y_offset + 110), (PAGE_W - MARGIN_X, y_offset + 110)], fill="#8B0000", width=4)
            y_offset += 130

            t_bbox = draw.textbbox((0, 0), title.upper(), font=f_title)
            draw.text(((PAGE_W - (t_bbox[2] - t_bbox[0])) // 2, y_offset), title.upper(), font=f_title, fill="#000000")
            y_offset += 60

            sub_b = draw.textbbox((0, 0), "Paper - II : History Practice Booklet", font=f_sub)
            draw.text(((PAGE_W - (sub_b[2] - sub_b[0])) // 2, y_offset), "Paper - II : History Practice Booklet", font=f_sub, fill="#555555")
            y_offset += 50

            draw.rectangle([MARGIN_X, y_offset, PAGE_W - MARGIN_X, y_offset + 150], outline="#333333", width=2)
            draw.line([(MARGIN_X + 440, y_offset), (MARGIN_X + 440, y_offset + 150)], fill="#333333", width=2)
            draw.line([(PAGE_W - MARGIN_X - 640, y_offset), (PAGE_W - MARGIN_X - 640, y_offset + 150)], fill="#333333", width=2)
            draw.line([(MARGIN_X, y_offset + 90), (PAGE_W - MARGIN_X, y_offset + 90)], fill="#333333", width=2)

            draw.text((MARGIN_X + 20, y_offset + 12), "TEST NO.", font=f_tbl_head, fill="#444444")
            draw.text((MARGIN_X + 20, y_offset + 42), "01", font=f_tbl_val, fill="#000000")

            draw.text((MARGIN_X + 460, y_offset + 12), "ROLL NO.", font=f_tbl_head, fill="#444444")
            rx = MARGIN_X + 460
            for _ in range(8):
                draw.rectangle([rx, y_offset + 40, rx + 32, y_offset + 76], outline="#666666", width=2)
                rx += 40

            draw.text((PAGE_W - MARGIN_X - 620, y_offset + 12), "BOOKLET SERIES", font=f_tbl_head, fill="#444444")
            bx = PAGE_W - MARGIN_X - 620
            for char, active in [("A", True), ("B", False), ("C", False), ("D", False)]:
                if active:
                    draw.ellipse([bx, y_offset + 42, bx + 32, y_offset + 74], fill="#8B0000")
                    draw.text((bx + 8, y_offset + 44), char, font=f_tbl_val, fill="#FFFFFF")
                else:
                    draw.ellipse([bx, y_offset + 42, bx + 32, y_offset + 74], outline="#666666", width=2)
                    draw.text((bx + 8, y_offset + 44), char, font=f_tbl_val, fill="#000000")
                bx += 48

            draw.text((MARGIN_X + 20, y_offset + 104), "Time: 2 Hours", font=f_tbl_val, fill="#111111")
            draw.text((MARGIN_X + 460, y_offset + 104), f"Total Questions: {total_q}", font=f_tbl_val, fill="#111111")
            draw.text((PAGE_W - MARGIN_X - 620, y_offset + 104), f"Max. Marks: {total_q * 2}", font=f_tbl_val, fill="#111111")
            y_offset += 175

            draw.rectangle([MARGIN_X, y_offset, PAGE_W - MARGIN_X, y_offset + 185], outline="#DDDDDD", width=2)
            draw.text((MARGIN_X + 30, y_offset + 12), "INSTRUCTIONS / निर्देश", font=f_inst_title, fill="#8B0000")
            draw.text((MARGIN_X + 30, y_offset + 48), "1. इस पुस्तिका में कुल बहुविकल्पीय प्रश्न हैं। प्रत्येक प्रश्न 2 अंक का है।", font=f_inst, fill="#333333")
            draw.text((MARGIN_X + 30, y_offset + 80), "2. ओएमआर उत्तर पत्रक पर केवल नीले/काले बॉल-पॉइंट पेन से गोलों को गहरा करें।", font=f_inst, fill="#333333")
            draw.text((MARGIN_X + 30, y_offset + 112), "3. परीक्षा कक्ष में मोबाइल फोन या किसी भी इलेक्ट्रॉनिक उपकरण का प्रयोग वर्जित है।", font=f_inst, fill="#333333")
            draw.text((MARGIN_X + 30, y_offset + 144), "4. उत्तर तालिका अंतिम पृष्ठ पर प्रदान की गई है।", font=f_inst, fill="#333333")
            y_offset += 205

            draw.rectangle([MARGIN_X, y_offset, PAGE_W - MARGIN_X, y_offset + 50], fill="#8B0000")
            r_box = draw.textbbox((0, 0), "GENERAL PAPER & SUBJECT SECTION", font=f_bar)
            draw.text(((PAGE_W - (r_box[2] - r_box[0])) // 2, y_offset + 10), "GENERAL PAPER & SUBJECT SECTION", font=f_bar, fill="#FFFFFF")
            y_offset += 75
        else:
            y_offset = 120

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
            wrapped = wrap_text(f"{lbl} {c_opt}", f_opt, COL_W - 30, cur_draw)
            opt_items.append(wrapped)

        correct_idx = q.get('correct_id', 0)
        c_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        answer_keys.append((f"{i}", c_lbl))

        tot_opt_lines = sum(len(x) for x in opt_items)
        block_h = (len(q_lines) * 44) + (tot_opt_lines * 38) + 30

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
            cur_y += 44

        for item in opt_items:
            for line in item:
                cur_draw.text((col_x + 24, cur_y), line, font=f_opt, fill="#222222")
                cur_y += 38

        cur_y += 24

    pages.append(cur_img)

    # Last Page Answer Key
    ans_img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFFFF")
    ans_draw = ImageDraw.Draw(ans_img)
    ans_draw.text((MARGIN_X, 45), f"{creator.upper()} — ANSWER KEY & EVALUATION", font=f_sub, fill="#666666")
    ans_draw.line([(MARGIN_X, 75), (PAGE_W - MARGIN_X, 75)], fill="#8B0000", width=4)

    ay = 120
    t_box = ans_draw.textbbox((0, 0), "ANSWER KEY / उत्तर तालिका", font=f_ans_title)
    ans_draw.text(((PAGE_W - (t_box[2] - t_box[0])) // 2, ay), "ANSWER KEY / उत्तर तालिका", font=f_ans_title, fill="#8B0000")
    ay += 80

    sub_txt = f"{title}  |  Total Questions: {len(questions)}  |  Booklet Series: A"
    s_box = ans_draw.textbbox((0, 0), sub_txt, font=f_sub)
    ans_draw.text(((PAGE_W - (s_box[2] - s_box[0])) // 2, ay), sub_txt, font=f_sub, fill="#555555")
    ay += 70
    ans_draw.line([(MARGIN_X + 200, ay), (PAGE_W - MARGIN_X - 200, ay)], fill="#8B0000", width=2)
    ay += 70

    cols = 5
    usable_w = PAGE_W - (2 * MARGIN_X) - 80
    cw = usable_w // cols
    sx = MARGIN_X + 40

    for idx, (qn, ans) in enumerate(answer_keys):
        c = idx % cols
        r = idx // cols
        ix = sx + (c * cw)
        iy = ay + (r * 68)
        ans_draw.rectangle([ix, iy, ix + cw - 30, iy + 56], outline="#CCCCCC", fill="#FDFDFD", width=2)
        ans_draw.text((ix + 16, iy + 12), f"Q.{qn}", font=f_key, fill="#000000")
        ans_draw.text((ix + cw - 90, iy + 12), ans, font=f_key, fill="#8B0000")

    pages.append(ans_img)
    pdf_io = io.BytesIO()
    if pages:
        pages[0].save(pdf_io, format="PDF", save_all=True, append_images=pages[1:], resolution=300.0)
    pdf_io.seek(0)
    return pdf_io
    # --- BOT LOGIC ---
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
        "🌐 *Quiz Creator Web:* आप नीचे **Open App** पर टैप करके वेब से भी टेस्ट बना सकते हैं।\n\n"
        "• नया टेस्ट: `/create टेस्ट का नाम`\n"
        "• प्रश्न फ़ॉरवर्ड करने के बाद: `/done`\n"
        "• टेस्ट सूची: `/myquizzes`\n"
        "• ग्रुप में चलायें: `/play QUIZ_ID`"
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
        f"✅ नया सत्र: *'{title}'*\n🆔 ID: `{q_id}`\n\n"
        "👉 अब **@QuizBot** से पोल फ़ॉरवर्ड करना शुरू करें।\n"
        "सारे फ़ॉरवर्ड हो जाने के बाद **/done** भेजें।"
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

    cleaned_q = clean_question_text(poll.question)

    session = creator_sessions[user_id]
    session["questions"].append({
        "question": cleaned_q,
        "options": options,
        "correct_id": correct_id,
        "explanation": explanation
    })

    count = len(session["questions"])
    if count == 1 or count % 5 == 0:
        await update.message.reply_text(f"✅ {count} प्रश्न सुरक्षित! ➡️ और भेजें या /done")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions or not creator_sessions[user_id]["questions"]:
        await update.message.reply_text("❌ कोई प्रश्न नहीं मिला। पहले पोल भेजें।")
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

        threading.Thread(target=send_quiz_email_backup, args=(session["title"], q_id, total_q, session)).start()

        del creator_sessions[user_id]

        card_text = (
            f"🎉 *Quiz Created!*\n\n"
            f"🏷 *Name:* {session['title']}\n"
            f"❓ *Questions:* {total_q}\n"
            f"🆔 *ID:* `{q_id}`\n"
            f"📧 *Email Backup:* Sent!\n"
            f"🏷 *Type:* {session['type']}\n"
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

# --- TIMING & EXPLANATION SETTINGS ---
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
        text=f"⚙️ *टेस्ट सेटअप:* `{all_q[quiz_id]['title']}`\n\nकृपया **टाइमर (प्रति प्रश्न समय)** चुनें:",
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
                await query.answer("❌ केवल एडमिन ही यह चुन सकते हैं।", show_alert=True)
                return

            pending_setups[chat_id]["timer"] = timer_val

            exp_keyboard = [
                [
                    InlineKeyboardButton("✅ हाँ (Show)", callback_data=f"set_exp_{chat_id}_yes"),
                    InlineKeyboardButton("❌ नहीं (Hide)", callback_data=f"set_exp_{chat_id}_no")
                ]
            ]
            await query.edit_message_text(
                text=f"⏱ समय: *{timer_val} सेकंड* चुना गया।\n\nक्या आप **व्याख्या (Explanation)** दिखाना चाहते हैं?",
                reply_markup=InlineKeyboardMarkup(exp_keyboard),
                parse_mode="Markdown"
            )

    elif data.startswith("set_exp_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        exp_choice = parts[3]

        if chat_id in pending_setups:
            if user_id != pending_setups[chat_id]["host_id"] and user_id != ADMIN_ID:
                await query.answer("❌ केवल एडमिन ही यह चुन सकते हैं।", show_alert=True)
                return

            pending_setups[chat_id]["show_exp"] = (exp_choice == "yes")
            setup_data = pending_setups[chat_id]
            q_id = setup_data["quiz_id"]
            t_sec = setup_data["timer"]
            s_exp = setup_data["show_exp"]

            del pending_setups[chat_id]
            await query.edit_message_text(f"✅ सेटअप पूरा हुआ! (समय: {t_sec}s | व्याख्या: {'हाँ' if s_exp else 'नहीं'})")
            await start_group_quiz(chat_id, q_id, t_sec, s_exp, context)

    elif data.startswith("pdf_"):
        quiz_id = data.replace("pdf_", "")
        await send_quiz_pdf(query.message.chat_id, quiz_id, context)

async def send_quiz_pdf(chat_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    if quiz_id not in all_q or not all_q[quiz_id].get("questions"):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` नहीं मिला।")
        return

    await context.bot.send_message(chat_id=chat_id, text="⏳ हाई-डेफिनिशन (Ultra HD) बुकलेट PDF तैयार हो रही है...")
    try:
        pdf_buffer = generate_pdf_bytes(all_q[quiz_id])
        safe_filename = f"{all_q[quiz_id].get('title', 'Exam')}_Booklet.pdf".replace(" ", "_")

        await context.bot.send_document(
            chat_id=chat_id,
            document=pdf_buffer,
            filename=safe_filename,
            caption=f"📄 *{all_q[quiz_id]['title']} (Booklet Format)*\n📌 *उत्तर तालिका अंतिम पृष्ठ पर है।*",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ PDF त्रुटि: {str(e)}")

# --- AUTO GROUP RUNNER ---
async def start_group_quiz(chat_id, quiz_id, timer_sec, show_exp, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    quiz = all_q[quiz_id]
    total = len(quiz["questions"])

    active_group_quizzes[chat_id] = {
        "quiz_id": quiz_id,
        "index": 0,
        "timer": int(timer_sec),
        "show_exp": show_exp,
        "users": {},
        "current_msg_id": None,
        "total_q": total
    }

    start_banner = (
        f"🎯 *टेस्ट शुरू हो रहा है!*\n\n"
        f"📝 टेस्ट: *{quiz['title']}*\n"
        f"❓ कुल प्रश्न: *{total}*\n"
        f"⏱ समय: *{timer_sec} सेकंड प्रति प्रश्न*\n"
        f"💡 व्याख्या: *{'सक्रिय (ON)' if show_exp else 'बंद (OFF)'}*\n\n"
        "⚡ *पहला प्रश्न 3 सेकंड में आ रहा है... तैयार रहें!*"
    )
    await context.bot.send_message(chat_id=chat_id, text=start_banner, parse_mode="Markdown")
    await asyncio.sleep(3)
    await send_next_question(chat_id, context)

async def auto_timer_countdown(chat_id, msg_id, duration, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(duration)
    if chat_id in active_group_quizzes:
        sess = active_group_quizzes[chat_id]
        if sess.get("current_msg_id") == msg_id:
            try:
                await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
            await asyncio.sleep(1)
            await send_next_question(chat_id, context)

async def send_next_question(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in active_group_quizzes:
        return

    sess = active_group_quizzes[chat_id]
    all_q = get_all_quizzes()
    quiz = all_q[sess["quiz_id"]]
    idx = sess["index"]
    timer_sec = int(sess["timer"])
    show_exp = sess["show_exp"]

    if idx < len(quiz["questions"]):
        q = quiz["questions"][idx]
        sess["index"] += 1

        exp_text = q.get("explanation", "") if show_exp else ""
        clean_q = clean_question_text(q['question'])

        header_q = f"[{idx+1}/{len(quiz['questions'])}] ⏱ {timer_sec}s | {clean_q}"
        if len(header_q) > 300:
            header_q = header_q[:295] + "..."

        try:
            poll_msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=header_q,
                options=q["options"],
                type="quiz",
                correct_option_id=int(q["correct_id"]),
                is_anonymous=False,
                open_period=timer_sec,
                explanation=exp_text[:200] if exp_text else None
            )
        except Exception:
            poll_msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=header_q,
                options=q["options"],
                type="quiz",
                correct_option_id=int(q["correct_id"]),
                is_anonymous=False,
                explanation=exp_text[:200] if exp_text else None
            )

        sess["current_msg_id"] = poll_msg.message_id
        context.bot_data[poll_msg.poll.id] = (chat_id, int(q["correct_id"]))

        asyncio.create_task(auto_timer_countdown(chat_id, poll_msg.message_id, timer_sec, context))
    else:
        await finish_quiz_and_show_ranks(chat_id, context)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p_ans = update.poll_answer
    poll_id = p_ans.poll_id
    user = p_ans.user

    if poll_id in context.bot_data:
        chat_id, correct_id = context.bot_data[poll_id]
        if chat_id in active_group_quizzes:
            sess = active_group_quizzes[chat_id]
            uid = user.id
            name = user.first_name or "Participant"

            if uid not in sess["users"]:
                sess["users"][uid] = {"name": name, "score": 0}

            if p_ans.option_ids and p_ans.option_ids[0] == correct_id:
                sess["users"][uid]["score"] += 1

async def finish_quiz_and_show_ranks(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in active_group_quizzes:
        return

    sess = active_group_quizzes[chat_id]
    all_q = get_all_quizzes()
    quiz = all_q[sess["quiz_id"]]
    total_q = sess["total_q"]
    participants = sess["users"]

    del active_group_quizzes[chat_id]

    if not participants:
        res_text = (
            f"🏁 *टेस्ट समाप्त!*\n\n"
            f"📝 टेस्ट: *{quiz['title']}*\n"
            "⚠️ किसी भी प्रतिभागी ने प्रश्नों का उत्तर नहीं दिया।"
        )
        await context.bot.send_message(chat_id=chat_id, text=res_text, parse_mode="Markdown")
        return

    sorted_users = sorted(participants.values(), key=lambda x: x["score"], reverse=True)

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    leaderboard_lines = []

    for rank, p in enumerate(sorted_users, 1):
        badge = medals[rank - 1] if rank <= 10 else f"{rank}."
        leaderboard_lines.append(f"{badge} *{p['name']}* — {p['score']}/{total_q} सही")

    rank_list_text = "\n".join(leaderboard_lines)

    final_result_message = (
        f"🏁 *टेस्ट परिणाम (Final Result)* 🏁\n\n"
        f"📝 टेस्ट: *{quiz['title']}*\n"
        f"❓ कुल प्रश्न: *{total_q}*\n"
        f"👥 कुल प्रतिभागी: *{len(sorted_users)}*\n\n"
        f"🏆 *रैंक व लीडरबोर्ड:*\n\n"
        f"{rank_list_text}\n\n"
        f"💐 *सभी प्रतिभागियों को बहुत-बहुत बधाई!*"
    )
    await context.bot.send_message(chat_id=chat_id, text=final_result_message, parse_mode="Markdown")

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
            f"🎯 Start Quiz: `/play {q_id}`\n"
            f"📄 PDF: `/pdf {q_id}`\n"
            "--------------------------------"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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
    
