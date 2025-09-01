# doctor_ai_module.py
# Личный советник: профиль используется ТОЛЬКО в prompt, в ответе пользователю не показывается.

import requests
from config import OPENAI_API_KEY
from sheets_api import get_personal_profile


# Если когда-нибудь захотите снова показывать профиль пользователю,
# поменяйте на True и добавьте вывод (смотрите комментарии ниже).
SHOW_PROFILE_TO_USER = False


def trim(text: str, maxlen: int = 750) -> str:
    """Обрезает текст до maxlen символов, добавляя '…' если обрезано."""
    text = text or ""
    return text if len(text) <= maxlen else text[: maxlen - 1] + "…"


def _to_compact_profile_for_prompt(profile: dict | None) -> str:
    """Компактная строка профиля ТОЛЬКО для prompt (не для показа пользователю)."""
    if not profile:
        return ""
    # приводим значения к str, чтобы не упасть на числах
    parts = [f"{k}: {v}" for k, v in profile.items() if v is not None and str(v).strip() != ""]
    return "; ".join(parts)


def ask_doctor_ai(question: str, phone: str) -> str:
    # Получаем профиль пользователя из листа Sample
    user_profile = get_personal_profile(phone)

    # Профиль добавляем только в системную подсказку
    profile_for_prompt = _to_compact_profile_for_prompt(user_profile)
    patient_info = (
        (
            "\nВот медицинская и поведенческая информация о пациенте:\n"
            f"{profile_for_prompt}\n"
            "Используй эти данные для точности и персонализации совета."
        )
        if profile_for_prompt
        else ""
    )

    system_prompt = (
        "Ты опытный эндокринолог. Отвечай просто, максимально коротко, понятно и с заботой о человеке. "
        "Дай совет по диабету, питанию, образу жизни или симптомам. "
        "Если вопрос не по профилю — вежливо попроси обратиться к врачу лично. "
        "Не ставь диагноз, не назначай лекарства дистанционно!"
        + patient_info
    )

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "max_tokens": 500,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=40)
        if resp.status_code == 200:
            ai_answer = resp.json()["choices"][0]["message"]["content"].strip()
            answer = trim(ai_answer, 750)

            # НЕ показываем профиль пользователю
            if SHOW_PROFILE_TO_USER and user_profile:
                # если включите True — тут можно приклеить отформатированный профиль перед ответом
                # from sheets_api import format_profile
                # prof_block = format_profile(user_profile)
                # if prof_block:
                #     return f"{prof_block}\n\n{answer}"
                pass

            return answer

        print("Ошибка врача:", resp.text)
        return "❗Извините, не удалось получить ответ от врача. Попробуйте позже."
    except Exception as e:
        print("Ошибка врача:", e)
        return "❗Ошибка обработки. Попробуйте ещё раз."
