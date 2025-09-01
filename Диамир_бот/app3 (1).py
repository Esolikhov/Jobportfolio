import json
from sheets_api import user_exists_in_sheets, save_food_decision, user_sent_food_photo
from photo_ai_module import analyze_food_photo
from telegram_api import send_to_telegram
from whatsapp_api import send_whatsapp_message, send_whatsapp_quick_reply, send_whatsapp_image

MAIN_MENU = [
    {"id": "cmd_vrach", "title": "Личный советник"},
    {"id": "cmd_photo", "title": "Дневник питания"},
]

def show_menu(phone, *args, **kwargs):
    send_whatsapp_quick_reply(phone, "Главное меню. Выберите действие:", MAIN_MENU)

async def route_message_app3(message, phone, user_states, show_menu):
    print(f"\n===> RAW MESSAGE для {phone}:\n{json.dumps(message, ensure_ascii=False, indent=2)}")
    state = user_states.get(phone, {})
    print("Текущее состояние:", state)

    # 1) покупка (если у тебя используется)
    if state.get("buy_mode"):
        pkg = message.get("text", {}).get("body", "").strip()
        if pkg.lower() in ["стартовый", "премиум", "популярный"]:
            send_to_telegram(f"Пользователь {phone} выбрал пакет: {pkg}", phone)
            send_whatsapp_message(phone, f"Спасибо! Вы выбрали пакет: {pkg}. С вами свяжется менеджер.")
            user_states.pop(phone, None)
            show_menu(phone)
            return {"status": "ok"}
        else:
            send_whatsapp_message(phone, "Пожалуйста, напишите одно из: стартовый, премиум, популярный.")
            return {"status": "ok"}

    # 2) оценка еды (если сюда попадёт)
    if state.get("photo_mode"):
        media_id = None
        if "image" in message and "id" in message["image"]:
            media_id = message["image"]["id"]
        elif "photo" in message and "id" in message["photo"]:
            media_id = message["photo"]["id"]
        elif "document" in message and "id" in message["document"]:
            media_id = message["document"]["id"]
        elif message.get("text", {}):
            url = message["text"]["body"].strip()
            if url.startswith("http"):
                result, score, comment = analyze_food_photo(url, phone)
                if "Ошибка" not in result:
                    send_whatsapp_message(phone, f"{result}\n\nОценка: {score}/5\nКомментарий: {comment}")
                    user_states[phone] = {"food_result": (result, score, comment)}
                    send_whatsapp_message(phone, "Вы будете это есть? Ответьте 'Да' или 'Нет'.")
                else:
                    send_whatsapp_message(phone, result)
                return {"status": "ok"}
            else:
                send_whatsapp_message(phone, "Пожалуйста, отправьте изображение блюда или ссылку на фото.")
                return {"status": "ok"}

        if media_id:
            result, score, comment = analyze_food_photo(media_id, phone)
            if "Ошибка" not in result:
                send_whatsapp_message(phone, f"{result}\n\nОценка: {score}/5\nКомментарий: {comment}")
                user_states[phone] = {"food_result": (result, score, comment)}
                send_whatsapp_message(phone, "Вы будете это есть? Ответьте 'Да' или 'Нет'.")
            else:
                send_whatsapp_message(phone, result)
            return {"status": "ok"}
        else:
            send_whatsapp_message(phone, "Пожалуйста, отправьте изображение блюда или ссылку на фото.")
            return {"status": "ok"}

    # 3) подтверждение Да/Нет
    if state.get("food_result"):
        text = message.get("text", {}).get("body", "").strip().lower()
        if text in ["да", "yes"]:
            result, score, comment = state["food_result"]
            save_food_decision(phone, result, score, comment, "Да")
            send_whatsapp_message(phone, "Ваш ответ сохранён! Спасибо.")
            user_states.pop(phone, None)
            show_menu(phone)
            return {"status": "ok"}
        elif text in ["нет", "no"]:
            result, score, comment = state["food_result"]
            save_food_decision(phone, result, score, comment, "Нет")
            send_whatsapp_message(phone, "Ваш ответ сохранён! Спасибо.")
            user_states.pop(phone, None)
            show_menu(phone)
            return {"status": "ok"}
        else:
            send_whatsapp_message(phone, "Пожалуйста, ответьте 'Да' или 'Нет'.")
            return {"status": "ok"}

    # 4) если ничего не подошло — показать меню
    show_menu(phone)
    return {"status": "ok"}
