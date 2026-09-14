import asyncio
import json
import logging
import os
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_TOKEN = "8706836737:AAG2NjJA2g7tYUr37u--QKTsqN_-Y80Lk1E"
GEMINI_API_KEY = "AQ.Ab8RN6IRsvyNA7cpoEzeVkhaZ_yhGHN9rNicxXmC2wDeCStF_w"

GEMINI_MODEL = "gemini-2.5-flash"

# Quiz configuration
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

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


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
# HELPER FUNCTIONS
# ============================================================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting the medium."""

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
    """Keyboard for selecting a subject."""

    keyboard = [
        [
            InlineKeyboardButton("➗ Mathematics", callback_data="subject:math"),
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
    """Keyboard for selecting difficulty."""

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


def quiz_options_keyboard(
    question_number: int,
    options: list[str],
) -> InlineKeyboardMarkup:
    """Create the answer keyboard for a quiz question."""

    keyboard = []

    for index, option in enumerate(options):
        # Telegram callback_data has a practical size limitation,
        # so only send the option index, not the full option text.
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{chr(65 + index)}. {option}",
                    callback_data=f"answer:{question_number}:{index}",
                )
            ]
        )

    return InlineKeyboardMarkup(keyboard)


def reset_quiz(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the current quiz state."""

    for key in (
        "medium",
        "subject",
        "difficulty",
        "questions",
        "current_question",
        "score",
    ):
        context.user_data.pop(key, None)


# ============================================================
# GEMINI QUESTION GENERATION
# ============================================================

def build_gemini_prompt(
    language: str,
    subject: str,
    difficulty: str,
) -> str:
    """Create the prompt used to generate the quiz."""

    language_instruction = (
        "Bengali (বাংলা). Use natural, student-friendly Bengali."
        if language == "Bengali"
        else
        "English. Use clear, student-friendly English."
    )

    return f"""
You are an expert WBBSE (West Bengal Board of Secondary Education)
Class 10 Madhyamik teacher and examination question setter.

Generate exactly {NUMBER_OF_QUESTIONS} high-quality multiple-choice
questions for a Class 10 Madhyamik student.

Subject: {subject}
Difficulty: {difficulty}
Question language: {language_instruction}

Requirements:
1. Questions must be relevant to the WBBSE Class 10 Madhyamik syllabus.
2. Do not use undergraduate, competitive-exam, or unrelated material.
3. Each question must have exactly 4 answer options.
4. There must be exactly one correct answer.
5. The answer_index must be zero-based:
   0 = first option
   1 = second option
   2 = third option
   3 = fourth option.
6. Make the questions educational and factually accurate.
7. Avoid ambiguous questions.
8. Do not repeat questions.
9. Do not include explanations.
10. Do not include Markdown.
11. Do not include any text before or after the JSON.

Return STRICTLY valid JSON in exactly this structure:

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


def extract_json(text: str) -> dict[str, Any]:
    """
    Parse Gemini output as JSON.

    This also tolerates accidental Markdown code fences while still
    validating the actual JSON structure.
    """

    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        # Remove opening ```json / ```
        if lines:
            lines = lines[1:]

        # Remove closing ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    # First try normal JSON parsing.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: locate the outer JSON object.
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini did not return a JSON object.")

    return json.loads(text[start:end + 1])


def validate_questions(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate Gemini's generated quiz structure."""

    if not isinstance(data, dict):
        raise ValueError("Gemini response is not a JSON object.")

    questions = data.get("questions")

    if not isinstance(questions, list):
        raise ValueError("'questions' must be a list.")

    if len(questions) != NUMBER_OF_QUESTIONS:
        raise ValueError(
            f"Expected {NUMBER_OF_QUESTIONS} questions, "
            f"received {len(questions)}."
        )

    validated = []

    for number, item in enumerate(questions, start=1):

        if not isinstance(item, dict):
            raise ValueError(f"Question {number} is not an object.")

        question = item.get("question")
        options = item.get("options")
        answer_index = item.get("answer_index")

        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Question {number} has invalid text.")

        if not isinstance(options, list) or len(options) != 4:
            raise ValueError(
                f"Question {number} must contain exactly 4 options."
            )

        if not all(isinstance(option, str) and option.strip()
                   for option in options):
            raise ValueError(
                f"Question {number} contains an invalid option."
            )

        if (
            not isinstance(answer_index, int)
            or isinstance(answer_index, bool)
            or answer_index not in range(4)
        ):
            raise ValueError(
                f"Question {number} has an invalid answer_index."
            )

        validated.append(
            {
                "question": question.strip(),
                "options": [option.strip() for option in options],
                "answer_index": answer_index,
            }
        )

    return validated


async def generate_questions(
    language: str,
    subject: str,
    difficulty: str,
) -> list[dict[str, Any]]:
    """
    Generate questions with Gemini.

    The synchronous google-genai call is moved to a worker thread so
    it doesn't block Telegram's asyncio event loop.
    """

    prompt = build_gemini_prompt(
        language=language,
        subject=subject,
        difficulty=difficulty,
    )

    def call_gemini() -> str:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        if not response.text:
            raise ValueError("Gemini returned an empty response.")

        return response.text

    raw_response = await asyncio.to_thread(call_gemini)

    data = extract_json(raw_response)

    return validate_questions(data)


# ============================================================
# DISPLAY QUESTIONS
# ============================================================

async def send_current_question(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Display the current quiz question."""

    questions = context.user_data.get("questions", [])
    current_question = context.user_data.get("current_question", 0)

    if current_question >= len(questions):
        await finish_quiz(query, context)
        return

    quiz_question = questions[current_question]

    medium = context.user_data.get("medium", "en")
    total = len(questions)

    if medium == "bn":
        question_header = (
            f"📝 প্রশ্ন {current_question + 1}/{total}\n\n"
            f"{quiz_question['question']}"
        )
    else:
        question_header = (
            f"📝 Question {current_question + 1}/{total}\n\n"
            f"{quiz_question['question']}"
        )

    await query.edit_message_text(
        text=question_header,
        reply_markup=quiz_options_keyboard(
            current_question,
            quiz_question["options"],
        ),
    )


async def finish_quiz(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Display the final score."""

    score = context.user_data.get("score", 0)
    questions = context.user_data.get("questions", [])

    total = len(questions)

    medium = context.user_data.get("medium", "en")

    subject_key = context.user_data.get("subject", "")
    difficulty_key = context.user_data.get("difficulty", "")

    subject = SUBJECTS.get(subject_key, "Unknown")
    difficulty = DIFFICULTIES.get(difficulty_key, "Unknown")

    if medium == "bn":
        text = (
            "🎉 কুইজ শেষ!\n\n"
            f"📚 বিষয়: {subject}\n"
            f"🎯 কঠিনতা: {difficulty}\n\n"
            f"🏆 আপনার স্কোর: {score}/{total}\n\n"
            "আবার খেলতে নিচের বোতামটি চাপুন।"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄 আবার কুইজ দিন",
                        callback_data="back:subject",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 নতুন করে শুরু করুন",
                        callback_data="back:medium",
                    )
                ],
            ]
        )

    else:
        percentage = round((score / total) * 100) if total else 0

        text = (
            "🎉 Quiz Complete!\n\n"
            f"📚 Subject: {subject}\n"
            f"🎯 Difficulty: {difficulty}\n\n"
            f"🏆 Your Score: {score}/{total}\n"
            f"📊 Percentage: {percentage}%\n\n"
            "Choose an option below to play again."
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄 Take Another Quiz",
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
        )

    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /start."""

    reset_quiz(context)

    text = (
        "👋 Welcome to the WBBSE Class 10 Madhyamik Quiz Bot!\n\n"
        "Test your knowledge with AI-generated questions based "
        "on the Madhyamik syllabus.\n\n"
        "Please choose your medium:"
    )

    if update.effective_user:
        text = (
            f"👋 Hello, {update.effective_user.first_name}!\n\n"
            "Welcome to the WBBSE Class 10 Madhyamik Quiz Bot.\n\n"
            "Test your knowledge with AI-generated questions based "
            "on the Madhyamik syllabus.\n\n"
            "Please choose your medium:"
        )

    if update.message:
        await update.message.reply_text(
            text=text,
            reply_markup=main_menu_keyboard(),
        )


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle all inline keyboard interactions."""

    query = update.callback_query

    if query is None:
        return

    await query.answer()

    data = query.data or ""

    # --------------------------------------------------------
    # MEDIUM SELECTION
    # --------------------------------------------------------

    if data.startswith("medium:"):

        medium = data.split(":", 1)[1]

        if medium not in LANGUAGES:
            await query.edit_message_text(
                "Invalid medium selection. Please use /start."
            )
            return

        context.user_data.clear()
        context.user_data["medium"] = medium

        if medium == "bn":
            text = (
                "📚 মাধ্যম: বাংলা\n\n"
                "এখন একটি বিষয় নির্বাচন করুন:"
            )
        else:
            text = (
                "📚 Medium: English\n\n"
                "Please choose a subject:"
            )

        await query.edit_message_text(
            text=text,
            reply_markup=subject_keyboard(),
        )

        return

    # --------------------------------------------------------
    # BACK TO MEDIUM
    # --------------------------------------------------------

    if data == "back:medium":

        reset_quiz(context)

        await query.edit_message_text(
            text="Please choose your medium:",
            reply_markup=main_menu_keyboard(),
        )

        return

    # --------------------------------------------------------
    # SUBJECT SELECTION
    # --------------------------------------------------------

    if data.startswith("subject:"):

        subject = data.split(":", 1)[1]

        if subject not in SUBJECTS:
            await query.edit_message_text(
                "Invalid subject selection. Please use /start."
            )
            return

        context.user_data["subject"] = subject

        medium = context.user_data.get("medium", "en")

        if medium == "bn":
            text = (
                f"📚 বিষয়: {SUBJECTS[subject]}\n\n"
                "🎯 কঠিনতার স্তর নির্বাচন করুন:"
            )
        else:
            text = (
                f"📚 Subject: {SUBJECTS[subject]}\n\n"
                "🎯 Choose the difficulty level:"
            )

        await query.edit_message_text(
            text=text,
            reply_markup=difficulty_keyboard(),
        )

        return

    # --------------------------------------------------------
    # BACK TO SUBJECT
    # --------------------------------------------------------

    if data == "back:subject":

        context.user_data.pop("difficulty", None)
        context.user_data.pop("questions", None)
        context.user_data.pop("current_question", None)
        context.user_data.pop("score", None)

        medium = context.user_data.get("medium", "en")

        if medium == "bn":
            text = "📚 একটি বিষয় নির্বাচন করুন:"
        else:
            text = "📚 Please choose a subject:"

        await query.edit_message_text(
            text=text,
            reply_markup=subject_keyboard(),
        )

        return

    # --------------------------------------------------------
    # DIFFICULTY SELECTION
    # --------------------------------------------------------

    if data.startswith("difficulty:"):

        difficulty = data.split(":", 1)[1]

        if difficulty not in DIFFICULTIES:
            await query.edit_message_text(
                "Invalid difficulty selection. Please use /start."
            )
            return

        subject_key = context.user_data.get("subject")
        medium_key = context.user_data.get("medium")

        if subject_key not in SUBJECTS or medium_key not in LANGUAGES:
            await query.edit_message_text(
                "Your session has expired. Please use /start."
            )
            return

        context.user_data["difficulty"] = difficulty

        subject = SUBJECTS[subject_key]
        language = LANGUAGES[medium_key]
        difficulty_name = DIFFICULTIES[difficulty]

        if medium_key == "bn":
            loading_text = (
                "⏳ প্রশ্ন তৈরি হচ্ছে...\n\n"
                f"বিষয়: {subject}\n"
                f"কঠিনতা: {difficulty_name}\n\n"
                "একটু অপেক্ষা করুন।"
            )
        else:
            loading_text = (
                "⏳ Generating your quiz...\n\n"
                f"Subject: {subject}\n"
                f"Difficulty: {difficulty_name}\n\n"
                "Please wait."
            )

        await query.edit_message_text(text=loading_text)

        try:
            questions = await generate_questions(
                language=language,
                subject=subject,
                difficulty=difficulty_name,
            )

        except Exception as exc:
            logger.exception(
                "Failed to generate Gemini questions: %s",
                exc,
            )

            if medium_key == "bn":
                error_text = (
                    "❌ দুঃখিত, এই মুহূর্তে প্রশ্ন তৈরি করা সম্ভব হয়নি。\n\n"
                    "আবার চেষ্টা করতে নিচের বোতামট
