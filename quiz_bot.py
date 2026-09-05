import json
import os
import random
import re
import string
import io
import asyncio
import threading
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
    text = re.sub(r"^\s*\[\d+/\d+\]\s*", "", raw_text)
    text = re.sub(r"^\s*(Q|q)?\d+[\.\)\-:]\s*", "", text)
    return text.strip()

# ----------------- WEB DASHBOARD (QUIZ CREATOR WEB) -----------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JB STUDY POINT - Quiz Creator Web</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; color: #1c1e21; }
  .box { max-width: 650px; margin: 0 auto; background: #fff; padding: 22px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
  h2 { color: #8B0000; text-align: center; margin-top: 0; margin-bottom: 5px; }
  p.subtitle { text-align: center; color: #65676b; margin-top: 0; margin-bottom: 20px; font-size: 14px; }
  .field { margin-bottom: 15px; }
  label { font-weight: 600; font-size: 13px; display: block; margin-bottom: 5px; color: #333; }
  input[type="text"], textarea, select { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #ccd0d5; border-radius: 6px; font-size: 14px; }
  textarea { resize: vertical; }
  .card-q { background: #fafafa; border: 1px solid #e4e6eb; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
  .q-title { font-weight: bold; color: #1a237e; margin-bottom: 8px; font-size: 14px; }
  .btn { display: block; width: 100%; background: #8B0000; color: #fff; border: none; padding: 12px; font-size: 16px; font-weight: bold; border-radius: 6px; cursor: pointer; }
  .btn:hover { background: #6b0000; }
  .btn-add { background: #0D47A1; margin-bottom: 15px; }
  .btn-add:hover { background: #082d6b; }
  .opt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
</style>
<script>
let qCount = 1;
function addQuestion() {
  qCount++;
  const div = document.createElement('div');
  div.className = 'card-q';
  div.id = 'qc_' + qCount;
  div.innerHTML = `
    <div class="q-title">प्रश्न ` + qCount + `</div>
    <input type="text" name="q_text_` + qCount + `" placeholder="यहाँ प्रश्न लिखें..." required>
    <div class="opt-grid">
      <input type="text" name="q_optA_` + qCount + `" placeholder="विकल्प A" required>
      <input type="text" name="q_optB_` + qCount + `" placeholder="विकल्प B" required>
      <input type="text" name="q_optC_` + qCount + `" placeholder="विकल्प C" required>
      <input type="text" name="q_optD_` + qCount + `" placeholder="विकल्प D" required>
    </div>
    <div style="margin-top: 8px; display: flex; gap: 10px; align-items: center;">
      <label style="margin:0; font-size:12px;">सही उत्तर:</label>
      <select name="q_ans_` + qCount + `" style="width: auto;">
        <option value="0">विकल्प A</option>
        <option value="1">विकल्प B</option>
        <option value="2">विकल्प C</option>
        <option value="3">विकल्प D</option>
      </select>
    </div>
  `;
  document.getElementById('question-list').appendChild(div);
  document.getElementById('total_questions').value = qCount;
}
</script>
</head>
<body>
<div class="box">
  <h2>JB STUDY POINT</h2>
  <p class="subtitle">ऑनलाइन क्विज़ व टेस्ट क्रिएटर वेब पोर्टल</p>
  <form action="/save_quiz" method="POST">
    <input type="hidden" name="total_questions" id="total_questions" value="1">
    
    <div class="field">
      <label>टेस्ट का नाम (Test Title):</label>
      <input type="text" name="title" value="इतिहास टेस्ट" required>
    </div>

    <div class="field">
      <label>क्रिएटर / संस्थान का नाम:</label>
      <input type="text" name="creator" value="Dr. Dev Kumar | JB STUDY POINT" required>
    </div>

    <div id="question-list">
      <div class="card-q" id="qc_1">
        <div class="q-title">प्रश्न 1</div>
        <input type="text" name="q_text_1" placeholder="यहाँ प्रश्न लिखें..." required>
        <div class="opt-grid">
          <input type="text" name="q_optA_1" placeholder="विकल्प A" required>
          <input type="text" name="q_optB_1" placeholder="विकल्प B" required>
          <input type="text" name="q_optC_1" placeholder="विकल्प C" required>
          <input type="text" name="q_optD_1" placeholder="विकल्प D" required>
        </div>
        <div style="margin-top: 8px; display: flex; gap: 10px; align-items: center;">
          <label style="margin:0; font-size:12px;">सही उत्तर:</label>
          <select name="q_ans_1" style="width: auto;">
            <option value="0">विकल्प A</option>
            <option value="1">विकल्प B</option>
            <option value="2">विकल्प C</option>
            <option value="3">विकल्प D</option>
          </select>
        </div>
      </div>
    </div>

    <button type="button" class="btn btn-add" onclick="addQuestion()">➕ अगला प्रश्न जोड़ें (Add Question)</button>
    <button type="submit" class="btn">💾 टेस्ट पब्लिश करें (Publish to Telegram)</button>
  </form>
</div>
</body>
</html>
"""

class QuizCreatorServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

    def do_POST(self):
        if self.path == "/save_quiz":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            parsed = parse_qs(post_data)

            title = parsed.get("title", ["इतिहास टेस्ट"])[0]
            creator = parsed.get("creator", [DEFAULT_CREATOR])[0]
            total_q = int(parsed.get("total_questions", [1])[0])

            questions = []
            for idx in range(1, total_q + 1):
                q_text = parsed.get(f"q_text_{idx}", [""])[0].strip()
                if not q_text:
                    continue
                oa = parsed.get(f"q_optA_{idx}", [""])[0].strip()
                ob = parsed.get(f"q_optB_{idx}", [""])[0].strip()
                oc = parsed.get(f"q_optC_{idx}", [""])[0].strip()
                od = parsed.get(f"q_optD_{idx}", [""])[0].strip()
                ans = int(parsed.get(f"q_ans_{idx}", [0])[0])

                questions.append({
                    "question": q_text,
                    "options": [oa, ob, oc, od],
                    "correct_id": ans,
                    "explanation": ""
                })

            if questions:
                q_id = generate_quiz_id()
                all_q = get_all_quizzes()
                all_q[q_id] = {
                    "id": q_id,
                    "title": title,
                    "creator": creator,
                    "type": "free",
                    "promo": "None",
                    "timer": "20s",
                    "questions": questions
                }
                save_all_quizzes(all_q)

                resp = f"""
                <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>body {{ font-family: sans-serif; text-align: center; padding: 40px 15px; background: #f0f2f5; }}
                .card {{ max-width: 480px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                h2 {{ color: #2e7d32; }}
                .code {{ background: #eee; padding: 8px 16px; border-radius: 6px; font-weight: bold; font-size: 20px; }}
                a {{ display: inline-block; margin-top: 20px; text-decoration: none; background: #8B0000; color: #fff; padding: 10px 20px; border-radius: 6px; }}
                </style></head><body>
                <div class="card">
                  <h2>✅ टेस्ट सफलतापूर्वक पब्लिश हुआ!</h2>
                  <p>टेस्ट का नाम: <b>{title}</b></p>
                  <p>कुल प्रश्न: <b>{len(questions)}</b></p>
                  <p>आपकी Quiz ID है:</p>
                  <div class="code">{q_id}</div>
                  <p style="font-size:13px; color:#666; margin-top:15px;">टेलीग्राम में चलायें: <code>/play {q_id}</code></p>
                  <a href="/">नया टेस्ट बनाएँ</a>
                </div></body></html>
                """
            else:
                resp = "<html><body><h3>कोई प्रश्न दर्ज नहीं किया गया।</h3><a href='/'>वापस जाएँ</a></body></html>"

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(resp.encode("utf-8"))

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), QuizCreatorServer)
    server.serve_forever()

# ----------------- 2-COLUMN BOOKLET PDF GENERATOR -----------------

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

            sub_b = draw.textbbox((0, 0), "Paper - II : Practice Booklet", font=f_sub)
            draw.text(((PAGE_W - (sub_b[2] - sub_b[0])) // 2, y_offset), "Paper - II : Practice Booklet", font=f_sub, fill="#555555")
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
            draw.text((MARGIN_X + 20, y_offset + 58), "3. परीक्षा कक्ष में मोबाइल फोन या किसी भी प्रकार का उपकरण वर्जित है।", font=f_inst, fill="#333333")
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

# ----------------- TELEGRAM BOT ENGINE -----
