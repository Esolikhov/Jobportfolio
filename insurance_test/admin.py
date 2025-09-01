import sqlite3

# Укажите здесь свой реальный Telegram ID!
ADMIN_IDS = [623765402]

DB_PATH = "insurancebot.db"

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_all_interviews():
    try:
        with open("interviews.csv", encoding="utf-8") as f:
            data = f.readlines()
        if not data:
            return "Нет заявок на собеседование."
        lines = ["Список заявок на собеседование:"]
        for i, line in enumerate(data, 1):
            user_id, name, phone = line.strip().split(",", 2)
            lines.append(f"{i}) {name}, {phone} (user_id: {user_id})")
        return "\n".join(lines)
    except Exception as e:
        return "Ошибка чтения файла заявок: " + str(e)

def get_interviews_file():
    try:
        return open("interviews.csv", "rb")
    except Exception:
        return None

def get_active_users():
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT telegram_id, name, registration_date, current_lesson FROM users")
        users = cur.fetchall()
        con.close()
        if not users:
            return "Нет зарегистрированных пользователей."
        lines = ["Активные пользователи:"]
        for i, (telegram_id, name, reg_date, curr_lesson) in enumerate(users, 1):
            lines.append(f"{i}) {name} (ID: {telegram_id}), Зарегистрирован: {reg_date}, Прогресс: урок {curr_lesson}")
        return "\n".join(lines)
    except Exception as e:
        return "Ошибка чтения списка пользователей: " + str(e)

def get_inactive_users():
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT telegram_id, name, registration_date FROM users WHERE current_lesson=1")
        users = cur.fetchall()
        con.close()
        if not users:
            return "Нет неактивных пользователей (все начали обучение)."
        lines = ["Неактивные пользователи (ещё не начали обучение):"]
        for i, (telegram_id, name, reg_date) in enumerate(users, 1):
            lines.append(f"{i}) {name} (ID: {telegram_id}), Зарегистрирован: {reg_date}")
        return "\n".join(lines)
    except Exception as e:
        return "Ошибка чтения неактивных пользователей: " + str(e)
