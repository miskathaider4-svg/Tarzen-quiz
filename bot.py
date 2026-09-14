import json
import logging
from google import genai
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- API KEYS ---
TELEGRAM_TOKEN = "8706836737:AAG2NjJA2g7tYUr37u--QKTsqN_-Y80Lk1E"
GEMINI_API_KEY = "AQ.Ab8RN6IRsvyNA7cpoEzeVkhaZ_yhGHN9rNicxXmC2wDeCStF_w"

# Initialize Gemini Client using the official google-genai SDK
client = genai.Client(api_key=GEMINI_API_KEY)

# Store user session data
user_sessions = {}


# --- AI QUESTION GENERATOR ---
def generate_quiz_via_sdk(subject: str, topic: str, difficulty: str, lang: str, count: int) -> list:
    lang_name = "Bengali (বাংলা)" if lang == "bn" else "English"
    
    prompt = f"""
    Generate {count} multiple-choice questions for WBBSE Class 10 Madhyamik level.
    Subject: {subject}
    Topic: {topic}
    Difficulty: {difficulty}
    Language: {lang_name}
    
    Strictly follow standard WBBSE curriculum alignment.
    Respond STRICTLY with valid JSON. Do not write markdown blocks or setup text.
    Format JSON structure:
    [
      {{
        "question": "Question text here",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "answer_index": 0
      }}
    ]
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini generation error: {e}")
        return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📚 Bengali Medium (বাংলা মাধ্যম)", callback_data="lang_bn")],
        [InlineKeyboardButton("📚 English Medium", callback_data="lang_en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to WBBSE Madhyamik Quiz Bot! 🎓\nSelect your preferred medium:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("lang_"):
        lang = data.split("_")[1]
        user_sessions[user_id] = {"lang": lang}
        
        keyboard = [
            [InlineKeyboardButton("Math (অঙ্ক)", callback_data="subj_Math"), InlineKeyboardButton("Physical Science (ভৌত বিজ্ঞান)", callback_data="subj_PhysicalScience")],
            [InlineKeyboardButton("Life Science (জীবন বিজ্ঞান)", callback_data="subj_LifeScience"), InlineKeyboardButton("History (ইতিহাস)", callback_data="subj_History")],
            [InlineKeyboardButton("Geography (ভূগোল)", callback_data="subj_Geography")]
        ]
        await query.edit_message_text("Choose a subject:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("subj_"):
        subject = data.split("_")[1]
        if user_id in user_sessions:
            user_sessions[user_id]["subject"] = subject
            
        keyboard = [
            [InlineKeyboardButton("Easy", callback_data="diff_Easy")],
            [InlineKeyboardButton("Medium", callback_data="diff_Medium")],
            [InlineKeyboardButton("Hard", callback_data="diff_Hard")]
        ]
        await query.edit_message_text("Choose difficulty level:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("diff_"):
        difficulty = data.split("_")[1]
        session = user_sessions.get(user_id, {"lang": "en", "subject": "Math"})
        session["difficulty"] = difficulty
        
        await query.edit_message_text("🤖 Generating your custom WBBSE quiz questions using Gemini...")
        
        questions = generate_quiz_via_sdk(
            subject=session["subject"],
            topic="General Chapter",
            difficulty=difficulty,
            lang=session["lang"],
            count=3
        )
        
        if not questions:
            await query.edit_message_text("Failed to generate quiz due to an API error. Please try again later.")
            return
            
        session["questions"] = questions
        session["current_q"] = 0
        session["score"] = 0
        
        # Send the first question
        await send_question(query.message.chat_id, context, user_id)

    elif data.startswith("ans_"):
        selected_idx = int(data.split("_")[1])
        session = user_sessions.get(user_id)
        
        if not session or "questions" not in session:
            await query.edit_message_text("Session expired. Please type /start to begin again.")
            return
            
        current_q = session["current_q"]
        q_data = session["questions"][current_q]
        correct_idx = q_data["answer_index"]
        
        if selected_idx == correct_idx:
            session["score"] += 1
            feedback = "✅ Correct!"
        else:
            correct_opt = q_data["options"][correct_idx]
            feedback = f"❌ Wrong! The correct answer was: {correct_opt}"
            
        # Update current message to show feedback and remove buttons
        await query.edit_message_text(f"{query.message.text}\n\n{feedback}")
        
        # Move to next question
        session["current_q"] += 1
        await send_question(query.message.chat_id, context, user_id)


async def send_question(chat_id, context, user_id):
    session = user_sessions.get(user_id)
    if not session or session["current_q"] >= len(session["questions"]):
        score = session.get('score', 0)
        total = len(session.get('questions', []))
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Quiz finished! 🎉 Your score: {score}/{total}"
        )
        return
        
    q_data = session["questions"][session["current_q"]]
    keyboard = []
    for idx, opt in enumerate(q_data["options"]):
        keyboard.append([InlineKeyboardButton(opt, callback_data=f"ans_{idx}")])
        
    q_num = session["current_q"] + 1
    text = f"**Question {q_num}:**\n{q_data['question']}"
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def main():
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.run_polling()


if __name__ == "__main__":
    main()
    
