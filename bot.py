import os
import logging
from telegram import Update, Poll
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
)
from google import genai
from google.genai import types

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Gemini 3.6 Flash client with your API key
client = genai.Client(api_key="AQ.Ab8RN6JmsmTgJQ9J06eMCLo6-dOSFwUyZK4S6lwVMIy8_dW1rg")

# In-memory database mock for storing scores & active polls
# Structure: { user_id: {"name": str, "score": int} }
LEADERBOARD = {}

# Structure: { poll_id: {"correct_option": int, "subject": str, "explanation": str} }
ACTIVE_POLLS = {}

# WBBSE Madhyamik Subjects List
SUBJECTS = [
    "English", 
    "Bengali", 
    "Mathematics", 
    "History", 
    "Geography", 
    "Physical Science", 
    "Life Science"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the bot with a simple welcome message and subject selector."""
    welcome_text = (
        "📚 **Welcome to the WBBSE Madhyamik Quiz Bot!**\n\n"
        "Powered by **Gemini 3.6 Flash**, this bot tests your preparation across all 7 Madhyamik subjects:\n"
        "• English | Bengali | Mathematics | History | Geography | Physical Science | Life Science\n\n"
        "**Commands:**\n"
        "• `/quiz <subject>` - Start a native poll question (e.g., `/quiz History`)\n"
        "• `/leaderboard` - Check the engaging competitive leaderboard\n"
        "• `/subjects` - View available subjects"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def subjects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all available WBBSE subjects."""
    sub_list = "\n".join([f"📌 {sub}" for sub in SUBJECTS])
    await update.message.reply_text(
        f"**Available WBBSE Madhyamik Subjects:**\n\n{sub_list}\n\nUse `/quiz [subject]` to begin!",
        parse_mode="Markdown"
    )

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates a structured multiple-choice question using Gemini 3.6 Flash and sends a native Telegram poll."""
    query_args = context.args
    if not query_args:
        await update.message.reply_text(
            "⚠️ Please specify a subject! Example: `/quiz Mathematics` or `/quiz History`",
            parse_mode="Markdown"
        )
        return

    subject = " ".join(query_args).title()
    if subject not in SUBJECTS:
        await update.message.reply_text(
            f"❌ Invalid subject. Choose from: {', '.join(SUBJECTS)}"
        )
        return

    await update.message.reply_text(f"⏳ Generating a high-yield WBBSE standard question for **{subject}**...")

    # Crafting structured prompt for Gemini 3.6 Flash
    prompt = f"""
    You are an expert curriculum creator and examiner for the West Bengal Board of Secondary Education (WBBSE) Madhyamik examination.
    Generate a single, high-quality Multiple Choice Question (MCQ) for the subject: {subject}.
    The question must strictly mirror the standard, difficulty, and curriculum style of WBBSE Madhyamik Board exams.
    
    You MUST provide your output in the following format:
    QUESTION: [Insert clear question text here]
    OPTION_A: [First option]
    OPTION_B: [Second option]
    OPTION_C: [Third option]
    OPTION_D: [Fourth option]
    CORRECT: [A, B, C, or D]
    EXPLANATION: [Brief educational explanation of why the answer is correct according to WBBSE guidelines]
    """

    try:
        # Calling Gemini 3.6 Flash with Structured Output expectations
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        text_output = response.text

        # Basic text parser to extract fields
        lines = text_output.strip().split("\n")
        q_data = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                q_data[key.strip()] = val.strip()

        question_text = q_data.get("QUESTION", "What is the correct concept?")
        options = [
            q_data.get("OPTION_A", "Option A"),
            q_data.get("OPTION_B", "Option B"),
            q_data.get("OPTION_C", "Option C"),
            q_data.get("OPTION_D", "Option D"),
        ]
        
        correct_letter = q_data.get("CORRECT", "A").upper()
        mapping = {"A": 0, "B": 1, "C": 2, "D": 3}
        correct_index = mapping.get(correct_letter, 0)
        
        explanation = q_data.get("EXPLANATION", "Correct based on WBBSE curriculum syllabus.")

        # Send Telegram Native Poll
        message = await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=f"[{subject}] {question_text}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_index,
            is_anonymous=False,
            explanation=explanation
        )

        # Save poll data globally to track responses
        payload = message.poll
        ACTIVE_POLLS[payload.id] = {
            "correct_option": correct_index,
            "subject": subject,
            "explanation": explanation
        }

    except Exception as e:
        logger.error(f"Error generating quiz: {e}")
        await update.message.reply_text("⚠️ Sorry, could not generate the quiz right now. Try again later!")

async def receive_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tracks user answers via Telegram poll answers and awards points."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    user_id = user.id
    username = user.first_name or "Student"

    if poll_id in ACTIVE_POLLS:
        poll_info = ACTIVE_POLLS[poll_id]
        correct_option = poll_info["correct_option"]
        user_selection = answer.option_ids[0]

        # Initialize user in global leaderboard tracking if not present
        if user_id not in LEADERBOARD:
            LEADERBOARD[user_id] = {"name": username, "score": 0}

        # Award +5 points for correct answers
        if user_selection == correct_option:
            LEADERBOARD[user_id]["score"] += 5
            logger.info(f"User {username} answered correctly (+5 pts). Total: {LEADERBOARD[user_id]['score']}")

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays an engaging leaderboard ONLY when explicitly called via /leaderboard."""
    if not LEADERBOARD:
        await update.message.reply_text(
            "🏆 **Madhyamik Leaderboard Arena**\n\n"
            "The leaderboard is currently empty! Be the first to play by typing `/quiz [subject]` and scoring points.",
            parse_mode="Markdown"
        )
        return

    # Sort users based on score descending
    sorted_users = sorted(LEADERBOARD.values(), key=lambda x: x["score"], reverse=True)

    leaderboard_msg = "🏆 **WBBSE Madhyamik Battle Royale Leaderboard** 🏆\n"
    leaderboard_msg += "--------------------------------------------------\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for idx, user_data in enumerate(sorted_users[:10]): # Top 10 users
        rank_icon = medals[idx] if idx < 3 else f"#{idx + 1}"
        leaderboard_msg += f"{rank_icon} **{user_data['name']}** — 🎯 `{user_data['score']} pts`\n"

    leaderboard_msg += "\n--------------------------------------------------\n"
    leaderboard_msg += "💡 *Keep participating using `/quiz` to climb up the ranks!*"

    await update.message.reply_text(leaderboard_msg, parse_mode="Markdown")

def main():
    """Run the bot."""
    # Your hardcoded Telegram Bot Token
    TOKEN = "8706836737:AAGZKFU9s6ueCaCVl-ryY-bApLq_hHT0ryg"
    
    application = ApplicationBuilder().token(TOKEN).build()

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subjects", subjects_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    
    # Native poll answer tracker
    application.add_handler(PollAnswerHandler(receive_poll_answer))

    print("🤖 WBBSE Madhyamik Quiz Bot powered by Gemini 3.6 Flash is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
          
