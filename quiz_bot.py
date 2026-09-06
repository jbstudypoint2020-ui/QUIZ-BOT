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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS.strip())
            server.send_message(msg)
    except Exception as e:
        print(f"Email error: {e}")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="hi"><head><meta charset="UTF-8"><title>JB STUDY POINT</title></head>
<body style="font-family:sans-serif;text-align:center;padding:50px;">
<h2>JB STUDY POINT - Quiz Bot Active</h2>
<p>आपका बॉट और वेब सर्वर सफलतापूर्वक चल रहा है।</p>
</body></html>"""

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

def generate_pdf_bytes(quiz_data):
    PAGE_W, PAGE_H = 2480, 3508
    img = Image.new("RGB", (PAGE_W, PAGE_H), "#FFFDF5")
    draw = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(FONT_PATH, 40)
    title = str(quiz_data.get('title', 'MOCK TEST'))
    draw.text((200, 200), title, font=f_title, fill="#8B0000")
    pdf_io = io.BytesIO()
    img.save(pdf_io, format="PDF", resolution=300.0)
    pdf_io.seek(0)
    return pdf_io

async def post_init(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("create", "Create a new quiz"),
        BotCommand("myquizzes", "View quizzes"),
        BotCommand("omr", "Download OMR Sheet"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"नमस्ते {user.first_name}! JB STUDY POINT बॉट सक्रिय है।")

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_q = get_all_quizzes()
    await update.message.reply_text(f"कुल क्विज़: {len(all_q)}")

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myquizzes", my_quizzes))
    app.run_polling()

if __name__ == "__main__":
    main()
