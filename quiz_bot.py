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
        self.wfile.write(HTML_TEMPLATE.encode("text/html; charset=utf-8"))

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

                resp = f"<html><head><meta charset='UTF-8'></head><body style='text-align:center;font-family:sans-serif;padding:40px;'><h2>✅ टेस्ट '{title}' बना दिया गया!</h2><p>Quiz ID: <b>{q_id}</b></p><p>📧 बैकअप ईमेल पर भेजा गया।</p><p>Telegram में भेजें: <code>/play {q_id}</code></p><a href='/'>वापस जाएँ</a></body></html>"
            else:
                resp = "<html><head><meta charset='UTF-8'></head><body><h3>कोई सवाल नहीं मिला।</h3><a href='/'>वापस</a></body></html>"

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
    MARGIN_Y = 140
    COL_GAP = 90
    COL_W = (PAGE_W - (2 * MARGIN_X) - COL_GAP) // 2

    f_sub = ImageFont.truetype(FONT_PATH, 26)
    f_q = ImageFont.truetype(FONT_PATH, 28)
    f_opt = ImageFont.truetype(FONT_PATH, 26)
    f_ans_title = ImageFont.truetype(FONT_PATH, 50)
    f_key = ImageFont.truetype(FONT_PATH, 28)

    title = str(quiz_data.get('title', 'MOCK TEST'))
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

    def create_page():
        img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
        draw = ImageDraw.Draw(img)

        draw.rectangle([80, 80, PAGE_W - 80, PAGE_H - 80], outline="#8B0000", width=6)
        draw.rectangle([95, 95, PAGE_W - 95, PAGE_H - 95], outline="#DAA520", width=3)

        mid_x = PAGE_W // 2
        draw.line([(mid_x, 160), (mid_x, PAGE_H - 160)], fill="#B0C4DE", width=3)

        draw.text((120, 105), "JB STUDY POINT YOUTUBE CHANNEL", font=f_sub, fill="#8B0000")
        draw.text((PAGE_W - 520, 105), "Mob: 8218345167", font=f_sub, fill="#000000")

        txt_img = Image.new("RGBA", (PAGE_W, PAGE_H), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        wm_font = ImageFont.truetype(FONT_PATH, 150)
        txt_draw.text((PAGE_W // 2 - 580, PAGE_H // 2 - 90), "JB STUDY POINT", font=wm_font, fill=(220, 180, 180, 85))
        rotated_wm = txt_img.rotate(30, resample=Image.Resampling.BICUBIC, center=(PAGE_W // 2, PAGE_H // 2))
        img.paste(Image.alpha_composite(img.convert("RGBA"), rotated_wm).convert("RGB"))

        return img, draw

    cur_img, cur_draw = create_page()
    cur_col = 0
    cur_y = MARGIN_Y + 70
    col_tops = [cur_y, cur_y]

    opt_labels = ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)"]
    answer_keys = []

    for i, q in enumerate(questions, 1):
        clean_q = clean_question_text(q.get('question', ''))
        q_lines = wrap_text(f"{i}. {clean_q}", f_q, COL_W, cur_draw)

        opt_items = []
        for o_idx, opt in enumerate(q.get('options', [])):
            lbl = opt_labels[o_idx] if o_idx < len(opt_labels) else f"({o_idx+1})"
            c_opt = clean_question_text(opt)
            wrapped = wrap_text(f"{lbl} {c_opt}", f_opt, COL_W - 30, cur_draw)
            opt_items.append(wrapped)

        correct_idx = q.get('correct_id', 0)
        c_lbl = opt_labels[correct_idx] if correct_idx < len(opt_labels) else f"({correct_idx+1})"
        answer_keys.append((f"{i}", c_lbl))

        tot_opt_lines = sum(len(x) for x in opt_items)
        block_h = (len(q_lines) * 44) + (tot_opt_lines * 38) + 35

        if cur_y + block_h > (PAGE_H - MARGIN_Y):
            if cur_col == 0:
                cur_col = 1
                cur_y = col_tops[1]
            else:
                pages.append(cur_img)
                cur_img, cur_draw = create_page()
                cur_col = 0
                cur_y = MARGIN_Y + 70
                col_tops = [cur_y, cur_y]

        col_x = MARGIN_X if cur_col == 0 else MARGIN_X + COL_W + COL_GAP

        q_box_h = (len(q_lines) * 44) + 10
        cur_draw.rectangle([col_x - 10, cur_y - 5, col_x + COL_W + 10, cur_y + q_box_h], fill="#EAE6FF", outline="#7B68EE", width=2)

        for line in q_lines:
            cur_draw.text((col_x, cur_y), line, font=f_q, fill="#000080")
            cur_y += 44

        cur_y += 8
        for item in opt_items:
            for line in item:
                cur_draw.text((col_x + 15, cur_y), line, font=f_opt, fill="#111111")
                cur_y += 38

        cur_y += 30

    pages.append(cur_img)

    ans_img, ans_draw = create_page()
    ay = MARGIN_Y + 80
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
    if pages:
        pages[0].save(pdf_io, format="PDF", save_all=True, append_images=pages[1:], resolution=300.0)
    pdf_io.seek(0)
    return pdf_io
    # --- BOT LOGIC & GAME ENGINE ---
async def post_init(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("create", "Create a new quiz"),
        BotCommand("done", "Complete quiz creation"),
        BotCommand("myquizzes", "View created quizzes"),
        BotCommand("backup", "Send backup to email now"),
        BotCommand("omr", "Download 100-Question OMR Sheet"),
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
        "🌐 *Quiz Creator Web:* नीचे **Open App** पर टैप करके वेब से सीधे टेस्ट बनाएँ।\n\n"
        "• नया टेस्ट: `/create` (बॉट आपसे टेस्ट का नाम पूछेगा)\n"
        "• प्रश्न फ़ॉरवर्ड करने के बाद: `/done`\n"
        "• टेस्ट सूची: `/myquizzes`\n"
        "• ईमेल पर बैकअप: `/backup`\n"
        "• OMR शीट डाउनलोड करें: `/omr`\n"
        "• PDF बुकलेट डाउनलोड करें: `/pdf QUIZ_ID`\n"
        "• ग्रुप में चलायें: `/play QUIZ_ID`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ केवल एडमिन ही नया क्विज़ बना सकते हैं।")
        return

    if context.args:
        title = " ".join(context.args).strip()
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
            "सारे प्रश्न फ़ॉरवर्ड हो जाने के बाद **/done** भेजें।"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        creator_sessions[user_id] = {
            "step": "AWAITING_TITLE"
        }
        await update.message.reply_text("📝 कृपया इस टेस्ट का **नाम (शीर्षक)** लिखकर भेजें:")

async def handle_incoming_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in creator_sessions or creator_sessions[user_id].get("step") != "COLLECTING_POLLS":
        await update.message.reply_text("⚠️ कृपया पहले `/create` भेजकर टेस्ट का नाम तय करें!")
        return

    poll = update.message.poll
    if not poll:
        return

    options = [clean_question_text(opt.text) for opt in poll.options]
    correct_id = poll.correct_option_id if poll.correct_option_id is not None else 0
    explanation = clean_question_text(poll.explanation) if hasattr(poll, "explanation") and poll.explanation else ""
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
    if user_id not in creator_sessions or not creator_sessions[user_id].get("questions"):
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

    if step == "AWAITING_TITLE":
        title = text
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
            f"✅ टेस्ट का नाम तय हुआ: *'{title}'*\n🆔 ID: `{q_id}`\n\n"
            "👉 अब **@QuizBot** से पोल फ़ॉरवर्ड करना शुरू करें।\n"
            "सारे प्रश्न फ़ॉरवर्ड हो जाने के बाद **/done** भेजें।"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif step == "ASK_SECTION":
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
            f"📧 *Email Backup:* Sent to {GMAIL_USER}\n"
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

async def handle_document_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    doc = update.message.document
    if doc and doc.file_name.endswith(".json"):
        await update.message.reply_text("⏳ बैकअप फ़ाइल प्रोसेस की जा रही है...")
        try:
            tg_file = await context.bot.get_file(doc.file_id)
            b_data = await tg_file.download_as_bytearray()
            restored = json.loads(b_data.decode("utf-8"))

            all_q = get_all_quizzes()
            if "id" in restored and "questions" in restored:
                all_q[restored["id"]] = restored
                save_all_quizzes(all_q)
                await update.message.reply_text(f"✅ टेस्ट `{restored.get('title')}` सफलतापूर्वक रिस्टोर हो गया! (ID: `{restored['id']}`)")
            elif isinstance(restored, dict):
                all_q.update(restored)
                save_all_quizzes(all_q)
                await update.message.reply_text(f"✅ कुल {len(restored)} टेस्ट सफलतापूर्वक रिस्टोर हो गए!")
        except Exception as e:
            await update.message.reply_text(f"❌ रिस्टोर विफल: {str(e)}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    all_q = get_all_quizzes()
    if not all_q:
        await update.message.reply_text("❌ कोई टेस्ट मौजूद नहीं है।")
        return

    await update.message.reply_text(f"⏳ कुल {len(all_q)} टेस्टों का बैकअप {GMAIL_USER} पर भेजा जा रहा है...")
    threading.Thread(target=send_quiz_email_backup, args=("All Tests Backup", "FULL_BACKUP", len(all_q), all_q)).start()
    await update.message.reply_text("✅ बैकअप ईमेल भेज दिया गया है!")

async def omr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ 100 प्रश्नों की OMR शीट तैयार हो रही है...")
    try:
        omr_buffer = generate_omr_sheet_bytes()
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=omr_buffer,
            filename="JB_STUDY_POINT_100Q_OMR_Sheet.pdf",
            caption="📄 *100 प्रश्नों की प्रिंटेबल OMR शीट (300 DPI Ultra-HD)*"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ OMR त्रुटि: {str(e)}")

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ क्विज़ आईडी लिखें। उदाहरण: `/play GGN80C50L`")
        return
    quiz_id = context.args[0].strip().upper()
    await prompt_quiz_settings(update.effective_chat.id, quiz_id, update.effective_user.id, context)

# --- ADVANCED SETTINGS ---
async def prompt_quiz_settings(chat_id, quiz_id, host_user_id, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    if quiz_id not in all_q or not all_q[quiz_id].get("questions"):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` उपलब्ध नहीं है।")
        return

    pending_setups[chat_id] = {
        "quiz_id": quiz_id,
        "host_id": host_user_id,
        "timer": 20,
        "negative": 0.0,
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
        text=f"⚙️ *टेस्ट सेटअप:* `{all_q[quiz_id]['title']}`\n\n1️⃣ **समय (टाइमर) चुनें:**",
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
            neg_keyboard = [
                [
                    InlineKeyboardButton("0.0 (No Negative)", callback_data=f"set_neg_{chat_id}_0"),
                    InlineKeyboardButton("-0.33 (1/3rd)", callback_data=f"set_neg_{chat_id}_33")
                ],
                [
                    InlineKeyboardButton("-0.50 (1/2)", callback_data=f"set_neg_{chat_id}_50"),
                    InlineKeyboardButton("-0.25 (1/4th)", callback_data=f"set_neg_{chat_id}_25")
                ]
            ]
            await query.edit_message_text(
                text=f"⏱ समय: *{timer_val}s*\n\n2️⃣ **निगेटिव मार्किंग चुनें:**",
                reply_markup=InlineKeyboardMarkup(neg_keyboard),
                parse_mode="Markdown"
            )

    elif data.startswith("set_neg_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        neg_code = parts[3]
        neg_map = {"0": 0.0, "33": 0.33, "50": 0.50, "25": 0.25}
        neg_val = neg_map.get(neg_code, 0.0)

        if chat_id in pending_setups:
            if user_id != pending_setups[chat_id]["host_id"] and user_id != ADMIN_ID:
                await query.answer("❌ केवल एडमिन ही यह चुन सकते हैं।", show_alert=True)
                return

            pending_setups[chat_id]["negative"] = neg_val
            exp_keyboard = [
                [
                    InlineKeyboardButton("✅ हाँ (Show)", callback_data=f"set_exp_{chat_id}_yes"),
                    InlineKeyboardButton("❌ नहीं (Hide)", callback_data=f"set_exp_{chat_id}_no")
                ]
            ]
            await query.edit_message_text(
                text=f"⏱ समय: *{pending_setups[chat_id]['timer']}s* | निगेटिव: *{neg_val}*\n\n3️⃣ **व्याख्या (Explanation) दिखाना चाहते हैं?**",
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
            neg_val = setup_data["negative"]
            s_exp = setup_data["show_exp"]
            is_private = (query.message.chat.type == "private")

            del pending_setups[chat_id]
            await query.edit_message_text(f"✅ सेटअप पूरा हुआ! (समय: {t_sec}s | निगेटिव: -{neg_val} | व्याख्या: {'हाँ' if s_exp else 'नहीं'})")
            await start_group_quiz(chat_id, q_id, t_sec, neg_val, s_exp, is_private, context)

    elif data.startswith("pdf_"):
        quiz_id = data.replace("pdf_", "")
        await send_quiz_pdf(query.message.chat_id, quiz_id, context)

async def send_quiz_pdf(chat_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    if quiz_id not in all_q or not all_q[quiz_id].get("questions"):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ क्विज़ `{quiz_id}` नहीं मिला।")
        return

    await context.bot.send_message(chat_id=chat_id, text="⏳ असली परीक्षा पेपर जैसी HD बुकलेट PDF तैयार हो रही है...")
    try:
        pdf_buffer = generate_pdf_bytes(all_q[quiz_id])
        safe_filename = f"{all_q[quiz_id].get('title', 'Exam')}_Booklet.pdf".replace(" ", "_")

        await context.bot.send_document(
            chat_id=chat_id,
            document=pdf_buffer,
            filename=safe_filename,
            caption=f"📄 *{all_q[quiz_id]['title']} (Exam Booklet)*\n📌 *JB STUDY POINT | Mob: 8218345167*",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ PDF त्रुटि: {str(e)}")

# --- AUTO QUIZ RUNNER ---
async def start_group_quiz(chat_id, quiz_id, timer_sec, neg_val, show_exp, is_private, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    quiz = all_q[quiz_id]
    total = len(quiz["questions"])

    active_group_quizzes[chat_id] = {
        "quiz_id": quiz_id,
        "index": 0,
        "timer": int(timer_sec),
        "negative": neg_val,
        "show_exp": show_exp,
        "is_private": is_private,
        "users": {},
        "current_msg_id": None,
        "total_q": total,
        "timer_task": None
    }

    start_banner = (
        f"🎯 *टेस्ट शुरू हो रहा है!*\n\n"
        f"📝 टेस्ट: *{quiz['title']}*\n"
        f"❓ कुल प्रश्न: *{total}*\n"
        f"⏱ समय: *{timer_sec}s प्रति प्रश्न*\n"
        f"⚠️ निगेटिव मार्किंग: *{'-' + str(neg_val) if neg_val > 0 else 'नहीं (0)'}*\n\n"
        "⚡ *पहला प्रश्न 2 सेकंड में आ रहा है... तैयार रहें!*"
    )
    await context.bot.send_message(chat_id=chat_id, text=start_banner, parse_mode="Markdown")
    await asyncio.sleep(2)
    await send_next_question(chat_id, context)

async def auto_timer_countdown(chat_id, msg_id, duration, context: ContextTypes.DEFAULT_TYPE):
    try:
        await asyncio.sleep(duration)
        if chat_id in active_group_quizzes:
            sess = active_group_quizzes[chat_id]
            if sess.get("current_msg_id") == msg_id:
                try:
                    await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                await send_next_question(chat_id, context)
    except asyncio.CancelledError:
        pass

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
        context.bot_data[poll_msg.poll.id] = (chat_id, int(q["correct_id"]), idx)
        sess["timer_task"] = asyncio.create_task(auto_timer_countdown(chat_id, poll_msg.message_id, timer_sec, context))
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
            uid = user.id
            name = user.first_name or "Participant"

            if uid not in sess["users"]:
                sess["users"][uid] = {
                    "name": name,
                    "correct": 0,
                    "wrong": 0,
                    "score": 0.0,
                    "wrong_questions": []
                }

            if p_ans.option_ids:
                user_choice = p_ans.option_ids[0]
                if user_choice == correct_id:
                    sess["users"][uid]["correct"] += 1
                    sess["users"][uid]["score"] += 1.0
                else:
                    sess["users"][uid]["wrong"] += 1
                    sess["users"][uid]["score"] -= sess["negative"]
                    all_q = get_all_quizzes()
                    q_data = all_q[sess["quiz_id"]]["questions"][q_idx]
                    sess["users"][uid]["wrong_questions"].append({
                        "q_num": q_idx + 1,
                        "question": q_data["question"],
                        "correct_opt": q_data["options"][correct_id]
                    })

            if sess.get("is_private") is True:
                if sess.get("timer_task") and not sess["timer_task"].done():
                    sess["timer_task"].cancel()
                    asyncio.create_task(trigger_fast_next(chat_id, sess.get("current_msg_id"), context))

async def trigger_fast_next(chat_id, msg_id, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1.5)
    if chat_id in active_group_quizzes:
        sess = active_group_quizzes[chat_id]
        if sess.get("current_msg_id") == msg_id:
            try:
                await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            await send_next_question(chat_id, context)

async def finish_quiz_and_show_ranks(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in active_group_quizzes:
        return

    sess = active_group_quizzes[chat_id]
    all_q = get_all_quizzes()
    quiz = all_q[sess["quiz_id"]]
    total_q = sess["total_q"]
    participants = sess["users"]
    neg_rate = sess["negative"]

    del active_group_quizzes[chat_id]

    if not participants:
        await context.bot.send_message(chat_id=chat_id, text=f"🏁 *टेस्ट समाप्त!*\n📝 *{quiz['title']}*\nकिसी ने उत्तर नहीं दिया।", parse_mode="Markdown")
        return

    sorted_users = sorted(participants.items(), key=lambda x: x[1]["score"], reverse=True)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    leaderboard_lines = []

    highest_score = max(0.0, round(sorted_users[0][1]["score"], 2))
    gen_cut = round(highest_score * 0.75, 2)
    obc_cut = round(highest_score * 0.68, 2)
    sc_cut = round(highest_score * 0.58, 2)

    for rank, (uid, p) in enumerate(sorted_users, 1):
        badge = medals[rank - 1] if rank <= 10 else f"{rank}."
        final_sc = max(0.0, round(p['score'], 2))
        leaderboard_lines.append(f"{badge} *{p['name']}* — {final_sc}/{total_q} अंक (✅{p['correct']} | ❌{p['wrong']})")

        try:
            wrong_review = ""
            if p["wrong_questions"]:
                wrong_review = "\n\n❌ *आपके द्वारा गलत किए गए प्रश्न व सही उत्तर:*\n"
                for w in p["wrong_questions"][:10]:
                    wrong_review += f"• *प्र.{w['q_num']}:* {w['question'][:60]}...\n👉 *सही उत्तर:* `{w['correct_opt']}`\n"

            student_card = (
                f"📋 *आपका परीक्षा परिणाम (Detailed Scorecard)*\n\n"
                f"📝 टेस्ट: *{quiz['title']}*\n"
                f"🏆 रैंक: *#{rank}*\n"
                f"✅ सही: *{p['correct']}* | ❌ गलत: *{p['wrong']}*\n"
                f"🎯 कुल प्राप्तांक: *{final_sc} / {total_q}*\n"
                f"{wrong_review}\n\n"
                f"💐 *JB STUDY POINT (Mob: 8218345167)*"
            )
            await context.bot.send_message(chat_id=uid, text=student_card, parse_mode="Markdown")
        except Exception:
            pass

    rank_list_text = "\n".join(leaderboard_lines)
    cutoff_card = (
        f"\n\n📊 *अनुमानित कट-ऑफ (Estimated Cut-Off):*\n"
        f"• UR: *{gen_cut}* | OBC: *{obc_cut}* | SC: *{sc_cut}*"
    )

    final_msg = (
        f"🏁 *टेस्ट परिणाम (Final Result)* 🏁\n\n"
        f"📝 टेस्ट: *{quiz['title']}*\n"
        f"👥 कुल प्रतिभागी: *{len(sorted_users)}*\n\n"
        f"🏆 *रैंक व लीडरबोर्ड:*\n\n{rank_list_text}{cutoff_card}"
    )
    await context.bot.send_message(chat_id=chat_id, text=final_msg, parse_mode="Markdown")

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
    app.add_handler(CommandHandler("omr", omr_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_restore))
    app.add_handler(MessageHandler(filters.POLL, handle_incoming_poll))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    app.run_polling()

if __name__ == "__main__":
    main()
