# sheets_api.py
# Безопасное чтение таблиц (устойчиво к дубликатам/пустым заголовкам),
# поиск телефонов и расписаний без привязки к названиям столбцов,
# FoodLog (с датой) и новый лист Feedback (сохранение удовлетворённости).

import re
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import SERVICE_ACCOUNT_FILE, SHEET_ID


# =========================
# БАЗОВОЕ ПОДКЛЮЧЕНИЕ GSheets
# =========================

def get_gsheets():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client


def get_users_worksheet(sheet_name="Users"):
    gc = get_gsheets()
    sh = gc.open_by_key(SHEET_ID)
    return sh.worksheet(sheet_name)


# =========================
# УТИЛИТЫ
# =========================

def _only_digits(s):
    return re.sub(r"\D+", "", str(s or ""))


def _norm(s):
    return (s or "").strip()


def _lower(s):
    return (s or "").strip().lower()


def _get_all_records_no_fail(ws):
    """
    Возвращает список dict по листу, не используя expected_headers.
    Дубликаты/пустые заголовки делаем уникальными ТОЛЬКО локально.
    """
    matrix = ws.get_all_values()  # список списков
    if not matrix:
        return []

    headers_raw = matrix[0]
    seen = {}
    headers = []
    for i, h in enumerate(headers_raw, start=1):
        base = (h or "").strip()
        if not base:
            base = f"__col{i}"  # локальный псевдозаголовок
        c = seen.get(base, 0)
        headers.append(base if c == 0 else f"{base}__{c+1}")
        seen[base] = c + 1

    out = []
    for row in matrix[1:]:
        rec = {}
        for j, key in enumerate(headers):
            rec[key] = row[j] if j < len(row) else ""
        out.append(rec)
    return out


# =========================
# НОРМАЛИЗАЦИЯ КЛЮЧЕЙ (пригодится для профиля)
# =========================

CANONICAL_MAP = {
    "телефон": "Телефон",
    "phone": "Телефон",
    "имя": "Имя",
    "стадия": "Стадия",
    "резултат": "Результат",
    "результат": "Результат",
    "сахар на тощак": "Сахар на тощак",
    "возраст": "Возраст",
    "препарат 1": "Препарат 1",
    "препарат1": "Препарат 1",
    "препарат 2": "Препарат 2",
    "препарат2": "Препарат 2",
    "когда1": "Когда (препарат 1)",
    "когда 1": "Когда (препарат 1)",
    "когда (препарат 1)": "Когда (препарат 1)",
    "когда2": "Когда (препарат 2)",
    "когда 2": "Когда (препарат 2)",
    "когда (препарат 2)": "Когда (препарат 2)",
    "кол-во / день (препарат 1)": "Кол-во / день (препарат 1)",
    "кол-во / день (препарат 2)": "Кол-во / день (препарат 2)",
}

def canonical_key(raw_key: str) -> str:
    k = _lower(raw_key)
    return CANONICAL_MAP.get(k, raw_key.strip())


def normalize_record_keys(record: dict) -> dict:
    return {canonical_key(k): v for k, v in record.items()}


# =========================
# FOODLOG
# =========================

def user_sent_food_photo(phone):
    try:
        ws = get_users_worksheet("FoodLog")
        recs = _get_all_records_no_fail(ws)
        pn = _only_digits(phone)
        for r in recs:
            tel = r.get("Телефон")
            if _only_digits(tel) == pn:
                return True
        return False
    except Exception as e:
        print("== Ошибка при проверке FoodLog в Google Sheets ==", e)
        return False


def save_food_decision(phone, food_result, score, comment, decision):
    """
    A: Телефон
    B: Результат
    C: Оценка (баллы)
    D: Описание
    E: Будет есть
    F: Дата
    """
    try:
        ws = get_users_worksheet("FoodLog")
        headers = ws.row_values(1)
        target = ["Телефон", "Результат", "Оценка (баллы)", "Описание", "Будет есть", "Дата"]
        if headers[:len(target)] != target:
            ws.update("A1:F1", [target])

        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [str(phone), food_result, score, comment, decision, date_str]
        ws.append_row(row, value_input_option="USER_ENTERED")
        print("== FoodLog: запись добавлена ==")
    except Exception as e:
        print("== Ошибка записи FoodLog в Google Sheets ==", e)


# =========================
# FEEDBACK (новый лист)
# =========================

def save_feedback(phone: str, kind: str, ok: bool, details: str = ""):
    """
    Сохраняем оценку полезности ответа.
    Лист: Feedback
    A: Телефон
    B: Тип (doctor|food)
    C: Устроило (Да/Нет)
    D: Детали (коротко)
    E: Дата
    """
    try:
        ws = get_users_worksheet("Feedback")
        headers = ws.row_values(1)
        target = ["Телефон", "Тип", "Устроило", "Детали", "Дата"]
        if headers[:len(target)] != target:
            ws.update("A1:E1", [target])

        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [str(phone), kind, "Да" if ok else "Нет", details or "", date_str]
        ws.append_row(row, value_input_option="USER_ENTERED")
        print("== Feedback: запись добавлена ==")
    except Exception as e:
        print("== Ошибка записи Feedback в Google Sheets ==", e)


# =========================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# =========================

def get_personal_profile(phone, sheet_name="Sample"):
    """
    Возвращает dict строки пользователя (по любому полю с телефоном),
    fallback: если номер встретился в любом значении строки.
    """
    try:
        ws = get_users_worksheet(sheet_name)
        recs = _get_all_records_no_fail(ws)
        pn = _only_digits(phone)
        for r in recs:
            r_norm = normalize_record_keys(r)
            for key, val in r_norm.items():
                if "телефон" in _lower(key) or "phone" in _lower(key):
                    if _only_digits(val) == pn:
                        return r_norm
            if pn and pn in [_only_digits(v) for v in r.values()]:
                return r_norm
        return None
    except Exception as e:
        print("Ошибка get_personal_profile:", e)
        return None


def format_profile(profile_dict):
    if not profile_dict:
        return None
    rec = normalize_record_keys(profile_dict)

    def _med_line(n):
        name = _norm(rec.get(f"Препарат {n}"))
        kvo  = _norm(rec.get(f"Кол-во / день (препарат {n})"))
        when = _norm(rec.get(f"Когда (препарат {n})"))
        if not name:
            return ""
        out = name
        if kvo:
            out += f" — {kvo} р/д"
        if when:
            out += f", {when}"
        return out

    med1 = _med_line(1)
    med2 = _med_line(2)

    items = [
        ("Телефон", rec.get("Телефон", "")),
        ("Имя", rec.get("Имя", "")),
        ("Стадия", rec.get("Стадия", "")),
        ("Результат", rec.get("Результат", "")),
        ("Сахар на тощак", rec.get("Сахар на тощак", "")),
        ("Возраст", rec.get("Возраст", "")),
        ("Препарат 1", med1 if med1 else rec.get("Препарат 1", "")),
        ("Препарат 2", med2 if med2 else rec.get("Препарат 2", "")),
        ("Сопутствующие заболевания", rec.get("Сопутствующие заболевания", "")),
        ("Hba1c", rec.get("Hba1c", "")),
        ("Вода (мл/ день)", rec.get("Вода (мл/ день)", "")),
        ("Пищевые привычки", rec.get("Пищевые привычки", "")),
        ("Ранние сложности", rec.get("Ранние сложности", rec.get("Рание сложности", ""))),
        ("Физ. активность", rec.get("Физ. активность", "")),
    ]
    lines = [f"{label}: {val}" for label, val in items if _norm(val)]
    return "\n".join(lines) if lines else None


def build_ai_profile_text(phone, sheet_name="Sample"):
    rec = get_personal_profile(phone, sheet_name=sheet_name)
    return format_profile(rec)


# =========================
# МЕДИКАМЕНТЫ/РАСПИСАНИЕ
# =========================

def get_user_meds_schedule(phone, sheet_name="Sample"):
    """
    Ищем строку по телефону без жёсткой привязки к названиям столбцов.
    Пытаемся угадать «Препарат N»/«Когда (препарат N)» по подстрокам.
    (Оставлено для обратной совместимости, но для воркера лучше
    использовать get_all_meds_schedules())
    """
    try:
        ws = get_users_worksheet(sheet_name)
        recs = _get_all_records_no_fail(ws)
        pn = _only_digits(phone)

        def pick(colnames, row):
            for k in row:
                lk = _lower(k)
                if any(s in lk for s in colnames):
                    v = _norm(row.get(k))
                    if v:
                        return v
            return ""

        for r in recs:
            r_norm = normalize_record_keys(r)
            row_digits = [_only_digits(v) for v in r_norm.values()]
            if pn and pn in row_digits:
                med1 = pick(["препарат 1", "prep 1", "drug 1", "лекарств 1"], r_norm)
                when1 = pick(["когда (препарат 1)", "когда1", "when 1"], r_norm)
                med2 = pick(["препарат 2", "prep 2", "drug 2", "лекарств 2"], r_norm)
                when2 = pick(["когда (препарат 2)", "когда2", "when 2"], r_norm)
                return {
                    "med1_name": med1,
                    "med1_time": when1,
                    "med2_name": med2,
                    "med2_time": when2,
                }
        return {"med1_name": "", "med1_time": "", "med2_name": "", "med2_time": ""}
    except Exception as e:
        print("Ошибка get_user_meds_schedule:", e)
        return {"med1_name": "", "med1_time": "", "med2_name": "", "med2_time": ""}


def get_all_meds_schedules(sheet_name="Sample"):
    """
    ПРОЧИТЫВАЕТ ЛИСТ ОДИН РАЗ и возвращает словарь:
      { "<digits_phone>": {"med1_name":..., "med1_time":..., "med2_name":..., "med2_time":...}, ... }
    """
    try:
        ws = get_users_worksheet(sheet_name)
        recs = _get_all_records_no_fail(ws)

        def pick(colnames, row):
            for k in row:
                lk = _lower(k)
                if any(s in lk for s in colnames):
                    v = _norm(row.get(k))
                    if v:
                        return v
            return ""

        out = {}
        for r in recs:
            r_norm = normalize_record_keys(r)
            # попробуем найти телефон в любом поле строки
            row_digits_map = {k: _only_digits(v) for k, v in r_norm.items()}
            phones_in_row = [v for v in row_digits_map.values() if v and len(v) >= 9]
            if not phones_in_row:
                continue
            # берём первый подходящий
            pn = phones_in_row[0]

            med1 = pick(["препарат 1", "prep 1", "drug 1", "лекарств 1"], r_norm)
            when1 = pick(["когда (препарат 1)", "когда1", "when 1"], r_norm)
            med2 = pick(["препарат 2", "prep 2", "drug 2", "лекарств 2"], r_norm)
            when2 = pick(["когда (препарат 2)", "когда2", "when 2"], r_norm)

            out[pn] = {
                "med1_name": med1,
                "med1_time": when1,
                "med2_name": med2,
                "med2_time": when2,
            }
        return out
    except Exception as e:
        print("Ошибка get_all_meds_schedules:", e)
        return {}


# =========================
# ТЕЛЕФОНЫ ИЗ SAMPLE
# =========================

def get_all_user_phones_from_sample(sheet_name="Sample"):
    """
    Возвращает все телефоны (≥9 цифр), найденные в листе, БЕЗ зависимости от имён столбцов.
    """
    try:
        ws = get_users_worksheet(sheet_name)
        values = ws.get_all_values()
        if not values:
            return []

        phones = set()
        for row in values[1:]:  # пропускаем заголовки
            for cell in row:
                pn = _only_digits(cell)
                if len(pn) >= 9:
                    phones.add(pn)

        return sorted(phones)
    except Exception as e:
        print("Ошибка get_all_user_phones_from_sample:", e)
        return []


# =========================
# ДНЕВНЫЕ ЗАДАНИЯ
# =========================

def get_daily_task_by_day(day_num, sheet_name="DailyTasks"):
    try:
        ws = get_users_worksheet(sheet_name)
        recs = _get_all_records_no_fail(ws)
        if not recs:
            return {"Task": "Сегодня нет задания", "Description": ""}
        index = (day_num - 1) % len(recs)
        return recs[index]
    except Exception as e:
        print("Ошибка get_daily_task_by_day:", e)
        return {"Task": "Ошибка загрузки задания", "Description": ""}
