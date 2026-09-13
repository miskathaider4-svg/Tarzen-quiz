import os
import logging
import asyncio
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    PollAnswerHandler,
)
from google import genai

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Gemini 3.6 Flash client
client = genai.Client(api_key="AQ.Ab8RN6JmsmTgJQ9J06eMCLo6-dOSFwUyZK4S6lwVMIy8_dW1rg")

# Data structures for tracking session states and leaderboards
LEADERBOARD = {}          # { user_id: {"name": str, "score": int} }
ACTIVE_POLLS = {}         # { poll_id: {"correct_option": int, "subject": str} }
USER_SESSIONS = {}        # { user_id: {"subject": str, "chapter": str, "total_q": int, "delay": int, "mode": str, "timer": int} }

# Complete WBBSE Madhyamik Syllabus Chapters mapping across all 7 subjects
WBBSE_SYLLABUS = {
    "English": [
        "Prose (Father's Help, Passing Away of Bapu, etc.)",
        "Poetry (Fable, The Snail, Sea Fever, etc.)",
        "Rapid Reader (Tales from Shakespeare / The Hound of the Baskervilles)",
        "Grammar & Rhetoric",
        "Writing Skills (Notice, Report, Letter Writing)"
    ],
    "Bengali": [
        "জ্ঞানচক্ষু",
        "অসুখী একজন",
        "আয় আরো বেঁধে বেঁধে থাকি",
        "আফ্রিকা",
        "হারিয়ে যাওয়া কালিকলম",
        "বহুরূপী",
        "অভিষেক",
        "প্রলয় উল্লাস",
        "পথের দাবী",
        "সিন্ধু তীরে",
        "অদল-বদল",
        "অস্ত্রের বিরুদ্ধে গান",
        "নদীর বিদ্রোহ",
        "বাংলা ভাষায় বিজ্ঞান"
    ],
    "Mathematics": [
        "Simple Interest (সরল সুদকষা)",
        "Quadratic Equation in One Variable (একচল বিশিষ্ট দ্বিঘাত সমীকরণ)",
        "Compound Interest & Uniform Rate (চক্রবৃদ্ধি সুদ ও সমহার বৃদ্ধি/হ্রাস)",
        "Theorem & Construction (বৃত্ত সম্পর্কিত উপপাদ্য ও জ্যামিতিক অঙ্কন)",
        "Trigonometry & Heights/Distances (ত্রিকোণমিতি ও উচ্চতা-দূরত্ব)",
        "Mensuration: Sphere, Cone, Cylinder (গোলক, লম্ব বৃত্তাকার চোঙ, শকু)",
        "Statistics: Mean, Median, Ogive, Mode (রাশিবিজ্ঞান)"
    ],
    "History": [
        "Chapter 1: Ideas of History (ইতিহাসের ধারণা)",
        "Chapter 2: Reform: Characteristics and Observations (সংস্কার: বৈশিষ্ট্য ও মূল্যায়ন)",
        "Chapter 3: Resistance and Rebellion: Characteristics and Analyses (প্রতিরোধ ও বিদ্রোহ)",
        "Chapter 4: Early Stages of Collective Action (বিকল্প চিন্তা ও উদ্যোগ)",
        "Chapter 5: Alternative Ideas and Initiatives (শতাব্দীর প্রারম্ভে ছত্রপদ্ধতি)",
        "Chapter 6: Peasant, Working Class and Left Movements (বিংশ শতকের কৃষক, শ্রমিক ও বামপন্থী আন্দোলন)",
        "Chapter 7: Movements Organised by Women, Students & Marginal People (নারী, ছাত্র ও প্রান্তিক জনগোষ্ঠীর আন্দোলন)",
        "Chapter 8: Post-Colonial India: Second half of the 20th Century (উত্তর ঔপনিবেশিক ভারত)"
    ],
    "Geography": [
        "Exogenetic Processes & Resultant Landforms (বহির্জাত প্রক্রিয়া ও গঠিত ভূমিরূপ)",
        "Atmosphere (বায়ুমণ্ডল)",
        "Hydrosphere (বারিুমণ্ডল)",
        "Waste Management (বর্জ্য ব্যবস্থাপনা)",
        "India: Physical & Economic Environment (ভারত: প্রাকৃতিক ও অর্থনৈতিক পরিবেশ)",
        "Satellite Imagery & Topographical Map (উপগ্রহ চিত্র ও ভূবৈচিত্র্যসূচক মানচিত্র)"
    ],
    "Physical Science": [
        "Concerns about Our Environment (আমাদের পরিবেশ)",
        "Behaviour of Gases (গ্যাসের আচরণ)",
        "Chemical Calculations (রাসায়নিক গণনা)",
        "Thermal Phenomena (তাপের ঘটনাসমূহ)",
        "Light (আলো)",
        "Current Electricity (চলতড়িৎ)",
        "Atomic Nucleus (পরমাণু কেন্দ্রক)",
        "Periodic Table & Periodicity (পর্যায় সারণী ও মৌলদের ধর্মের পর্যায়বৃত্ততা)",
        "Ionic and Covalent Bonding (আয়নীয় ও সমযোজী বন্ধন)",
        "Electricity & Chemical Reactions (তড়িৎ ও রাসায়নিক বিক্রিয়া)",
        "Inorganic Chemistry in Lab & Industry (রসায়নাগার ও শিল্পে অজৈব রসায়ন)",
        "Metallurgy (ধাতুবিদ্যা)",
        "Organic Chemistry (অর্গানিক বা জৈব রসায়ন)"
    ],
    "Life Science": [
        "Control and Coordination in Living Organisms (জীবজগতে নিয়ন্ত্রণ ও সমন্বয়)",
        "Continuity of Life (জীবনের প্রবাহমানতা)",
        "Heredity and Some Common Genetic Diseases (বংশগতি এবং কয়েকটি সাধারণ জিনগত রোগ)",
        "Evolution and Adaptation (অভিব্যক্তি ও অভিযোজন)",
        "Environment, Resources & Conservation (পরিবেশ, তার সম্পদ ও সংরক্ষণ)"
    ]
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Professional welcome screen showing subject inline buttons."""
    keyboard = []
    for subject in WBBSE_SYLLABUS.keys():
        keyboard.append([InlineKeyboardButton(f"📘 {subject}", callback_data=f"sub_{subject}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_message = (
        "🎓 **WBBSE Madhyamik Ultimate Board Examination Bot** 🎓\n\n"
        "Powered by **Gemini 3.6 Flash** and structured precisely for WBBSE standards.\n\n"
        "👉 **Please select a subject to begin your customized quiz session:**"
    )
    await update.message.reply_text(welcome_message, parse_mode="Markdown", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all interactive step-by-step inline button choices."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("sub_"):
        subject = data.replace("sub_", "")
        USER_SESSIONS[user_id] = {"subject": subject}
        
        chapters = WBBSE_SYLLABUS.get(subject, [])
        keyboard = []
        for idx, chapter in enumerate(chapters):
            short_name = chapter[:40] + "..." if len(chapter) > 40 else chapter
            keyboard.append([InlineKeyboardButton(short_name, callback_data=f"chap_{idx}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📖 Selected Subject: **{subject}**\n\nNow, select a specific chapter:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif data.startswith("chap_"):
        chap_idx = int(data.replace("chap_", ""))
        sub = USER_SESSIONS.get(user_id, {}).get("subject", "Bengali")
        chapters = WBBSE_SYLLABUS.get(sub, [])
        selected_chapter = chapters[chap_idx] if chap_idx < len(chapters) else "General"
        
        USER_SESSIONS[user_id]["chapter"] = selected_chapter

        keyboard = [
            [InlineKeyboardButton("10 Questions", callback_data="q_10"), InlineKeyboardButton("20 Questions", callback_data="q_20")],
            [InlineKeyboardButton("30 Questions", callback_data="q_30"), InlineKeyboardButton("50 Questions", callback_data="q_50")]
        ]
        await query.edit_message_text(
            f"📌 Chapter: *{selected_chapter}*\n\nHow many questions would you like in this quiz session?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("q_"):
        q_count = int(data.replace("q_", ""))
        USER_SESSIONS[user_id]["total_q"] = q_count

        keyboard = [
            [InlineKeyboardButton("10 Seconds", callback_data="delay_10"), InlineKeyboardButton("15 Seconds", callback_data="delay_15")],
            [InlineKeyboardButton("30 Seconds", callback_data="delay_30")]
        ]
        await query.edit_message_text(
            f"📊 Selected: **{q_count} Questions**\n\nSelect the time delay between consecutive questions:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("delay_"):
        delay_val = int(data.replace("delay_", ""))
        USER_SESSIONS[user_id]["delay"] = delay_val

        keyboard = [
            [InlineKeyboardButton("🔒 Lock Poll (Time bound countdown)", callback_data="mode_lock")],
            [InlineKeyboardButton("🌐 Unlimited Time (Standard open poll)", callback_data="mode_unlimited")]
        ]
        await query.edit_message_text(
            f"⏱️ Delay Interval: **{delay_val}s**\n\nChoose your poll answer pacing mode:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("mode_"):
        mode_type = data.replace("mode_", "")
        USER_SESSIONS[user_id]["mode"] = mode_type

        if mode_type == "lock":
            keyboard = [
                [InlineKeyboardButton("10 Seconds", callback_data="timer_10"), InlineKeyboardButton("15 Seconds", callback_data="timer_15")],
                [InlineKeyboardButton("20 Seconds", callback_data="timer_20"), InlineKeyboardButton("30 Seconds", callback_data="timer_30")]
            ]
            await query.edit_message_text(
                "🔒 **Lock Poll Mode Active**\n\nSelect the locking timer duration for each question:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            USER_SESSIONS[user_id]["timer"] = 0
            await query.edit_message_text("🚀 Setup complete! Starting your WBBSE Madhyamik Quiz Session now...")
            asyncio.create_task(run_quiz_session(query.message.chat_id, user_id, context))

    elif data.startswith("timer_"):
        timer_val = int(data.replace("timer_", ""))
        USER_SESSIONS[user_id]["timer"] = timer_val
        await query.edit_message_text(f"🔒 Locked Polls ({timer_val}s active). Starting your session now...")
        asyncio.create_task(run_quiz_session(query.message.chat_id, user_id, context))

async def run_quiz_session(chat_id, user_id, context):
    """Executes the multi-question loop with error debugging."""
    session = USER_SESSIONS.get(user_id, {})
    subject = session.get("subject", "Bengali")
    chapter = session.get("chapter", "General")
    total_q = session.get("total_q", 10)
    delay = session.get("delay", 10)
    mode = session.get("mode", "unlimited")
    timer_duration = session.get("timer", 0)

    for i in range(1, total_q + 1):
        try:
            prompt = f"""
            You are a senior WBBSE Madhyamik board examiner. 
            Generate 1 unique Multiple Choice Question (MCQ) for Subject: {subject}, Chapter/Topic: {chapter}.
            Difficulty must match standard West Bengal Board class 10 exams. Make sure options are distinct.
            
            Provide your response strictly in the following format with exact headings:
            QUESTION: [Insert question here]
            OPTION_A: [First option]
            OPTION_B: [Second option]
            OPTION_C: [Third option]
            OPTION_D: [Fourth option]
            CORRECT: [A or B or C or D]
            EXPLANATION: [Short explanation]
            """

            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            text_output = response.text
            logger.info(f"Gemini Raw Output: {text_output}")

            lines = text_output.strip().split("\n")
            q_data = {}
            for line in lines:
                if ":" in line:
                    parts = line.split(":", 1)
                    q_data[parts[0].strip()] = parts[1].strip()

            q_text = q_data.get("QUESTION", f"Sample question {i} for {subject}?")
            options = [
                q_data.get("OPTION_A", "Option A"),
                q_data.get("OPTION_B", "Option B"),
                q_data.get("OPTION_C", "Option C"),
                q_data.get("OPTION_D", "Option D")
            ]
            
            # Ensure options are clean strings within Telegram's 100 character limit
            options = [opt[:100] for opt in options]
            q_text = q_text[:300]

            correct_letter = q_data.get("CORRECT", "A").strip().upper()
            if correct_letter not in ["A", "B", "C", "D"]:
                correct_letter = "A"
                
            mapping = {"A": 0, "B": 1, "C": 2, "D": 3}
            correct_idx = mapping.get(correct_letter, 0)
            explanation = q_data.get("EXPLANATION", "WBBSE curriculum standard answer.")[:200]

            # Send Native Telegram Poll
            poll_message = await context.bot.send_poll(
                chat_id=chat_id,
                question=f"[{subject} | Q{i}/{total_q}] {q_text}",
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_idx,
                is_anonymous=False,
                explanation=explanation,
                open_period=timer_duration if mode == "lock" else None
            )

            ACTIVE_POLLS[poll_message.poll.id] = {
                "correct_option": correct_idx,
                "subject": subject
            }

            # Wait for delay duration before serving the next question
            await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"CRITICAL ERROR generating question {i}: {e}")
            # Send a notification message so user knows an error occurred instead of silent failure
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"⚠️ Error generating question {i}. Skipping to next..."
            )
            continue

    # Quiz Completion Summary Message
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎉 **WBBSE Madhyamik Quiz Session Completed!** 🎉\n\n"
            f"You successfully completed your test for **{subject}** (*{chapter}*).\n\n"
            "🏆 Type `/show` to view the latest engaging leaderboard rankings!"
        ),
        parse_mode="Markdown"
    )

async def receive_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tracks responses and awards points behind the scenes."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    user_id = user.id
    username = user.first_name or "Student"

    if poll_id in ACTIVE_POLLS:
        poll_info = ACTIVE_POLLS[poll_id]
        correct_option = poll_info["correct_option"]
        user_selection = answer.option_ids[0]

        if user_id not in LEADERBOARD:
            LEADERBOARD[user_id] = {"name": username, "score": 0}

        if user_selection == correct_option:
            LEADERBOARD[user_id]["score"] += 10

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Isolated command to render the high-engagement leaderboard via /show."""
    if not LEADERBOARD:
        await update.message.reply_text(
            "🏆 **Madhyamik Leaderboard Arena**\n\n"
            "The leaderboard is currently empty! Complete a quiz session using `/start` to earn points.",
            parse_mode="Markdown"
        )
        return

    sorted_users = sorted(LEADERBOARD.values(), key=lambda x: x["score"], reverse=True)

    leaderboard_msg = "🏆 **WBBSE Madhyamik Battle Royale Leaderboard** 🏆\n"
    leaderboard_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for idx, user_data in enumerate(sorted_users[:10]):
        rank_icon = medals[idx] if idx < 3 else f"#{idx + 1}"
        leaderboard_msg += f"{rank_icon} **{user_data['name']}** — 🎯 `{user_data['score']} pts`\n"

    leaderboard_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    leaderboard_msg += "💡 *Run `/start` to start a new subject session and climb higher!*"

    await update.message.reply_text(leaderboard_msg, parse_mode="Markdown")

def main():
    TOKEN = "8706836737:AAGZKFU9s6ueCaCVl-ryY-bApLq_hHT0ryg"
    
    application = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("show", leaderboard_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(PollAnswerHandler(receive_poll_answer))

    print("🤖 Professional WBBSE Madhyamik Quiz Bot running successfully...")
    application.run_polling()

if __name__ == "__main__":
    main()
