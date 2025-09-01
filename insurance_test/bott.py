import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile, ReplyKeyboardRemove
from aiogram.utils import executor
import csv
import os

from questions import TEST_QUESTIONS

API_TOKEN = "8035255326:AAEQ9ZVC2jfXQJ6bIHXy6mKDfJ4vunFJLuE"
ADMIN_IDS = [623765402]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

user_sessions = {}

def build_keyboard(options):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for opt in options:
        kb.add(KeyboardButton(opt))
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_sessions[message.from_user.id] = {
        "step": 0,
        "answers": [],
        "name": None,
        "waiting_name": True,
        "user_id": message.from_user.id
    }
    await message.answer(
        "Добро пожаловать в тест!\n\n"
        "Пожалуйста, введите ваше имя (фамилию и имя через пробел).\n"
        "Для отмены — /cancel"
    )

async def send_question(message):
    session = user_sessions.get(message.from_user.id)
    if session is None:
        return await message.answer("Ошибка! Попробуйте /start заново.")
    step = session["step"]
    if step < len(TEST_QUESTIONS):
        q = TEST_QUESTIONS[step]
        await message.answer(
            f"Вопрос {step+1} из {len(TEST_QUESTIONS)}:\n\n{q['question']}",
            reply_markup=build_keyboard(q["options"])
        )
    else:
        await show_results(message)

@dp.message_handler(commands=["cancel"])
async def cmd_cancel(message: types.Message):
    user_sessions.pop(message.from_user.id, None)
    await message.answer("Тест отменён. Чтобы начать заново: /start", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(lambda m: m.from_user.id in user_sessions)
async def handle_answer(message: types.Message):
    session = user_sessions[message.from_user.id]
    if session.get("waiting_name", False):
        name = message.text.strip()
        if len(name.split()) < 2:
            await message.answer("Пожалуйста, введите фамилию и имя полностью.")
            return
        session["name"] = name
        session["waiting_name"] = False
        await message.answer(f"Спасибо, {name}! Теперь начнем тест.")
        await send_question(message)
        return

    step = session["step"]
    if step >= len(TEST_QUESTIONS):
        return
    answer = message.text.strip()
    valid_options = [opt.split(" ")[0] for opt in TEST_QUESTIONS[step]["options"]]
    if not any(answer.startswith(x) for x in valid_options):
        await message.answer("Пожалуйста, выберите вариант, нажав на кнопку ниже.")
        return
    session["answers"].append(answer[0].upper())
    session["step"] += 1
    if session["step"] < len(TEST_QUESTIONS):
        await send_question(message)
    else:
        await show_results(message)

def save_result_to_csv(session, correct, total):
    filename = "results.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, "a", encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Имя", "UserID", "Верно", "Всего", "Ответы"])
        writer.writerow([
            session.get("name", "—"),
            session.get("user_id", "—"),
            correct,
            total,
            " ".join(session.get("answers", []))
        ])

async def show_results(message):
    session = user_sessions[message.from_user.id]
    correct = 0
    total = len(TEST_QUESTIONS)
    mistakes = []

    for i, (user_ans, q) in enumerate(zip(session["answers"], TEST_QUESTIONS)):
        if user_ans == q["correct"]:
            correct += 1
        else:
            mistakes.append(f"{i+1}. {q['question']}")

    percentage = correct / total

    name = session.get("name", "Неизвестно")
    save_result_to_csv(session, correct, total)

    if percentage < 0.5:
        await message.answer(
            f"К сожалению, вы не набрали минимум 50% правильных ответов.\n"
            f"Ваш результат: {correct} из {total}.\n"
            f"Пожалуйста, пройдите тест заново.",
            reply_markup=ReplyKeyboardRemove()
        )
        # Сбросим сессию, чтобы пользователь мог начать сначала
        user_sessions.pop(message.from_user.id, None)
    else:
        if mistakes:
            mistake_text = "\n".join(mistakes)
            await message.answer(
                f"Вы успешно прошли тест!\n\n"
                f"Вы допустили ошибки в следующих вопросах:\n{mistake_text}\n\n"
                f"Результат: {correct} из {total}.",
                reply_markup=ReplyKeyboardRemove()
            )
            # Удаляем сессию, тест окончен
            user_sessions.pop(message.from_user.id, None)
        else:
            await message.answer(
                f"Поздравляем! Вы ответили правильно на все вопросы.\n"
                f"Обращайтесь к вашему менеджеру: @Nata_Nikolavna",
                reply_markup=ReplyKeyboardRemove()
            )
            user_sessions.pop(message.from_user.id, None)

@dp.message_handler(commands=["results"])
async def cmd_results(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return
    filename = "results.csv"
    if os.path.exists(filename):
        await message.answer_document(InputFile(filename))
    else:
        await message.answer("Файл с результатами еще не создан.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
