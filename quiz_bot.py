import asyncio
import io
import json
import os
import random
import re
import smtplib
import string
import threading
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import HTTPServer, BaseHTTPRequestHandler

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    MessageHandler,
    filters,
    ContextTypes,
)


# ============================================================
# CONFIGURATION
# ============================================================

# IMPORTANT:
# Never put your real Telegram token directly in this file.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

ADMIN_ID = int(os.environ.get("ADMIN_ID", "1141231956"))

DB_FILE = os.environ.get("DB_FILE", "quizzes.json")

DEFAULT_CREATOR = "JB STUDY POINT"

# Gmail is optional.
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(CURRENT_DIR, "hindi.ttf")


if not TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN environment variable is missing."
    )


# ============================================================
# RUNTIME DATA
# ============================================================

creator_sessions = {}
pending_setups = {}
active_group_quizzes = {}


# ============================================================
# DATABASE
# ============================================================

def get_all_quizzes():
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except (OSError, json.JSONDecodeError) as e:
        print(f"Database read error: {e}")
        return {}


def save_all_quizzes(data):
    temp_file = DB_FILE + ".tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp_file, DB_FILE)

    except OSError as e:
        print(f"Database save error: {e}")


# ============================================================
# QUIZ ID
# ============================================================

def generate_quiz_id():

    return (
        "GGN"
        + "".join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=6
            )
        )
    )


# ============================================================
# TEXT CLEANER
# ============================================================

def clean_question_text(raw_text):

    if not raw_text:
        return ""

    text = str(raw_text)

    patterns = [
        r"\[\s*\d+\s*/\s*\d+\s*\]",
        r"⏱\s*\d+s?",
        r"\d+s\s*\|",
        r"\[\s*\d+s\s*\]",
        r"\[.*?s.*?\]",
        r"^\s*\[\s*\d+\s*/\s*\d+\s*\]\s*",
        r"^\s*(?:Q|q|प्रश्न)?\s*\d+[\.\)\-:]\s*",
        r"^\s*\[\s*\d+\s*\]\s*",
        r"^\s*\(\s*\d+\s*\)\s*",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text)

    return text.strip()


# ============================================================
# QUIZ VALIDATION
# ============================================================

def validate_quiz(quiz):

    questions = quiz.get("questions", [])

    if not questions:
        return False, "कम-से-कम 1 प्रश्न होना चाहिए।"

    for number, question in enumerate(questions, 1):

        question_text = question.get("question", "").strip()

        options = question.get("options", [])

        correct_id = question.get("correct_id")

        if not question_text:
            return False, f"प्रश्न {number} खाली है।"

        if not isinstance(options, list):
            return False, f"प्रश्न {number} के options गलत हैं।"

        if not 2 <= len(options) <= 10:
            return False, (
                f"प्रश्न {number} में "
                f"2 से 10 options होने चाहिए।"
            )

        if not isinstance(correct_id, int):
            return False, (
                f"प्रश्न {number} का correct answer गलत है।"
            )

        if correct_id < 0 or correct_id >= len(options):
            return False, (
                f"प्रश्न {number} का correct option invalid है।"
            )

    return True, ""


# ============================================================
# GMAIL BACKUP
# ============================================================

def send_quiz_email_backup(
    quiz_title,
    quiz_id,
    quiz_dict
):

    if not GMAIL_USER or not GMAIL_PASS:

        print(
            "Email backup skipped. "
            "GMAIL_USER / GMAIL_APP_PASSWORD not configured."
        )

        return

    try:

        msg = MIMEMultipart()

        msg["From"] = GMAIL_USER
        msg["To"] = GMAIL_USER

        msg["Subject"] = (
            f"JB STUDY POINT Backup: "
            f"{quiz_title} ({quiz_id})"
        )

        body = (
            "JB STUDY POINT\n\n"
            "Quiz Backup\n\n"
            f"Quiz Title: {quiz_title}\n"
            f"Quiz ID: {quiz_id}\n"
        )

        msg.attach(
            MIMEText(
                body,
                "plain",
                "utf-8"
            )
        )

        json_data = json.dumps(
            quiz_dict,
            ensure_ascii=False,
            indent=2
        ).encode("utf-8")

        attachment = MIMEApplication(
            json_data,
            _subtype="json"
        )

        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"{quiz_id}.json"
        )

        msg.attach(attachment)

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=30
        ) as server:

            server.login(
                GMAIL_USER,
                GMAIL_PASS
            )

            server.send_message(msg)

        print(
            f"Email backup sent successfully: {quiz_id}"
        )

    except Exception as e:

        print(
            f"Email backup error: {e}"
        )


# ============================================================
# FONT
# ============================================================

def get_font(size):

    if os.path.exists(FONT_PATH):

        try:
            return ImageFont.truetype(
                FONT_PATH,
                size
            )

        except Exception as e:

            print(
                f"Font loading error: {e}"
            )

    return ImageFont.load_default()


# ============================================================
# PDF GENERATOR
# ============================================================

def generate_pdf_bytes(quiz_data):

    PAGE_W = 2480
    PAGE_H = 3508

    MARGIN_X = 140
    COL_GAP = 90

    COL_W = (
        PAGE_W
        - (2 * MARGIN_X)
        - COL_GAP
    ) // 2

    f_sub = get_font(24)
    f_title = get_font(40)
    f_meta = get_font(22)
    f_instr = get_font(20)
    f_q = get_font(26)
    f_opt = get_font(24)
    f_ans_title = get_font(50)
    f_key = get_font(28)

    title = str(
        quiz_data.get(
            "title",
            "MOCK TEST"
        )
    )

    questions = quiz_data.get(
        "questions",
        []
    )

    # --------------------------------------------------------
    # Text wrapping
    # --------------------------------------------------------

    def wrap_text(
        text,
        font,
        max_width,
        draw
    ):

        words = str(text).split()

        if not words:
            return [""]

        lines = []
        current = ""

        for word in words:

            candidate = (
                f"{current} {word}"
            ).strip()

            bbox = draw.textbbox(
                (0, 0),
                candidate,
                font=font
            )

            width = (
                bbox[2] - bbox[0]
            )

            if width <= max_width:

                current = candidate

            else:

                if current:
                    lines.append(
                        current
                    )

                current = word

        if current:
            lines.append(
                current
            )

        return lines

    # --------------------------------------------------------
    # Dummy drawing
    # --------------------------------------------------------

    dummy_img = Image.new(
        "RGB",
        (PAGE_W, PAGE_H),
        "#FFFDF5"
    )

    dummy_draw = ImageDraw.Draw(
        dummy_img
    )

    option_labels = [
        "(a)",
        "(b)",
        "(c)",
        "(d)",
        "(e)",
        "(f)",
        "(g)",
        "(h)",
        "(i)",
        "(j)",
    ]

    question_blocks = []
    answer_keys = []

    # --------------------------------------------------------
    # Prepare questions
    # --------------------------------------------------------

    for number, question in enumerate(
        questions,
        1
    ):

        clean_question = (
            clean_question_text(
                question.get(
                    "question",
                    ""
                )
            )
        )

        question_lines = wrap_text(
            f"{number}. {clean_question}",
            f_q,
            COL_W,
            dummy_draw
        )

        option_items = []

        for option_index, option in enumerate(
            question.get(
                "options",
                []
            )
        ):

            if option_index < len(
                option_labels
            ):

                label = option_labels[
                    option_index
                ]

            else:

                label = (
                    f"({option_index + 1})"
                )

            clean_option = (
                clean_question_text(
                    option
                )
            )

            option_lines = wrap_text(
                f"{label} {clean_option}",
                f_opt,
                COL_W - 30,
                dummy_draw
            )

            option_items.append(
                option_lines
            )

        correct_id = int(
            question.get(
                "correct_id",
                0
            )
        )

        if correct_id < len(
            option_labels
        ):

            correct_label = (
                option_labels[
                    correct_id
                ]
            )

        else:

            correct_label = (
                f"({correct_id + 1})"
            )

        answer_keys.append(
            (
                str(number),
                correct_label
            )
        )

        total_option_lines = sum(
            len(lines)
            for lines in option_items
        )

        block_height = (
            len(question_lines) * 40
            + total_option_lines * 34
            + 55
        )

        question_blocks.append(
            {
                "q_lines": question_lines,
                "opt_items": option_items,
                "block_h": block_height,
            }
        )

    # --------------------------------------------------------
    # Page creation
    # --------------------------------------------------------

    def create_page(
        later=False
    ):

        img = Image.new(
            "RGB",
            (PAGE_W, PAGE_H),
            "#FFFDF5"
        )

        draw = ImageDraw.Draw(img)

        draw.rectangle(
            [
                80,
                80,
                PAGE_W - 80,
                PAGE_H - 80
            ],
            outline="#8B0000",
            width=6
        )

        draw.rectangle(
            [
                95,
                95,
                PAGE_W - 95,
                PAGE_H - 95
            ],
            outline="#DAA520",
            width=3
        )

        if later:

            header_text = (
                f"JB STUDY POINT | {title}"
            )

        else:

            header_text = (
                "JB STUDY POINT "
                "YOUTUBE CHANNEL"
            )

        draw.text(
            (120, 105),
            header_text,
            font=f_sub,
            fill="#8B0000"
        )

        draw.text(
            (PAGE_W - 520, 105),
            "Mob: 8218345167",
            font=f_sub,
            fill="#000000"
        )

        mid_x = PAGE_W // 2

        draw.line(
            [
                (mid_x, 140),
                (mid_x, PAGE_H - 140)
            ],
            fill="#B0C4DE",
            width=3
        )

        # Watermark
        try:

            watermark = Image.new(
                "RGBA",
                (PAGE_W, PAGE_H),
                (255, 255, 255, 0)
            )

            watermark_draw = ImageDraw.Draw(
                watermark
            )

            watermark_font = get_font(
                150
            )

            watermark_draw.text(
                (
                    PAGE_W // 2 - 580,
                    PAGE_H // 2 - 90
                ),
                "JB STUDY POINT",
                font=watermark_font,
                fill=(180, 120, 120, 45)
            )

            watermark = watermark.rotate(
                30,
                resample=Image.Resampling.BICUBIC
            )

            img = Image.alpha_composite(
                img.convert("RGBA"),
                watermark
            ).convert("RGB")

            draw = ImageDraw.Draw(img)

        except Exception:
            pass

        return img, draw

    # --------------------------------------------------------
    # First page
    # --------------------------------------------------------

    current_img, current_draw = (
        create_page(False)
    )

    current_column = 0
    current_y = 450

    page_limit = PAGE_H - 140

    # Header
    current_draw.rectangle(
        [
            120,
            140,
            PAGE_W - 120,
            215
        ],
        fill="#8B0000"
    )

    title_box = current_draw.textbbox(
        (0, 0),
        title,
        font=f_title
    )

    title_width = (
        title_box[2] - title_box[0]
    )

    current_draw.text(
        (
            (PAGE_W - title_width) // 2,
            155
        ),
        title,
        font=f_title,
        fill="#FFFFFF"
    )

    current_draw.rectangle(
        [
            120,
            230,
            PAGE_W - 120,
            310
        ],
        outline="#444444",
        width=2
    )

    current_draw.text(
        (140, 245),
        "TEST NO.: 01",
        font=f_meta,
        fill="#000000"
    )

    current_draw.text(
        (450, 245),
        "CANDIDATE NAME: ____________________",
        font=f_meta,
        fill="#000000"
    )

    current_draw.text(
        (1350, 245),
        "ROLL NO.: ________________",
        font=f_meta,
        fill="#000000"
    )

    current_draw.rectangle(
        [
            120,
            325,
            PAGE_W - 120,
            420
        ],
        fill="#F9F9F9",
        outline="#B0C4DE",
        width=2
    )

    current_draw.text(
        (140, 335),
        "INSTRUCTIONS / निर्देश:",
        font=f_meta,
        fill="#8B0000"
    )

    current_draw.text(
        (140, 365),
        "1. सभी प्रश्नों को ध्यानपूर्वक हल करें।",
        font=f_instr,
        fill="#333333"
    )

    current_draw.text(
        (140, 390),
        "2. सही विकल्प का चयन करें।",
        font=f_instr,
        fill="#333333"
    )

    pages = []

    # --------------------------------------------------------
    # Draw questions
    # --------------------------------------------------------

    for block in question_blocks:

        block_height = block[
            "block_h"
        ]

        if (
            current_y + block_height
            > page_limit
        ):

            if current_column == 0:

                current_column = 1
                current_y = 160

            else:

                pages.append(
                    current_img
                )

                current_img, current_draw = (
                    create_page(True)
                )

                current_column = 0
                current_y = 160

        if current_column == 0:

            column_x = MARGIN_X

        else:

            column_x = (
                MARGIN_X
                + COL_W
                + COL_GAP
            )

        question_box_height = (
            len(block["q_lines"])
            * 40
            + 10
        )

        current_draw.rectangle(
            [
                column_x - 10,
                current_y - 4,
                column_x + COL_W + 10,
                current_y
                + question_box_height
            ],
            fill="#EAE6FF",
            outline="#7B68EE",
            width=2
        )

        for line in block["q_lines"]:

            current_draw.text(
                (column_x, current_y),
                line,
                font=f_q,
                fill="#000080"
            )

            current_y += 40

        current_y += 6

        for option_lines in block[
            "opt_items"
        ]:

            for line in option_lines:

                current_draw.text(
                    (
                        column_x + 15,
                        current_y
                    ),
                    line,
                    font=f_opt,
                    fill="#111111"
                )

                current_y += 34

        current_y += 24

    pages.append(
        current_img
    )

    # ========================================================
    # ANSWER KEY
    # ========================================================

    answer_per_page = 45

    for start in range(
        0,
        len(answer_keys),
        answer_per_page
    ):

        answer_img, answer_draw = (
            create_page(True)
        )

        answer_y = 160

        answer_draw.text(
            (800, answer_y),
            "ANSWER KEY / उत्तर तालिका",
            font=f_ans_title,
            fill="#8B0000"
        )

        answer_y += 80

        answer_draw.text(
            (900, answer_y),
            (
                f"{title} | "
                f"Total: {len(questions)} Questions"
            ),
            font=f_sub,
            fill="#333333"
        )

        answer_y += 70

        columns = 5

        usable_width = (
            PAGE_W
            - (2 * MARGIN_X)
            - 80
        )

        column_width = (
            usable_width // columns
        )

        start_x = MARGIN_X + 40

        current_answers = answer_keys[
            start:start + answer_per_page
        ]

        for index, (
            question_number,
            answer
        ) in enumerate(
            current_answers
        ):

            column = index % columns
            row = index // columns

            x = (
                start_x
                + column * column_width
            )

            y = (
                answer_y
                + row * 70
            )

            answer_draw.rectangle(
                [
                    x,
                    y,
                    x + column_width - 25,
                    y + 55
                ],
                outline="#8B0000",
                fill="#FFFFFF",
                width=2
            )

            answer_draw.text(
                (x + 12, y + 10),
                f"Q.{question_number}",
                font=f_key,
                fill="#000000"
            )

            answer_draw.text(
                (
                    x + column_width - 80,
                    y + 10
                ),
                answer,
                font=f_key,
                fill="#8B0000"
            )

        pages.append(
            answer_img
        )

    # --------------------------------------------------------
    # Convert pages to PDF
    # --------------------------------------------------------

    pdf_io = io.BytesIO()

    pdf_io.name = (
        f"{title}_Exam_Booklet.pdf"
    )

    if pages:

        pages[0].save(
            pdf_io,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=300.0
        )

    pdf_io.seek(0)

    return pdf_io


# ============================================================
# BOT COMMAND MENU
# ============================================================

async def post_init(application):

    commands = [

        BotCommand(
            "start",
            "Start bot"
        ),

        BotCommand(
            "create",
            "Create quiz"
        ),

        BotCommand(
            "done",
            "Finish quiz creation"
        ),

        BotCommand(
            "cancel",
            "Cancel quiz creation"
        ),

        BotCommand(
            "myquizzes",
            "View quizzes"
        ),

        BotCommand(
            "play",
            "Play quiz"
        ),

        BotCommand(
            "pdf",
            "Download PDF"
        ),

        BotCommand(
            "backup",
            "Email backup"
        ),
    ]

    await application.bot.set_my_commands(
        commands
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    args = context.args

    # Deep link:
    # /start PLAY_GGNXXXXXX

    if (
        args
        and args[0].upper().startswith("PLAY_")
    ):

        quiz_id = (
            args[0][5:]
            .strip()
            .upper()
        )

        await prompt_quiz_settings(
            update.effective_chat.id,
            quiz_id,
            user.id,
            context
        )

        return

    await update.message.reply_text(

        f"🇮🇳 नमस्ते {user.first_name}!\n\n"

        "🎯 JB STUDY POINT Quiz Bot\n\n"

        "📝 नया टेस्ट: /create\n"
        "📚 टेस्ट सूची: /myquizzes\n"
        "▶️ टेस्ट खेलें: /play QUIZ_ID\n"
        "📄 PDF: /pdf QUIZ_ID\n"
        "📧 Backup: /backup QUIZ_ID\n"
        "🛑 Cancel: /cancel"
    )


# ============================================================
# /CREATE
# ============================================================

async def create_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ यह command केवल admin के लिए है।"
        )
        return

    # /create History Test
    if context.args:

        title = (
            " ".join(context.args)
            .strip()
        )

        if not title:
            await update.message.reply_text(
                "❌ Test title खाली है।"
            )
            return

        quiz_id = generate_quiz_id()

        creator_sessions[user_id] = {

            "title": title,

            "questions": [],

            "id": quiz_id,

            "step": "POLLS",

            "creator": DEFAULT_CREATOR,
        }

        await update.message.reply_text(

            f"✅ Test शुरू हो गया।\n\n"
            f"📝 Title: {title}\n"
            f"🆔 ID: {quiz_id}\n\n"
            "अब Telegram Quiz Polls forward करें।\n"
            "सभी questions के बाद /done भेजें।"
        )

        return

    # /create without title

    creator_sessions[user_id] = {

        "step": "TITLE"

    }

    await update.message.reply_text(
        "📝 कृपया Test का नाम भेजें:"
    )


# ============================================================
# TEXT HANDLER
# ============================================================

async def handle_text_messages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    session = creator_sessions.get(
        user_id
    )

    if not session:
        return

    if session.get("step") != "TITLE":
        return

    title = (
        update.message.text
        .strip()
    )

    if not title:

        await update.message.reply_text(
            "❌ Test title खाली नहीं हो सकता।"
        )

        return

    quiz_id = generate_quiz_id()

    creator_sessions[user_id] = {

        "title": title,

        "questions": [],

        "id": quiz_id,

        "step": "POLLS",

        "creator": DEFAULT_CREATOR,
    }

    await update.message.reply_text(

        f"✅ Test तैयार है।\n\n"
        f"📝 {title}\n"
        f"🆔 {quiz_id}\n\n"
        "अब Quiz Polls forward करें।\n"
        "समाप्त होने पर /done भेजें।"
    )


# ============================================================
# FORWARDED QUIZ POLL
# ============================================================

async def handle_incoming_poll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    session = creator_sessions.get(
        user_id
    )

    if not session:
        return

    if session.get("step") != "POLLS":
        return

    poll = update.message.poll

    if not poll:
        return

    # Only Quiz polls accepted

    if poll.type != "quiz":

        await update.message.reply_text(
            "❌ केवल Quiz Poll स्वीकार किया जाएगा।"
        )

        return

    # Correct option must exist

    if poll.correct_option_id is None:

        await update.message.reply_text(
            "❌ इस poll में correct answer नहीं मिला।"
        )

        return

    options = [
        option.text
        for option in poll.options
    ]

    if not 2 <= len(options) <= 10:

        await update.message.reply_text(
            "❌ Poll में 2 से 10 options होने चाहिए।"
        )

        return

    question = clean_question_text(
        poll.question
    )

    session["questions"].append(

        {
            "question": question,

            "options": options,

            "correct_id": int(
                poll.correct_option_id
            ),
        }
    )

    count = len(
        session["questions"]
    )

    await update.message.reply_text(

        f"✅ Question saved: {count}"
    )


# ============================================================
# /DONE
# ============================================================

async def done_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        return

    session = creator_sessions.get(
        user_id
    )

    if not session:

        await update.message.reply_text(
            "❌ कोई active quiz creation नहीं है।"
        )

        return

    if session.get("step") != "POLLS":

        await update.message.reply_text(
            "❌ Quiz creation अभी शुरू नहीं हुआ।"
        )

        return

    valid, error = validate_quiz(
        session
    )

    if not valid:

        await update.message.reply_text(
            f"❌ {error}"
        )

        return

    quiz_id = session["id"]

    all_quizzes = get_all_quizzes()

    all_quizzes[quiz_id] = session

    save_all_quizzes(
        all_quizzes
    )

    # Email backup in background

    threading.Thread(

        target=send_quiz_email_backup,

        args=(
            session["title"],
            quiz_id,
            session.copy()
        ),

        daemon=True

    ).start()

    del creator_sessions[user_id]

    keyboard = [

        [
            InlineKeyboardButton(
                "▶️ Start Quiz",
                callback_data=f"init_{quiz_id}"
            )
        ],

        [
            InlineKeyboardButton(
                "📄 Download PDF",
                callback_data=f"pdf_{quiz_id}"
            )
        ]

    ]

    await update.message.reply_text(

        "🎉 TEST SUCCESSFULLY CREATED!\n\n"

        f"📝 {session['title']}\n"
        f"🆔 {quiz_id}\n"
        f"❓ Questions: "
        f"{len(session['questions'])}\n\n"

        "अब आप Quiz Start कर सकते हैं।",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# /CANCEL
# ============================================================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if user_id in creator_sessions:

        del creator_sessions[user_id]

        await update.message.reply_text(
            "🛑 Quiz creation cancel कर दिया गया।"
        )

    else:

        await update.message.reply_text(
            "कोई active creation session नहीं है।"
        )


# ============================================================
# /MYQUIZZES
# ============================================================

async def my_quizzes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    quizzes = get_all_quizzes()

    if not quizzes:

        await update.message.reply_text(
            "📭 कोई quiz मौजूद नहीं है।"
        )

        return

    lines = [
        "📚 JB STUDY POINT QUIZZES\n"
    ]

    for quiz_id, quiz in quizzes.items():

        title = quiz.get(
            "title",
            "Untitled"
        )

        total = len(
            quiz.get(
                "questions",
                []
            )
        )

        lines.append(

            f"📝 {title}\n"
            f"🆔 {quiz_id}\n"
            f"❓ Questions: {total}\n"
            f"▶️ /play {quiz_id}\n"
            f"📄 /pdf {quiz_id}\n"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# QUIZ SETTINGS
# ============================================================

async def prompt_quiz_settings(
    chat_id,
    quiz_id,
    host_id,
    context
):

    all_quizzes = get_all_quizzes()

    quiz = all_quizzes.get(
        quiz_id
    )

    if not quiz:

        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Quiz नहीं मिला।"
        )

        return

    if chat_id in active_group_quizzes:

        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ इस chat में एक quiz पहले से चल रहा है।"
        )

        return

    pending_setups[chat_id] = {

        "quiz_id": quiz_id,

        "host_id": host_id,

        "timer": 20,

        "negative": 0.0,
    }

    keyboard = [

        [
            InlineKeyboardButton(
                "⏱ 15 सेकंड",
                callback_data=f"TIME:{chat_id}:15"
            ),

            InlineKeyboardButton(
                "⏱ 20 सेकंड",
                callback_data=f"TIME:{chat_id}:20"
            )
        ],

        [
            InlineKeyboardButton(
                "⏱ 25 सेकंड",
                callback_data=f"TIME:{chat_id}:25"
            ),

            InlineKeyboardButton(
                "⏱ 30 सेकंड",
                callback_data=f"TIME:{chat_id}:30"
            )
        ]

    ]

    await context.bot.send_message(

        chat_id=chat_id,

        text=(
            f"⚙️ Quiz Settings\n\n"
            f"📝 {quiz.get('title')}\n"
            f"❓ Questions: "
            f"{len(quiz.get('questions', []))}\n\n"
            "⏱ Question timer चुनें:"
        ),

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_click(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    # --------------------------------------------------------
    # INIT
    # --------------------------------------------------------

    if data.startswith("init_"):

        quiz_id = (
            data[5:]
            .strip()
            .upper()
        )

        await prompt_quiz_settings(

            query.message.chat_id,

            quiz_id,

            query.from_user.id,

            context
        )

        return

    # --------------------------------------------------------
    # TIMER
    # --------------------------------------------------------

    if data.startswith("TIME:"):

        try:

            _, chat_id_text, timer_text = (
                data.split(":")
            )

            chat_id = int(
                chat_id_text
            )

            timer_value = int(
                timer_text
            )

        except ValueError:

            return

        setup = pending_setups.get(
            chat_id
        )

        if not setup:
            return

        setup["timer"] = timer_value

        keyboard = [

            [
                InlineKeyboardButton(
                    "0.00 No Negative",
                    callback_data=f"NEG:{chat_id}:0"
                ),

                InlineKeyboardButton(
                    "-0.33",
                    callback_data=f"NEG:{chat_id}:33"
                )
            ],

            [
                InlineKeyboardButton(
                    "-0.50",
                    callback_data=f"NEG:{chat_id}:50"
                ),

                InlineKeyboardButton(
                    "-0.25",
                    callback_data=f"NEG:{chat_id}:25"
                )
            ]

        ]

        await query.edit_message_text(

            f"⏱ Timer: {timer_value} seconds\n\n"
            "⚠️ Negative Marking चुनें:",

            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # --------------------------------------------------------
    # NEGATIVE MARKING
    # --------------------------------------------------------

    if data.startswith("NEG:"):

        try:

            _, chat_id_text, negative_code = (
                data.split(":")
            )

            chat_id = int(
                chat_id_text
            )

        except ValueError:

            return

        setup = pending_setups.get(
            chat_id
        )

        if not setup:
            return

        negative_map = {

            "0": 0.0,

            "25": 0.25,

            "33": 0.33,

            "50": 0.50,
        }

        negative = negative_map.get(
            negative_code,
            0.0
        )

        setup["negative"] = negative

        quiz_id = setup["quiz_id"]

        timer = setup["timer"]

        host_id = setup["host_id"]

        del pending_setups[chat_id]

        await query.edit_message_text(
            "✅ Settings complete!\n"
            "🎯 Quiz शुरू हो रहा है..."
        )

        await start_group_quiz(

            chat_id,

            quiz_id,

            timer,

            negative,

            query.message.chat.type == "private",

            context
        )

        return

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if data.startswith("pdf_"):

        quiz_id = (
            data[4:]
            .strip()
            .upper()
        )

        await send_quiz_pdf(

            query.message.chat_id,

            quiz_id,

            context
        )


# ============================================================
# /PLAY
# ============================================================

async def play_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "उदाहरण:\n"
            "/play GGNABC123"
        )

        return

    quiz_id = (
        context.args[0]
        .strip()
        .upper()
    )

    await prompt_quiz_settings(

        update.effective_chat.id,

        quiz_id,

        update.effective_user.id,

        context
    )


# ============================================================
# PDF COMMAND
# ============================================================

async def send_quiz_pdf(
    chat_id,
    quiz_id,
    context
):

    quizzes = get_all_quizzes()

    quiz = quizzes.get(
        quiz_id
    )

    if not quiz:

        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Quiz नहीं मिला।"
        )

        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ Exam PDF तैयार हो रही है..."
    )

    try:

        pdf = generate_pdf_bytes(
            quiz
        )

        await context.bot.send_document(

            chat_id=chat_id,

            document=pdf,

            filename=(
                f"{quiz_id}_Exam_Booklet.pdf"
            )
        )

    except Exception as e:

        await context.bot.send_message(

            chat_id=chat_id,

            text=f"❌ PDF Error:\n{e}"
        )


async def pdf_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "उदाहरण:\n"
            "/pdf GGNABC123"
        )

        return

    quiz_id = (
        context.args[0]
        .strip()
        .upper()
    )

    await send_quiz_pdf(

        update.effective_chat.id,

        quiz_id,

        context
    )


# ============================================================
# BACKUP COMMAND
# ============================================================

async def backup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    if not GMAIL_USER or not GMAIL_PASS:

        await update.message.reply_text(

            "❌ Gmail backup configured नहीं है।\n\n"

            "GMAIL_USER और "
            "GMAIL_APP_PASSWORD "
            "environment variables सेट करें।"
        )

        return

    quizzes = get_all_quizzes()

    if not quizzes:

        await update.message.reply_text(
            "❌ कोई quiz नहीं है।"
        )

        return

    # Specific quiz backup

    if context.args:

        quiz_id = (
            context.args[0]
            .strip()
            .upper()
        )

        quiz = quizzes.get(
            quiz_id
        )

        if not quiz:

            await update.message.reply_text(
                "❌ Quiz नहीं मिला।"
            )

            return

        threading.Thread(

            target=send_quiz_email_backup,

            args=(
                quiz.get(
                    "title",
                    "Quiz"
                ),

                quiz_id,

                quiz
            ),

            daemon=True

        ).start()

        await update.message.reply_text(
            "📧 Quiz backup भेजा जा रहा है।"
        )

        return

    # Full backup

    threading.Thread(

        target=send_quiz_email_backup,

        args=(
            "ALL QUIZZES",
            "ALL_QUIZZES",
            quizzes
        ),

        daemon=True

    ).start()

    await update.message.reply_text(
        "📧 सभी quizzes का backup भेजा जा रहा है।"
    )


# ============================================================
# START QUIZ
# ============================================================

async def start_group_quiz(
    chat_id,
    quiz_id,
    timer_sec,
    negative_value,
    is_private,
    context
):

    if chat_id in active_group_quizzes:

        await context.bot.send_message(

            chat_id=chat_id,

            text=(
                "⚠️ इस chat में "
                "पहले से quiz चल रहा है।"
            )
        )

        return

    quizzes = get_all_quizzes()

    quiz = quizzes.get(
        quiz_id
    )

    if not quiz:

        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Quiz नहीं मिला।"
        )

        return

    total_questions = len(
        quiz.get(
            "questions",
            []
        )
    )

    active_group_quizzes[chat_id] = {

        "quiz_id": quiz_id,

        "index": 0,

        "timer": int(
            timer_sec
        ),

        "negative": float(
            negative_value
        ),

        "is_private": is_private,

        "users": {},

        "current_msg_id": None,

        "current_poll_id": None,

        "current_answers": {},

        "total_q": total_questions,

        "timer_task": None,

        "advancing": False,
    }

    await context.bot.send_message(

        chat_id=chat_id,

        text=(

            "🎯 TEST START\n\n"

            f"📝 {quiz.get('title')}\n"

            f"❓ Questions: {total_questions}\n"

            f"⏱ {timer_sec} seconds/question\n"

            f"❌ Negative: -{negative_value}"
        )
    )

    await asyncio.sleep(1)

    await send_next_question(
        chat_id,
        context
    )


# ============================================================
# TIMER
# ============================================================

async def auto_timer_countdown(
    chat_id,
    message_id,
    duration,
    context
):

    try:

        await asyncio.sleep(
            duration
        )

        session = active_group_quizzes.get(
            chat_id
        )

        if not session:
            return

        if (
            session.get(
                "current_msg_id"
            )
            == message_id
        ):

            await close_current_question(
                chat_id,
                context
            )

    except asyncio.CancelledError:

        pass


# ============================================================
# CLOSE CURRENT QUESTION
# ============================================================

async def close_current_question(
    chat_id,
    context
):

    session = active_group_quizzes.get(
        chat_id
    )

    if not session:
        return

    # Prevent double execution

    if session.get("advancing"):
        return

    session["advancing"] = True

    message_id = session.get(
        "current_msg_id"
    )

    if message_id:

        try:

            await context.bot.stop_poll(

                chat_id=chat_id,

                message_id=message_id
            )

        except Exception:
            pass

    current_task = (
        asyncio.current_task()
    )

    timer_task = session.get(
        "timer_task"
    )

    if (
        timer_task
        and timer_task != current_task
        and not timer_task.done()
    ):

        timer_task.cancel()

    await asyncio.sleep(
        0.2
    )

    session = active_group_quizzes.get(
        chat_id
    )

    if not session:
        return

    session["advancing"] = False

    await send_next_question(
        chat_id,
        context
    )


# ============================================================
# SEND NEXT QUESTION
# ============================================================

async def send_next_question(
    chat_id,
    context
):

    session = active_group_quizzes.get(
        chat_id
    )

    if not session:
        return

    quizzes = get_all_quizzes()

    quiz = quizzes.get(
        session["quiz_id"]
    )

    if not quiz:

        del active_group_quizzes[
            chat_id
        ]

        return

    question_index = session[
        "index"
    ]

    questions = quiz.get(
        "questions",
        []
    )

    # Quiz finished

    if question_index >= len(
        questions
    ):

        await finish_quiz_and_show_ranks(
            chat_id,
            context
        )

        return

    question = questions[
        question_index
    ]

    session["index"] += 1

    session["current_answers"] = {}

    question_text = clean_question_text(
        question.get(
            "question",
            ""
        )
    )

    header = (

        f"[{question_index + 1}"
        f"/{len(questions)}] "

        f"⏱ {session['timer']}s | "

        f"{question_text}"
    )

    poll_message = await context.bot.send_poll(

        chat_id=chat_id,

        question=header[:300],

        options=question[
            "options"
        ],

        type="quiz",

        correct_option_id=int(
            question[
                "correct_id"
            ]
        ),

        is_anonymous=False,

        open_period=int(
            session["timer"]
        )
    )

    session["current_msg_id"] = (
        poll_message.message_id
    )

    session["current_poll_id"] = (
        poll_message.poll.id
    )

    # Store poll metadata separately

    context.bot_data.setdefault(
        "quiz_polls",
        {}
    )

    context.bot_data[
        "quiz_polls"
    ][poll_message.poll.id] = {

        "chat_id": chat_id,

        "correct_id": int(
            question[
                "correct_id"
            ]
        ),

        "question_index":
            question_index,
    }

    session["timer_task"] = (
        asyncio.create_task(
            auto_timer_countdown(
                chat_id,
                poll_message.message_id,
                session["timer"],
                context
            )
        )
    )


# ============================================================
# POLL ANSWER HANDLER
# ============================================================

async def handle_poll_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    poll_answer = update.poll_answer

    poll_id = poll_answer.poll_id

    poll_database = context.bot_data.get(
        "quiz_polls",
        {}
    )

    poll_info = poll_database.get(
        poll_id
    )

    if not poll_info:
        return

    chat_id = poll_info[
        "chat_id"
    ]

    session = active_group_quizzes.get(
        chat_id
    )

    if not session:
        return

    # Ignore answers after current question

    if (
        session.get(
            "current_poll_id"
        )
        != poll_id
    ):

        return

    user = poll_answer.user

    user_id = user.id

    name = (
        user.first_name
        or "Participant"
    )

    # --------------------------------------------------------
    # Create participant
    # --------------------------------------------------------

    if user_id not in session[
        "users"
    ]:

        session["users"][user_id] = {

            "name": name,

            "correct": 0,

            "wrong": 0,

            "skipped": 0,

            "score": 0.0,
        }

    participant = session[
        "users"
    ][user_id]

    # --------------------------------------------------------
    # Reverse previous answer
    # --------------------------------------------------------

    previous = session[
        "current_answers"
    ].get(user_id)

    if previous:

        if previous.get(
            "correct"
        ):

            participant[
                "correct"
            ] -= 1

            participant[
                "score"
            ] -= 1.0

        elif previous.get(
            "wrong"
        ):

            participant[
                "wrong"
            ] -= 1

            participant[
                "score"
            ] += session[
                "negative"
            ]

    # --------------------------------------------------------
    # No answer
    # --------------------------------------------------------

    if not poll_answer.option_ids:

        session[
            "current_answers"
        ][user_id] = {

            "correct": False,

            "wrong": False,

            "option": None,
        }

        return

    selected_option = (
        poll_answer.option_ids[0]
    )

    correct_option = poll_info[
        "correct_id"
    ]

    # --------------------------------------------------------
    # Correct
    # --------------------------------------------------------

    if selected_option == correct_option:

        participant[
            "correct"
        ] += 1

        participant[
            "score"
        ] += 1.0

        session[
            "current_answers"
        ][user_id] = {

            "correct": True,

            "wrong": False,

            "option":
                selected_option,
        }

    # --------------------------------------------------------
    # Wrong
    # --------------------------------------------------------

    else:

        participant[
            "wrong"
        ] += 1

        participant[
            "score"
        ] -= session[
            "negative"
        ]

        session[
            "current_answers"
        ][user_id] = {

            "correct": False,

            "wrong": True,

            "option":
                selected_option,
        }


# ============================================================
# FINAL RESULT
# ============================================================

async def finish_quiz_and_show_ranks(
    chat_id,
    context
):

    session = active_group_quizzes.pop(
        chat_id,
        None
    )

    if not session:
        return

    timer_task = session.get(
        "timer_task"
    )

    if (
        timer_task
        and not timer_task.done()
    ):

        timer_task.cancel()

    quizzes = get_all_quizzes()

    quiz = quizzes.get(
        session["quiz_id"]
    )

    if not quiz:
        return

    participants = session[
        "users"
    ]

    if not participants:

        await context.bot.send_message(

            chat_id=chat_id,

            text=(
                "🏁 TEST FINISHED\n\n"
                "किसी participant ने answer नहीं किया।"
            )
        )

        return

    sorted_users = sorted(

        participants.items(),

        key=lambda item: (

            -item[1]["score"],

            -item[1]["correct"],

            item[1]["wrong"]
        )
    )

    lines = []

    for rank, (
        user_id,
        participant
    ) in enumerate(
        sorted_users,
        1
    ):

        score = round(
            participant["score"],
            2
        )

        lines.append(

            f"{rank}. "
            f"{participant['name']} — "
            f"{score}/{session['total_q']} "
            f"| ✅ {participant['correct']} "
            f"| ❌ {participant['wrong']}"
        )

    result_text = (

        "🏁 FINAL RESULT\n\n"

        f"📝 {quiz.get('title')}\n"

        f"❓ Questions: "
        f"{session['total_q']}\n"

        f"⏱ Timer: "
        f"{session['timer']}s\n"

        f"❌ Negative: "
        f"-{session['negative']}\n\n"

        "🏆 LEADERBOARD\n\n"

        + "\n".join(lines)
    )

    # Telegram message limit

    if len(result_text) <= 4096:

        await context.bot.send_message(

            chat_id=chat_id,

            text=result_text
        )

    else:

        # Split leaderboard

        await context.bot.send_message(

            chat_id=chat_id,

            text=(
                "🏁 FINAL RESULT\n\n"
                f"📝 {quiz.get('title')}\n"
                f"❓ Questions: "
                f"{session['total_q']}"
            )
        )

        chunk = ""

        for line in lines:

            if len(
                chunk + "\n" + line
            ) > 3900:

                await context.bot.send_message(

                    chat_id=chat_id,

                    text=chunk
                )

                chunk = line

            else:

                chunk += (
                    "\n" + line
                )

        if chunk:

            await context.bot.send_message(

                chat_id=chat_id,

                text=chunk
            )


# ============================================================
# WEB DASHBOARD
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>

<html lang="hi">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>JB STUDY POINT</title>

<style>

body{
    font-family:Arial,sans-serif;
    background:#f0f2f5;
    padding:30px;
}

.box{
    max-width:700px;
    margin:auto;
    background:white;
    padding:30px;
    border-radius:15px;
    box-shadow:0 4px 15px rgba(0,0,0,.12);
}

h1{
    color:#8B0000;
}

.status{
    padding:15px;
    background:#e8f5e9;
    border-radius:10px;
}

</style>

</head>

<body>

<div class="box">

<h1>JB STUDY POINT</h1>

<div class="status">

<h3>✅ Quiz Bot Server Running</h3>

<p>Telegram Quiz Engine: Active</p>

<p>PDF Generator: Active</p>

<p>Negative Marking: Active</p>

<p>Gmail Backup: Configurable</p>

</div>

</div>

</body>

</html>
"""


class QuizCreatorServer(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            HTML_TEMPLATE.encode(
                "utf-8"
            )
        )

    def log_message(
        self,
        format,
        *args
    ):

        return


def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            "8080"
        )
    )

    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        QuizCreatorServer
    )

    print(
        f"Web server running on port {port}"
    )

    server.serve_forever()


# ============================================================
# MAIN
# ============================================================

def main():

    # Web server

    threading.Thread(

        target=run_web_server,

        daemon=True

    ).start()

    # Telegram application

    application = (

        ApplicationBuilder()

        .token(TOKEN)

        .post_init(post_init)

        .build()
    )

    # --------------------------------------------------------
    # Commands
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "create",
            create_command
        )
    )

    application.add_handler(
        CommandHandler(
            "done",
            done_command
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
        )
    )

    application.add_handler(
        CommandHandler(
            "play",
            play_command
        )
    )

    application.add_handler(
        CommandHandler(
            "myquizzes",
            my_quizzes
        )
    )

    application.add_handler(
        CommandHandler(
            "pdf",
            pdf_command
        )
    )

    application.add_handler(
        CommandHandler(
            "backup",
            backup_command
        )
    )

    # --------------------------------------------------------
    # Poll handler
    # --------------------------------------------------------

    application.add_handler(

        MessageHandler(
            filters.POLL,
            handle_incoming_poll
        )
    )

    # --------------------------------------------------------
    # Text handler
    # --------------------------------------------------------

    application.add_handler(

        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text_messages
        )
    )

    # --------------------------------------------------------
    # Buttons
    # --------------------------------------------------------

    application.add_handler(

        CallbackQueryHandler(
            button_click
        )
    )

    # --------------------------------------------------------
    # Poll answers
    # --------------------------------------------------------

    application.add_handler(

        PollAnswerHandler(
            handle_poll_answer
        )
    )

    print(
        "===================================="
    )

    print(
        "JB STUDY POINT QUIZ BOT STARTED"
    )

    print(
        "===================================="
    )

    application.run_polling()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
