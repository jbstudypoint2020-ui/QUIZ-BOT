import json
import os
import random
import string
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
    ContextTypes,
    ConversationHandler
)

TOKEN = "5096262921:AAHDRkHesbzcUs6BvDduK3IUEfnrFr_K0dE"
BOT_USERNAME = "JBSTUDYPOINT_BOT"  # अपने बॉट का यूज़रनेम (बिना @ के)
ADMIN_ID = 1141231956

DB_FILE = "quizzes.json"

# क्विज़ डेटाबेस लोड/सेव करना
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

# स्टेट्स
WAIT_TITLE, WAIT_QUESTION = range(2)
user_states = {}

def generate_quiz_id():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

# मेन्यू सेटअप
async def post_init(application):
    commands = [
        BotCommand("start", "Start the bot / check if alive"),
        BotCommand("create", "Start creating a quiz"),
        BotCommand("features", "View all features of the bot"),
    ]
    await application.bot.set_my_commands(commands)

# /start कमांड
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # यदि किसी लिंक से स्टार्ट हुआ हो (जैसे deep linking: /start PLAY_ID)
    if args and args[0].startswith("PLAY_"):
        quiz_id = args[0].replace("PLAY_", "")
        await start_quiz_session(update.effective_chat.id, user.id, quiz_id, context)
        return

    text = (
        f"🇮🇳 *नमस्ते {user.first_name}!*\n\n"
        "यह एक एडवांस क्विज़ सिस्टम है।\n"
        "• नया क्विज़ बनाने के लिए: /create दबाएं\n"
        "• फीचर्स देखने के लिए: /features दबाएं"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# /features कमांड
async def features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✨ *बॉट के मुख्य फीचर्स:*\n\n"
        "1. 🎯 *बिना शेयर बटन और बिना उत्तर व्याख्या के निष्पक्ष परीक्षा*\n"
        "2. ➕ *ग्रुप में जोड़कर लाइव क्विज़ कराने की सुविधा*\n"
        "3. 🎮 *प्रैक्टिस और एग्जाम मोड*\n"
        "4. 📊 *तुरंत स्कोरकार्ड और परिणाम*\n"
        "5. 📝 *खुद का टेस्ट कभी भी बनाने की सुविधा*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# /create कमांड - नया क्विज़ बनाना शुरू करना
async def create_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ केवल एडमिन ही नया क्विज़ बना सकते हैं।")
        return ConversationHandler.END

    await update.message.reply_text("📝 *नया क्विज़ बनाएँ*\n\nकृपया अपने क्विज़ का नाम (Title) लिखकर भेजें:", parse_mode="Markdown")
    return WAIT_TITLE

async def get_quiz_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    quiz_id = generate_quiz_id()
    
    QUIZZES[quiz_id] = {
        "title": title,
        "creator": update.effective_user.first_name,
        "type": "Free",
        "questions": []
    }
    context.user_data["current_quiz_id"] = quiz_id

    help_msg = (
        f"✅ क्विज़ *'{title}'* बन गया है!\n"
        f"🆔 ID: `{quiz_id}`\n\n"
        "अब इस प्रारूप में प्रश्न भेजें (एक-एक करके):\n"
        "`प्रश्न | विकल्प 1 | विकल्प 2 | विकल्प 3 | विकल्प 4 | सही नंबर (1-4)`\n\n"
        "जब सारे प्रश्न जुड़ जाएं, तो */done* लिखकर भेजें।"
    )
    await update.message.reply_text(help_msg, parse_mode="Markdown")
    return WAIT_QUESTION

async def get_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    quiz_id = context.user_data.get("current_quiz_id")

    if "|" not in text:
        await update.message.reply_text("❌ प्रारूप गलत है! कृपया `प्रश्न | विक 1 | विक 2 | विक 3 | विक 4 | सही (1-4)` में भेजें।")
        return WAIT_QUESTION

    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 6:
        await update.message.reply_text("❌ ठीक 6 भाग होने चाहिए (प्रश्न + 4 विकल्प + सही उत्तर)।")
        return WAIT_QUESTION

    try:
        correct_num = int(parts[5])
        if correct_num < 1 or correct_num > 4:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ सही उत्तर 1 से 4 के बीच होना चाहिए।")
        return WAIT_QUESTION

    q_data = {
        "question": parts[0],
        "options": parts[1:5],
        "correct_id": correct_num - 1
    }
    QUIZZES[quiz_id]["questions"].append(q_data)
    save_quizzes(QUIZZES)

    total_q = len(QUIZZES[quiz_id]["questions"])
    await update.message.reply_text(f"✅ प्रश्न #{total_q} जुड़ गया! अगला प्रश्न भेजें या समाप्त करने के लिए */done* भेजें।", parse_mode="Markdown")
    return WAIT_QUESTION

async def create_quiz_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz_id = context.user_data.get("current_quiz_id")
    if not quiz_id or quiz_id not in QUIZZES:
        await update.message.reply_text("कोई क्विज़ एक्टिव नहीं था।")
        return ConversationHandler.END

    quiz = QUIZZES[quiz_id]
    total_q = len(quiz["questions"])

    # जैसा आपके स्क्रीनशॉट में कार्ड है, बिल्कुल वैसा लेआउट:
    card_text = (
        f"🇮🇳 *Advance Quiz Bot*\n"
        f"🆔 **ID:** `{quiz_id}`\n"
        f"🏷 **Type:** {quiz['type']}\n"
        f"📢 **Promo:** None\n"
        f"👤 **Creator:** {quiz['creator']}\n"
        f"📚 **Total Questions:** {total_q}\n"
        f"📝 **Name:** {quiz['title']}"
    )

    bot_info = await context.bot.get_me()
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=PLAY_{quiz_id}&text={quiz['title']}"
    add_group_url = f"https://t.me/{bot_info.username}?startgroup=PLAY_{quiz_id}"

    keyboard = [
        [InlineKeyboardButton("▶️ Start", callback_data=f"play_{quiz_id}")],
        [InlineKeyboardButton("➕ Add to Group", url=add_group_url)],
        [InlineKeyboardButton("📩 Share", url=share_url)],
        [
            InlineKeyboardButton("🎮 Play (Practice)", callback_data=f"play_{quiz_id}"),
            InlineKeyboardButton("🎯 Play (Exam)", callback_data=f"play_{quiz_id}")
        ]
    ]

    await update.message.reply_text(card_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ConversationHandler.END

# क्विज़ खेलना शुरू करना
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("play_"):
        quiz_id = data.replace("play_", "")
        await start_quiz_session(query.message.chat_id, query.from_user.id, quiz_id, context)

async def start_quiz_session(chat_id, user_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    if quiz_id not in QUIZZES or not QUIZZES[quiz_id]["questions"]:
        await context.bot.send_message(chat_id=chat_id, text="❌ यह क्विज़ उपलब्ध नहीं है या इसमें कोई प्रश्न नहीं हैं।")
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
        # टेस्ट समाप्त
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
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_quiz_start)],
        states={
            WAIT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quiz_title)],
            WAIT_QUESTION: [
                CommandHandler("done", create_quiz_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_quiz_question)
            ]
        },
        fallbacks=[CommandHandler("done", create_quiz_done)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("features", features))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    app.run_polling()

if __name__ == "__main__":
    main()
    
