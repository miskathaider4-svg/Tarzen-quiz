import asyncio
import json
import logging
from google import genai
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PollAnswerHandler,
    filters,
)

# Logging Setup
logging.basicConfig(level=logging.INFO)

# --- CONFIGURATION ---
BOT_TOKEN = "8706836737:AAGZKFU9s6ueCaCVl-ryY-bApLq_hHT0ryg"
GEMINI_API_KEY = "AIzaSyBcIM4PNx1KX5-EN2rcf8jnMZ57lYuJMlU"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

active_sessions = {}
quiz_setup_data = {}
poll_to_chat_map = {}

# --- SDK QUESTION GENERATOR ---
def fetch_questions_via_sdk(subject: str, topic: str, difficulty: str, lang: str, count: int) -> list:
    lang_instruction = "Bengali (বাংলা)" if lang == "bn" else "English"
    
    prompt = f"""
    Generate exactly {count} multiple-choice questions for WBBSE Class 10 Madhyamik level.
    Subject: {subject}
    Topic/Chapter: {topic}
    Difficulty Level: {difficulty}
    Language: {lang_instruction}

    Ensure exact standard WBBSE curriculum alignment.
    You MUST respond STRICTLY with valid JSON. Do not write markdown blocks or setup text.
    Use this exact JSON structure:
    [
      {{
        "question": "Question text here",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "correct_option_index": 0
      }}
    ]
    """

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )
    
    return json.loads(response.text)

# --- SIMPLIFIED SETUP FLOW ---
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    quiz_setup_data[user_id] = {"step": "waiting_subject"}
    
    await update.message.reply_text(
        "✨ **WBBSE LIGHTNING QUIZ BOT** ✨\n\n"
        "**Step 1:** Type the name of the **Subject** (e.g., *Physical Science, Life Science, History, Geography, Mathematics, বাংলা ব্যাকরণ*):",
        parse_mode="Markdown"
    )

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in quiz_setup_data:
        return

    state = quiz_setup_data[user_id].get("step")

    if state == "waiting_subject":
        quiz_setup_data[user_id]["subject"] = text
        quiz_setup_data[user_id]["step"] = "waiting_topic"
        await update.message.reply_text(
            f"Subject: **{text}**\n\n**Step 2:** Type the **Topic / Chapter Name** you want to test:",
            parse_mode="Markdown"
        )

    elif state == "waiting_topic":
        quiz_setup_data[user_id]["topic"] = text
        quiz_setup_data[user_id]["step"] = "waiting_diff"

        keyboard = [
            [
                InlineKeyboardButton("Easy 😄", callback_data="diff_easy"),
                InlineKeyboardButton("Moderate ⚖️", callback_data="diff_moderate"),
                InlineKeyboardButton("Extreme 🔥", callback_data="diff_extreme")
            ]
        ]
        await update.message.reply_text(
            f"Topic: **{text}**\n\n**Step 3:** Select Difficulty Level:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    user_id = query.from_user.id
    data = query.data
    chat_id = query.message.chat_id

    if user_id not in quiz_setup_data:
        return

    if data.startswith("diff_"):
        diff = data.split("_")[1]
        quiz_setup_data[user_id]["diff"] = diff

        keyboard = [
            [
                InlineKeyboardButton("Bengali (বাংলা) 🇧🇩", callback_data="lang_bn"),
                InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")
            ]
        ]
        await query.edit_message_text(
            f"Difficulty: **{diff.capitalize()}**\n\n**Step 4:** Select Question Language:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("lang_"):
        lang = data.split("_")[1]
        quiz_setup_data[user_id]["lang"] = lang

        keyboard = [
            [
                InlineKeyboardButton("10 Qs", callback_data="cnt_10"),
                InlineKeyboardButton("20 Qs", callback_data="cnt_20")
            ],
            [
                InlineKeyboardButton("30 Qs", callback_data="cnt_30"),
                InlineKeyboardButton("50 Qs", callback_data="cnt_50")
            ]
        ]
        await query.edit_message_text(
            f"Language: **{'Bengali' if lang=='bn' else 'English'}**\n\n**Step 5:** How many questions do you want?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("cnt_"):
        cnt = int(data.split("_")[1])
        quiz_setup_data[user_id]["count"] = cnt

        keyboard = [
            [
                InlineKeyboardButton("Yes ⏱️ (Lock Poll)", callback_data="timer_yes"),
                InlineKeyboardButton("No ♾️ (No Timer Lock)", callback_data="timer_no")
            ]
        ]
        await query.edit_message_text(
            f"Count: **{cnt} Questions**\n\n**Step 6:** Enable strict timer lock per question?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("timer_"):
        choice = data.split("_")[1]
        if choice == "no":
            quiz_setup_data[user_id]["open_period"] = None
            asyncio.create_task(build_and_launch(query, context, user_id, chat_id))
        else:
            keyboard = [
                [
                    InlineKeyboardButton("10 Seconds", callback_data="limit_10"),
                    InlineKeyboardButton("15 Seconds", callback_data="limit_15"),
                    InlineKeyboardButton("30 Seconds", callback_data="limit_30")
                ]
            ]
            await query.edit_message_text(
                "⏳ **Select Timer Duration Per Question:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

    elif data.startswith("limit_"):
        seconds = int(data.split("_")[1])
        quiz_setup_data[user_id]["open_period"] = seconds
        asyncio.create_task(build_and_launch(query, context, user_id, chat_id))

async def build_and_launch(query, context, user_id, chat_id):
    config = quiz_setup_data.get(user_id)
    if not config:
        return

    try:
        await query.edit_message_text("⚡ **Generating Questions via Gemini AI... Please wait.**", parse_mode="Markdown")
    except Exception:
        pass

    try:
        questions = await asyncio.to_thread(
            fetch_questions_via_sdk,
            config["subject"],
            config["topic"],
            config["diff"],
            config["lang"],
            config["count"]
        )
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            error_message = (
                "❌ **Failed to fetch questions: 429 RESOURCE_EXHAUSTED.**\n\n"
                "You exceeded your current free tier quota limit. Please wait about 60 seconds "
                "for your quota window to reset before trying again."
            )
        else:
            error_message = f"❌ **An unexpected error occurred:** {err_str}\n\nPlease try again in a moment."
            
        await context.bot.send_message(chat_id, error_message, parse_mode="Markdown")
        return

    active_sessions[chat_id] = {
        "current_index": 0,
        "total_q": len(questions),
        "open_period": config.get("open_period"),
        "questions": questions,
        "scores": {}
    }

    await context.bot.send_message(chat_id, "🔥 **QUIZ LOADED SUCCESSFULLY! LET'S GO!** 🔥", parse_mode="Markdown")
    await asyncio.sleep(1)
    await send_next_poll(context, chat_id)

# --- QUIZ EXECUTION ---
async def send_next_poll(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    session = active_sessions.get(chat_id)
    if not session:
        return

    idx = session["current_index"]
    questions = session["questions"]

    if idx >= session["total_q"]:
        await context.bot.send_message(
            chat_id,
            "🎉 **QUIZ COMPLETED!** 🎉\nSend `/leaderboard` to check the final score standing!",
            parse_mode="Markdown"
        )
        return

    q_item = questions[idx]

    try:
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"[{idx + 1}/{session['total_q']}] {q_item['question']}",
            options=q_item["options"],
            type="quiz",
            correct_option_id=q_item["correct_option_index"],
            is_anonymous=False,
            open_period=session["open_period"]
        )
        poll_to_chat_map[poll_message.poll.id] = (chat_id, idx)
    except Exception as e:
        logging.error(f"Poll error: {e}")

    wait_time = session["open_period"] if session["open_period"] else 12
    await asyncio.sleep(wait_time + 2)
    session["current_index"] += 1
    await send_next_poll(context, chat_id)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    selected_options = answer.option_ids

    if poll_id not in poll_to_chat_map or not selected_options:
        return

    chat_id, q_idx = poll_to_chat_map[poll_id]
    session = active_sessions.get(chat_id)
    if not session:
        return

    q_data = session["questions"][q_idx]

    if user.id not in session["scores"]:
        session["scores"][user.id] = {"name": user.first_name, "score": 0}

    if selected_options[0] == q_data["correct_option_index"]:
        session["scores"][user.id]["score"] += 1

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = active_sessions.get(chat_id)

    if not session or not session["scores"]:
        await update.message.reply_text("⚠️ No active score records found.")
        return

    sorted_scores = sorted(session["scores"].values(), key=lambda x: x["score"], reverse=True)

    board_msg = "🥳 ✨ 🎆 **VICTORY LEADERBOARD** 🎆 ✨ 🥳\n"
    board_msg += "```\n"
    board_msg += "Rank | Participant      | Score\n"
    board_msg += "-----+------------------+-------\n"

    for i, player in enumerate(sorted_scores):
        rank = f"{i+1}"
        name = player["name"][:16].ljust(16)
        score = str(player["score"]).rjust(5)
        board_msg += f" {rank:<3} | {name} | {score}\n"
    board_msg += "```\n\n"

    board_msg += "🏆 🎉 **CONGRATULATIONS TO OUR CHAMPIONS!** 🎉 🏆\n"
    medals = ["🥇", "🥈", "🥉"]
    for i in range(min(3, len(sorted_scores))):
        board_msg += f"{medals[i]} **{sorted_scores[i]['name']}** — {sorted_scores[i]['score']} Point(s)!\n"

    await update.message.reply_text(board_msg, parse_mode="Markdown")

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )
    
    app.add_handler(CommandHandler("start", start_quiz))
    app.add_handler(CommandHandler("quiz", start_quiz))
    app.add_handler(CommandHandler("leaderboard", show_leaderboard))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    print("Lightweight text-input Quiz Bot running successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
