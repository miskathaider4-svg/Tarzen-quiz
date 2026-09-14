"""
WBBSE Class 10 Madhyamik AI Quiz Bot
====================================

Tech stack:
    - Python 3.10+
    - python-telegram-bot 21+
    - google-genai
    - Gemini 2.5 Flash

Designed for PythonAnywhere.

Before running:
    export TELEGRAM_TOKEN="YOUR_NEW_TELEGRAM_TOKEN"
    export GEMINI_API_KEY="YOUR_NEW_GEMINI_API_KEY"

Install:
    pip3 install --user -U python-telegram-bot google-genai

Test syntax:
    python3 -m py_compile bot.py

Run:
    python3 bot.py
"""

import asyncio
import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_TOKEN = os.environ.get("8706836737:AAG2NjJA2g7tYUr37u--QKTsqN_-Y80Lk1E").strip()
GEMINI_API_KEY = os.environ.get("AQ.Ab8RN6IRsvyNA7cpoEzeVkhaZ_yhGHN9rNicxXmC2wDeCStF_w").strip()

GEMINI_MODEL = "gemini-2.5-flash"

NUMBER_OF_QUESTIONS = 3


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# GEMINI CLIENT
# ============================================================

if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    gemini_client = None


# ============================================================
# SUBJECTS
# ============================================================

SUBJECTS = {
    "math": "Mathematics",
    "physical": "Physical Science",
    "life": "Life Science",
    "history": "History",
    "geography": "Geography",
}


DIFFICULTIES = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
}


LANGUAGES = {
    "bn": "Bengali",
    "en": "English",
}


# ============================================================
# TEXT HELPERS
# ============================================================

def get_medium_name(medium_key: str) -> str:
    """Return a readable medium name."""
    return LANGUAGES.get(medium_key, "English")


def get_subject_name(subject_key: str) -> str:
    """Return a readable subject name."""
    return SUBJECTS.get(subject_key, "Unknown")


def get_difficulty_name(difficulty_key: str) -> str:
    """Return a readable difficulty name."""
    return DIFFICULTIES.get(difficulty_key, "Unknown")


# ============================================================
# KEYBOARDS
# ============================================================

def medium_keyboard() -> InlineKeyboardMarkup:
    """Create the medium selection keyboard."""

    keyboard = [
        [
            InlineKeyboardButton(
                "📚 Bengali Medium (বাংলা মাধ্যম)",
                callback_data="medium:bn",
            )
        ],
        [
            InlineKeyboardButton(
                "📚 English Medium",
                callback_data="medium:en",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def subject_keyboard() -> InlineKeyboardMarkup:
    """Create the subject selection keyboard."""

    keyboard = [
        [
            InlineKeyboardButton(
                "➗ Mathematics",
                callback_data="subject:math",
            ),
            InlineKeyboardButton(
                "⚛️ Physical Science",
                callback_data="subject:physical",
            ),
        ],
        [
            InlineKeyboardButton(
                "🧬 Life Science",
                callback_data="subject:life",
            ),
            InlineKeyboardButton(
                "📜 History",
                callback_data="subject:history",
            ),
        ],
        [
            InlineKeyboardButton(
                "🌍 Geography",
                callback_data="subject:geography",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 Change Medium",
                callback_data="back:medium",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def difficulty_keyboard() -> InlineKeyboardMarkup:
    """Create the difficulty selection keyboard."""

    keyboard = [
        [
            InlineKeyboardButton(
                "🟢 Easy",
                callback_data="difficulty:easy",
            ),
            InlineKeyboardButton(
                "🟡 Medium",
                callback_data="difficulty:medium",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔴 Hard",
                callback_data="difficulty:hard",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Change Subject",
                callback_data="back:subject",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def answer_keyboard(
    question_number: int,
    options: list[str],
) -> InlineKeyboardMarkup:
    """Create the answer buttons."""

    keyboard = []

    letters = ["A", "B", "C", "D"]

    for index, option in enumerate(options):
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{letters[index]}. {option}",
                    callback_data=(
                        f"answer:{question_number}:{index}"
                    ),
                )
            ]
        )

    return InlineKeyboardMarkup(keyboard)


def retry_keyboard(
    difficulty: str,
) -> InlineKeyboardMarkup:
    """Keyboard shown when Gemini generation fails."""

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Try Again",
                callback_data=f"difficulty:{difficulty}",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Change Subject",
                callback_data="back:subject",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def result_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after quiz completion."""

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Another Quiz",
                callback_data="back:subject",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Start Over",
                callback_data="back:medium",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# USER STATE
# ============================================================

def clear_quiz_state(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Remove quiz-specific state."""

    keys = [
        "medium",
        "subject",
        "difficulty",
        "questions",
        "current_question",
        "score",
        "answered",
    ]

    for key in keys:
        context.user_data.pop(key, None)


def initialize_quiz(
    context: ContextTypes.DEFAULT_TYPE,
    questions: list[dict[str, Any]],
) -> None:
    """Initialize a new quiz."""

    context.user_data["questions"] = questions
    context.user_data["current_question"] = 0
    context.user_data["score"] = 0
    context.user_data["answered"] = False


# ============================================================
# GEMINI PROMPT
# ============================================================

def build_prompt(
    language: str,
    subject: str,
    difficulty: str,
) -> str:
    """Build the Gemini question-generation prompt."""

    if language == "Bengali":
        language_instruction = """
Write every question and every answer option in natural,
clear Bengali suitable for a Class 10 WBBSE Madhyamik student.
Do not use unnecessary English words.
Use standard Bengali educational terminology where appropriate.
"""
    else:
        language_instruction = """
Write every question and every answer option in clear,
natural English suitable for a Class 10 WBBSE Madhyamik student.
"""

    prompt = f"""
You are an expert teacher and examination question setter
for the West Bengal Board of Secondary Education (WBBSE).

Generate exactly {NUMBER_OF_QUESTIONS} multiple-choice questions.

CLASS:
Class 10 Madhyamik

BOARD:
WBBSE - West Bengal Board of Secondary Education

SUBJECT:
{subject}

DIFFICULTY:
{difficulty}

LANGUAGE:
{language}

{language_instruction}

IMPORTANT REQUIREMENTS:

1. Questions must be appropriate for the WBBSE Class 10
   Madhyamik syllabus.

2. Questions must test genuine subject knowledge.

3. Do not ask university-level questions.

4. Do not ask questions unrelated to the WBBSE syllabus.

5. Generate exactly {NUMBER_OF_QUESTIONS} questions.

6. Each question must have exactly four options.

7. There must be exactly one correct answer.

8. answer_index must be zero-based:
   0 = first option
   1 = second option
   2 = third option
   3 = fourth option

9. Do not repeat questions.

10. Avoid ambiguous questions.

11. Do not include explanations.

12. Do not include Markdown.

13. Do not include ``` or code fences.

14. Return only the JSON object.

The JSON must have exactly this general structure:

{{
  "questions": [
    {{
      "question": "Question text",
      "options": [
        "Option 1",
        "Option 2",
        "Option 3",
        "Option 4"
      ],
      "answer_index": 0
    }}
  ]
}}
"""

    return prompt


# ============================================================
# JSON EXTRACTION
# ============================================================

def parse_json_response(
    text: str,
) -> dict[str, Any]:
    """Safely parse Gemini's JSON response."""

    if not text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    cleaned = text.strip()

    # Remove accidental Markdown fences if Gemini adds them.
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    # Normal JSON parsing.
    try:
        parsed = json.loads(cleaned)
        return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: locate the JSON object.
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")

    if first_brace == -1 or last_brace == -1:
        raise ValueError(
            "No JSON object was found in Gemini response."
        )

    json_text = cleaned[
        first_brace:last_brace + 1
    ]

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Gemini returned invalid JSON."
        ) from exc

    return parsed


# ============================================================
# QUESTION VALIDATION
# ============================================================

def validate_questions(
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate the complete Gemini quiz."""

    if not isinstance(data, dict):
        raise ValueError(
            "Gemini response is not a JSON object."
        )

    questions = data.get("questions")

    if not isinstance(questions, list):
        raise ValueError(
            "'questions' is not a list."
        )

    if len(questions) != NUMBER_OF_QUESTIONS:
        raise ValueError(
            f"Expected {NUMBER_OF_QUESTIONS} questions, "
            f"received {len(questions)}."
        )

    validated = []

    for number, item in enumerate(
        questions,
        start=1,
    ):
        if not isinstance(item, dict):
            raise ValueError(
                f"Question {number} is invalid."
            )

        question = item.get("question")
        options = item.get("options")
        answer_index = item.get("answer_index")

        if not isinstance(question, str):
            raise ValueError(
                f"Question {number} text is invalid."
            )

        question = question.strip()

        if not question:
            raise ValueError(
                f"Question {number} is empty."
            )

        if not isinstance(options, list):
            raise ValueError(
                f"Question {number} options are invalid."
            )

        if len(options) != 4:
            raise ValueError(
                f"Question {number} must have "
                "exactly four options."
            )

        cleaned_options = []

        for option_number, option in enumerate(
            options,
            start=1,
        ):
            if not isinstance(option, str):
                raise ValueError(
                    f"Question {number}, option "
                    f"{option_number} is invalid."
                )

            option = option.strip()

            if not option:
                raise ValueError(
                    f"Question {number}, option "
                    f"{option_number} is empty."
                )

            cleaned_options.append(option)

        if (
            not isinstance(answer_index, int)
            or isinstance(answer_index, bool)
        ):
            raise ValueError(
                f"Question {number} answer_index "
                "is invalid."
            )

        if answer_index < 0 or answer_index > 3:
            raise ValueError(
                f"Question {number} answer_index "
                "must be between 0 and 3."
            )

        validated.append(
            {
                "question": question,
                "options": cleaned_options,
                "answer_index": answer_index,
            }
        )

    return validated


# ============================================================
# GEMINI API CALL
# ============================================================

async def generate_questions(
    language: str,
    subject: str,
    difficulty: str,
) -> list[dict[str, Any]]:
    """Generate and validate questions using Gemini."""

    if gemini_client is None:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    prompt = build_prompt(
        language=language,
        subject=subject,
        difficulty=difficulty,
    )

    def make_request() -> str:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )

        if not response.text:
            raise ValueError(
                "Gemini returned no text."
            )

        return response.text

    raw_text = await asyncio.to_thread(
        make_request
    )

    parsed = parse_json_response(raw_text)

    return validate_questions(parsed)


# ============================================================
# START COMMAND
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /start."""

    clear_quiz_state(context)

    user = update.effective_user

    if user is not None and user.first_name:
        greeting = (
            f"👋 Hello, {user.first_name}!"
        )
    else:
        greeting = "👋 Hello!"

    text = (
        f"{greeting}\n\n"
        "🎓 Welcome to the WBBSE Class 10 "
        "Madhyamik Quiz Bot!\n\n"
        "You will get 3 AI-generated multiple-choice "
        "questions based on the Madhyamik syllabus.\n\n"
        "📚 Please choose your medium:"
    )

    if update.message:
        await update.message.reply_text(
            text=text,
            reply_markup=medium_keyboard(),
        )


# ============================================================
# SHOW SUBJECTS
# ============================================================

async def show_subjects(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show subject selection."""

    medium = context.user_data.get(
        "medium",
        "en",
    )

    if medium == "bn":
        text = (
            "📚 বাংলা মাধ্যম নির্বাচিত হয়েছে।\n\n"
            "এখন একটি বিষয় নির্বাচন করুন:"
        )
    else:
        text = (
            "📚 English Medium selected.\n\n"
            "Please choose a subject:"
        )

    await query.edit_message_text(
        text=text,
        reply_markup=subject_keyboard(),
    )


# ============================================================
# SHOW DIFFICULTIES
# ============================================================

async def show_difficulties(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show difficulty selection."""

    medium = context.user_data.get(
        "medium",
        "en",
    )

    subject_key = context.user_data.get(
        "subject"
    )

    subject = get_subject_name(
        subject_key
    )

    if medium == "bn":
        text = (
            f"📚 বিষয়: {subject}\n\n"
            "🎯 কঠিনতার স্তর নির্বাচন করুন:"
        )
    else:
        text = (
            f"📚 Subject: {subject}\n\n"
            "🎯 Choose the difficulty level:"
        )

    await query.edit_message_text(
        text=text,
        reply_markup=difficulty_keyboard(),
    )


# ============================================================
# SEND QUESTION
# ============================================================

async def send_current_question(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Send the current question."""

    questions = context.user_data.get(
        "questions",
        [],
    )

    current = context.user_data.get(
        "current_question",
        0,
    )

    if not questions:
        await query.edit_message_text(
            "Quiz data is missing. Please use /start."
        )
        return

    if current >= len(questions):
        await finish_quiz(
            query,
            context,
        )
        return

    quiz_question = questions[current]

    medium = context.user_data.get(
        "medium",
        "en",
    )

    total = len(questions)

    if medium == "bn":
        text = (
            f"📝 প্রশ্ন {current + 1}/{total}\n\n"
            f"{quiz_question['question']}"
        )
    else:
        text = (
            f"📝 Question {current + 1}/{total}\n\n"
            f"{quiz_question['question']}"
        )

    context.user_data["answered"] = False

    await query.edit_message_text(
        text=text,
        reply_markup=answer_keyboard(
            current,
            quiz_question["options"],
        ),
    )


# ============================================================
# FINISH QUIZ
# ============================================================

async def finish_quiz(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Display final quiz result."""

    score = context.user_data.get(
        "score",
        0,
    )

    questions = context.user_data.get(
        "questions",
        [],
    )

    total = len(questions)

    medium = context.user_data.get(
        "medium",
        "en",
    )

    subject = get_subject_name(
        context.user_data.get(
            "subject",
            "",
        )
    )

    difficulty = get_difficulty_name(
        context.user_data.get(
            "difficulty",
            "",
        )
    )

    percentage = (
        round((score / total) * 100)
        if total
        else 0
    )

    if medium == "bn":
        text = (
            "🎉 কুইজ শেষ!\n\n"
            f"📚 বিষয়: {subject}\n"
            f"🎯 কঠিনতা: {difficulty}\n\n"
            f"🏆 আপনার স্কোর: {score}/{total}\n"
            f"📊 শতাংশ: {percentage}%\n\n"
            "আবার কুইজ দিতে নিচের বোতাম চাপুন।"
        )
    else:
        text = (
            "🎉 Quiz Complete!\n\n"
            f"📚 Subject: {subject}\n"
            f"🎯 Difficulty: {difficulty}\n\n"
            f"🏆 Your Score: {score}/{total}\n"
            f"📊 Percentage: {percentage}%\n\n"
            "Choose an option below to continue."
        )

    await query.edit_message_text(
        text=text,
        reply_markup=result_keyboard(),
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle all inline keyboard buttons."""

    query = update.callback_query

    if query is None:
        return

    await query.answer()

    data = query.data or ""

    # --------------------------------------------------------
    # MEDIUM
    # --------------------------------------------------------

    if data.startswith("medium:"):

        medium = data.split(
            ":",
            1,
        )[1]

        if medium not in LANGUAGES:
            await query.edit_message_text(
                "Invalid medium. Please use /start."
            )
            return

        clear_quiz_state(context)

        context.user_data["medium"] = medium

        await show_subjects(
            query,
            context,
        )

        return

    # --------------------------------------------------------
    # BACK TO MEDIUM
    # --------------------------------------------------------

    if data == "back:medium":

        clear_quiz_state(context)

        await query.edit_message_text(
            text=(
                "👋 Let's start again.\n\n"
                "📚 Please choose your medium:"
            ),
            reply_markup=medium_keyboard(),
        )

        return

    # --------------------------------------------------------
    # SUBJECT
    # --------------------------------------------------------

    if data.startswith("subject:"):

        subject = data.split(
            ":",
            1,
        )[1]

        if subject not in SUBJECTS:
            await query.edit_message_text(
                "Invalid subject. Please use /start."
            )
            return

        if "medium" not in context.user_data:
            await query.edit_message_text(
                "Your session expired. "
                "Please use /start."
            )
            return

        context.user_data["subject"] = subject

        await show_difficulties(
            query,
            context,
        )

        return

    # --------------------------------------------------------
    # BACK TO SUBJECT
    # --------------------------------------------------------

    if data == "back:subject":

        context.user_data.pop(
            "difficulty",
            None,
        )

        context.user_data.pop(
            "questions",
            None,
        )

        context.user_data.pop(
            "current_question",
            None,
        )

        context.user_data.pop(
            "score",
            None,
        )

        context.user_data.pop(
            "answered",
            None,
        )

        if "medium" not in context.user_data:
            await query.edit_message_text(
                text=(
                    "📚 Please choose your medium:"
                ),
                reply_markup=medium_keyboard(),
            )
            return

        await show_subjects(
            query,
            context,
        )

        return

    # --------------------------------------------------------
    # DIFFICULTY
    # --------------------------------------------------------

    if data.startswith("difficulty:"):

        difficulty = data.split(
            ":",
            1,
        )[1]

        if difficulty not in DIFFICULTIES:
            await query.edit_message_text(
                "Invalid difficulty. "
                "Please use /start."
            )
            return

        medium_key = context.user_data.get(
            "medium"
        )

        subject_key = context.user_data.get(
            "subject"
        )

        if medium_key not in LANGUAGES:
            await query.edit_message_text(
                "Your session expired. "
                "Please use /start."
            )
            return

        if subject_key not in SUBJECTS:
            await query.edit_message_text(
                "Your session expired. "
                "Please use /start."
            )
            return

        context.user_data["difficulty"] = (
            difficulty
        )

        language = get_medium_name(
            medium_key
        )

        subject = get_subject_name(
            subject_key
        )

        difficulty_name = (
            get_difficulty_name(difficulty)
        )

        if medium_key == "bn":
            loading_text = (
                "⏳ প্রশ্ন তৈরি হচ্ছে...\n\n"
                f"📚 বিষয়: {subject}\n"
                f"🎯 কঠিনতা: {difficulty_name}\n\n"
                "একটু অপেক্ষা করুন..."
            )
        else:
            loading_text = (
                "⏳ Generating your quiz...\n\n"
                f"📚 Subject: {subject}\n"
                f"🎯 Difficulty: {difficulty_name}\n\n"
                "Please wait..."
            )

        await query.edit_message_text(
            text=loading_text
        )

        try:
            questions = await generate_questions(
                language=language,
                subject=subject,
                difficulty=difficulty_name,
            )

        except Exception as exc:
            logger.exception(
                "Gemini question generation failed: %s",
                exc,
            )

            if medium_key == "bn":
                error_text = (
                    "❌ দুঃখিত, এই মুহূর্তে "
                    "প্রশ্ন তৈরি করা সম্ভব হয়নি।\n\n"
                    "আবার চেষ্টা করুন।"
                )
            else:
                error_text = (
                    "❌ Sorry, I couldn't generate "
                    "the quiz right now.\n\n"
                    "Please try again."
                )

            await query.edit_message_text(
                text=error_text,
                reply_markup=retry_keyboard(
                    difficulty
                ),
            )

            return

        initialize_quiz(
            context,
            questions,
        )

        await send_current_question(
            query,
            context,
        )

        return

    # --------------------------------------------------------
    # ANSWER
    # --------------------------------------------------------

    if data.startswith("answer:"):

        parts = data.split(":")

        if len(parts) != 3:
            await query.answer(
                "Invalid answer.",
                show_alert=True,
            )
            return

        try:
            question_number = int(parts[1])
            selected_index = int(parts[2])
        except ValueError:
            await query.answer(
                "Invalid answer.",
                show_alert=True,
            )
            return

        questions = context.user_data.get(
            "questions",
            [],
        )

        current = context.user_data.get(
            "current_question",
            0,
        )

        # Protect against stale button presses.
        if question_number != current:
            await query.answer(
                "This question has already been answered.",
                show_alert=False,
            )
            return

        if current < 0 or current >= len(
            questions
        ):
            await query.answer(
                "Quiz session expired.",
                show_alert=True,
            )
            return

        if selected_index < 0 or selected_index > 3:
            await query.answer(
                "Invalid answer.",
                show_alert=True,
            )
            return

        # Prevent double clicking.
        if context.user_data.get(
            "answered",
            False,
        ):
            await query.answer(
                "Already answered.",
                show_alert=False,
            )
            return

        context.user_data["answered"] = True

        quiz_question = questions[current]

        correct_index = quiz_question[
            "answer_index"
        ]

        is_correct = (
            selected_index == correct_index
        )

        if is_correct:
            context.user_data["score"] = (
                context.user_data.get(
                    "score",
                    0,
                )
                + 1
            )

        # Move forward.
        context.user_data[
            "current_question"
        ] = current + 1

        medium = context.user_data.get(
            "medium",
            "en",
        )

        if medium == "bn":

            if is_correct:
                feedback = (
                    "✅ সঠিক উত্তর!"
                )
            else:
                correct_option = (
                    quiz_question["options"][
                        correct_index
                    ]
                )

                feedback = (
                    "❌ ভুল উত্তর!\n\n"
                    f"সঠিক উত্তর: {correct_option}"
                )

        else:

            if is_correct:
                feedback = "✅ Correct!"
            else:
                correct_option = (
                    quiz_question["options"][
                        correct_index
                    ]
                )

                feedback = (
                    "❌ Incorrect!\n\n"
                    f"Correct answer: {correct_option}"
                )

        next_question_exists = (
            context.user_data[
                "current_question"
            ] < len(questions)
        )

        await query.edit_message_text(
            text=feedback
        )

        await asyncio.sleep(0.8)

        if next_question_exists:
            await send_current_question(
                query,
                context,
            )
        else:
            await finish_quiz(
                query,
                context,
            )

        return

    # --------------------------------------------------------
    # UNKNOWN CALLBACK
    # --------------------------------------------------------

    await query.answer(
        "Unknown selection.",
        show_alert=True,
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle unexpected Telegram errors."""

    logger.exception(
        "Unhandled exception: %s",
        context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    """Start the Telegram bot."""

    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN environment variable "
            "is not set."
        )

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable "
            "is not set."
        )

    # --------------------------------------------------------
    # PYTHONANYWHERE FREE-TIER PROXY
    # --------------------------------------------------------

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .proxy("http://proxy.server:3128")
        .get_updates_proxy(
            "http://proxy.server:3128"
        )
        .build()
    )

    # --------------------------------------------------------
    # TELEGRAM HANDLERS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "========================================"
    )

    logger.info(
        "WBBSE Madhyamik Quiz Bot starting..."
    )

    logger.info(
        "Gemini model: %s",
        GEMINI_MODEL,
    )

    logger.info(
        "Questions per quiz: %s",
        NUMBER_OF_QUESTIONS,
    )

    logger.info(
        "========================================"
    )

    # --------------------------------------------------------
    # START POLLING
    # --------------------------------------------------------

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
