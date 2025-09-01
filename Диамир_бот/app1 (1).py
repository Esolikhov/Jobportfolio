# app1.py
import sys
import json
import time
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

from config import VERIFY_TOKEN, START_IMAGE_URLS
from whatsapp_api import (
    send_whatsapp_message,
    send_whatsapp_quick_reply,
    send_whatsapp_image,
)
from sheets_api import user_sent_food_photo

app = FastAPI()

# Память по пользователям (простейший стейт в памяти процесса)
user_states: dict[str, dict] = {}

MAIN_MENU = [
    {"id": "cmd_vrach", "title": "Личный советник"},
    {"id": "cmd_photo", "title": "Дневник питания"},
]

def show_menu(phone: str):
    send_whatsapp_quick_reply(phone, "Главное меню. Выберите действие:", MAIN_MENU)

def send_onboarding_images(phone: str):
    """Шлём 3 изображения без подписей, с паузами для гарантии порядка доставки."""
    for url in START_IMAGE_URLS:
        try:
            send_whatsapp_image(phone, url)
        except Exception:
            pass
        time.sleep(0.8)

@app.get("/", response_class=PlainTextResponse)
async def root_ok():
    return "ok"

@app.get("/health", response_class=PlainTextResponse)
async def health_ok():
    return "ok"

@app.get("/version")
async def version():
    return {"status": "ok", "service": "whatsapp-bot", "component": "app1"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Поддерживает и Meta-верификацию, и обычные health-пинги (не возвращаем 403).
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN and challenge is not None:
        try:
            return PlainTextResponse(str(int(challenge)))
        except Exception:
            return PlainTextResponse(str(challenge))

    return PlainTextResponse("ok")

@app.post("/webhook")
async def webhook_handler(request: Request):
    raw_body = await request.body()
    try:
        data = json.loads(raw_body)
        print("===> RAW MESSAGE:", file=sys.stderr)
        print(json.dumps(data, ensure_ascii=False, indent=2), file=sys.stderr)
    except Exception as e:
        print("Ошибка парсинга RAW:", e, file=sys.stderr)
        return JSONResponse({"status": "error", "detail": "Failed to parse"}, status_code=200)

    # Универсальный извлекатель первого сообщения (англ/рус)
    def get_first_message(data):
        # стандартный путь
        try:
            entry = data["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            messages = value.get("messages", [])
            statuses = value.get("statuses", [])
            if messages:
                return messages[0], value, False  # not a status
            if statuses:
                return None, value, True          # status webhook
        except Exception:
            pass
        # альтернативные ключи (рус)
        try:
            entry = data["entry"][0]
            changes = entry.get("изменения", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("сообщения", [])
            statuses = value.get("статусы", [])
            if messages:
                return messages[0], value, False
            if statuses:
                return None, value, True
        except Exception:
            pass
        return None, None, False

    message, value, is_status = get_first_message(data)
    if is_status:
        # тихо подтверждаем статусы (delivered/read/…)
        return JSONResponse({"status": "ok"}, status_code=200)

    if not message:
        print("НЕОБРАБОТАННОЕ СООБЩЕНИЕ (нет messages)", file=sys.stderr)
        return JSONResponse({"status": "ok"}, status_code=200)

    try:
        phone = message.get("from")
        msg_type = message.get("type", "")

        # === КНОПКИ ===
        if msg_type in ["interactive", "интерактивный"]:
            btn = message.get("interactive") or message.get("интерактивный") or {}
            btn_id = (btn.get("button_reply") or {}).get("id", "")

            if btn_id.startswith("cmd_next_") or btn_id.startswith("cmd_back_"):
                show_menu(phone)
                return {"status": "ok"}

            if btn_id == "cmd_close":
                send_whatsapp_message(phone, "Меню закрыто. Если потребуется — напишите /start.")
                return {"status": "ok"}

            if btn_id == "cmd_vrach":
                state = user_states.get(phone, {})
                state.update({"doctor_mode": True})
                user_states[phone] = state
                send_whatsapp_message(phone, "Онлайн-поддержка Диамир.")
                send_whatsapp_message(phone, "Вы подключены к личному советнику. Напишите свой вопрос.")
                return {"status": "ok"}

            if btn_id == "cmd_photo":
                state = user_states.get(phone, {})
                state.update({"photo_mode": True, "await_image": True})
                user_states[phone] = state
                send_whatsapp_message(phone, "Онлайн-поддержка Диамир.")
                send_whatsapp_message(phone, "Отправьте фото блюда (или ссылку) для оценки.")
                return {"status": "ok"}

            from app4 import process_other_message
            return await process_other_message(message, value, user_states, show_menu)

        # === ТЕКСТ ===
        text = (message.get("text", {}) or {}).get("body", "")
        text_norm = (text or "").strip().lower()

        # Первый произвольный текст => онбординг (если ещё не присылал еду)
        if text_norm:
            st = user_states.get(phone, {})
            first_time = (not st.get("onboarded", False)) and (not user_sent_food_photo(phone))
            if first_time:
                st["onboarded"] = True
                user_states[phone] = st
                send_onboarding_images(phone)
                show_menu(phone)
                return {"status": "ok"}

        # Команды
        if text_norm in ["/start", "start", "меню", "menu", "назад", "инструкция"]:
            st = user_states.get(phone, {})
            if text_norm == "инструкция" and not st.get("onboarded", False) and not user_sent_food_photo(phone):
                st["onboarded"] = True
                user_states[phone] = st
                send_onboarding_images(phone)
            show_menu(phone)
            return {"status": "ok"}

        # Любой другой текст без активного режима — меню
        if text_norm and not user_states.get(phone):
            show_menu(phone)
            return {"status": "ok"}

        from app4 import process_other_message
        return await process_other_message(message, value, user_states, show_menu)

    except Exception as e:
        print("== Ошибка обработки сообщения ==", e, file=sys.stderr)
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=200)
