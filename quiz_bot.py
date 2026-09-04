from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes

TOKEN = "5096262921:AAEhBO0LSfPowL0PAhui01I2jC0rcIA4M-w"

QUESTIONS = [
    {
        "question": "सिंधु घाटी सभ्यता का प्रमुख बंदरगाह कौन सा था?",
        "options": ["कालीबंगा", "लोथल", "रोपड़", "मोहनजोदड़ो"],
        "correct_id": 1
    },
    {
        "question": "अशोक के अधिकांश शिलालेख किस लिपि में हैं?",
        "options": ["ब्राह्मी", "खरोष्ठी", "अरामी", "देवनागरी"],
        "correct_id": 0
    }
]

user_scores = {}
user_question_index = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_scores[user_id] = 0
    user_question_index[user_id] = 0
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
            text=f"🏁 **टेस्ट समाप्त!**\n\nआपका कुल स्कोर: **{score} / {total}**\n\nधन्यवाद!"
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

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(PollAnswerHandler(handle_poll_answer))

if __name__ == "__main__":
    app.run_polling()
  
