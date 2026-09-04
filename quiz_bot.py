import json
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

TOKEN = "5096262921:AAFHINLj8SvFdPOQEJLVUV-13OTklEY6h0"
ADMIN_ID = 1141231956

DB_FILE = "questions.json"

def load_questions():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {
            "question": "सिंधु घाटी सभ्यता का प्रमुख बंदरगाह कौन सा था?",
            "options": ["कालीबंगा", "लोथल", "रोपड़", "मोहनजोदड़ो"],
            "correct_id": 1
        }
    ]

def save_questions(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

QUESTIONS = load_questions()

user_scores = {}
user_question_index = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_scores[user_id] = 0
    user_question_index[user_id] = 0
    
    if not QUESTIONS:
        await update.message.reply_text("वर्तमान में कोई प्रश्न उपलब्ध नहीं है।")
        return

    await update.message.reply_text("क्विज़ शुरू हो रहा है! शुभकामनाएँ।")
    await send_next_question(update.effective_chat.id, user_id, context)

async def send_next_question(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    index = user_question_index[user_id]
    if index < len(QUESTIONS):
        q = QUESTIONS[index]
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=q["question"],
            options=q["options"],
            type="quiz",
            correct_option_id=q["correct_id"],
            is_anonymous=False,
            explanation=""
        )
        context.bot_data[message.poll.id] = (user_id, chat_id, q["correct_id"])
    else:
        score = user_scores.get(user_id, 0)
        total = len(QUESTIONS)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🏁 *टेस्ट समाप्त!*\n\nआपका कुल स्कोर: *{score} / {total}*\n\nधन्यवाद!",
            parse_mode="Markdown"
        )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    
    if poll_id in context.bot_data:
        user_id, chat_id, correct_id = context.bot_data[poll_id]
        selected_option = poll_answer.option_ids[0]
        
        if selected_option == correct_id:
            user_scores[user_id] = user_scores.get(user_id, 0) + 1
            
        user_question_index[user_id] += 1
        await send_next_question(chat_id, user_id, context)

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = (
        "➕ *नया प्रश्न जोड़ने का तरीका:*\n\n"
        "इस प्रारूप में लिखकर भेजें (पाइप `|` चिन्ह के साथ):\n\n"
        "`प्रश्न | विकल्प 1 | विकल्प 2 | विकल्प 3 | विकल्प 4 | सही विकल्प नंबर (1-4)`\n\n"
        "*उदाहरण:*\n"
        "`अशोक के अधिकांश शिलालेख किस लिपि में हैं? | ब्राह्मी | खरोष्ठी | अरामी | देवनागरी | 1`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def receive_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text
    if "|" not in text:
        return

    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 6:
        await update.message.reply_text("❌ गलत प्रारूप! 6 भाग होने चाहिए: प्रश्न | 4 विकल्प | सही विकल्प संख्या (1-4)")
        return

    q_text = parts[0]
    options = parts[1:5]
    try:
        correct_num = int(parts[5])
        if correct_num < 1 or correct_num > 4:
            raise ValueError()
        correct_id = correct_num - 1
    except ValueError:
        await update.message.reply_text("❌ सही विकल्प संख्या केवल 1, 2, 3 या 4 में से एक होनी चाहिए।")
        return

    new_q = {
        "question": q_text,
        "options": options,
        "correct_id": correct_id
    }
    QUESTIONS.append(new_q)
    save_questions(QUESTIONS)

    await update.message.reply_text(f"✅ *प्रश्न सफलतापूर्वक जुड़ गया!*\nकुल प्रश्न संख्या: {len(QUESTIONS)}", parse_mode="Markdown")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_command))
app.add_handler(PollAnswerHandler(handle_poll_answer))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), receive_question_text))

if __name__ == "__main__":
    app.run_polling()
    
