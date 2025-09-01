from whatsapp_api import (
    send_whatsapp_message,
    send_whatsapp_quick_reply,
    download_whatsapp_media,
)
from telegram_api import send_to_telegram
from photo_ai_module import analyze_food_photo
from doctor_ai_module import ask_doctor_ai
from sheets_api import save_food_decision, save_feedback

def _clear_mode(user_states, phone, *keys_to_clear):
    st = user_states.get(phone, {})
    for k in keys_to_clear:
        st.pop(k, None)
    user_states[phone] = st

def _unpack_food_result(result):
    """
    Нормализуем ответ analyze_food_photo к (text, score, comment, recognized),
    принимая и 3-элементные варианты.
    """
    text, score, comment, recognized = None, None, None, False
    if isinstance(result, tuple):
        if len(result) >= 4:
            text, score, comment, recognized = result[0], result[1], result[2], result[3]
        elif len(result) == 3:
            text, score, comment = result
            recognized = "Не удалось распознать" not in (text or "")
        elif len(result) == 2:
            text, score = result
        elif len(result) == 1:
            text = result[0]
    else:
        text = str(result)
    # дефолты
    if score is None:
        score = 2
    if not comment:
        comment = "Комментарий отсутствует"
    return text, score, comment, bool(recognized)

async def process_other_message(message, value, user_states, show_menu):
    phone = message.get("from")
    msg_type = message.get("type", "")

    # ==== BUTTONS ====
    if msg_type in ["interactive", "интерактивный"]:
        btn = message.get("interactive") or message.get("интерактивный")
        btn_id = (btn.get("button_reply") or {}).get("id", "")

        # retry/exit после "не распознано"
        if btn_id == "food_retry":
            st = user_states.get(phone, {})
            st.pop("awaiting_retry", None)
            st["photo_mode"] = True
            user_states[phone] = st
            send_whatsapp_message(phone, "Пришлите новое фото блюда или ссылку на фото.")
            return {"status": "ok"}

        if btn_id == "food_exit":
            _clear_mode(user_states, phone,
                        "photo_mode", "await_image", "awaiting_retry",
                        "last_food_result", "last_food_score", "last_food_comment")
            send_whatsapp_message(phone, "Режим дневник питания закрыт.")
            show_menu(phone)
            return {"status": "ok"}

        # == doctor feedback ==
        if btn_id in ["doctor_feedback_yes", "doctor_feedback_no"]:
            last = user_states.get(phone, {})
            ok = (btn_id == "doctor_feedback_yes")
            details = f"Q: {last.get('last_doctor_question','')} | A: {last.get('last_doctor_answer','')}"
            save_feedback(phone, "doctor", ok, details)

            if ok:
                send_whatsapp_message(phone, "Спасибо за вашу обратную связь!")
            else:
                send_whatsapp_message(phone, "Ваш вопрос передан в поддержку! Ожидайте ответа.")
                support_msg = (
                    f"Недоволен ответом советника.\n"
                    f"Телефон: {phone}\n"
                    f"Вопрос: {last.get('last_doctor_question', '')}\n"
                    f"Ответ: {last.get('last_doctor_answer', '')}"
                )
                send_to_telegram(support_msg, phone)

            _clear_mode(user_states, phone, "doctor_mode", "last_doctor_question", "last_doctor_answer")
            show_menu(phone)
            return {"status": "ok"}

        # == food decision ==
        if btn_id in ["food_yes", "food_no"]:
            decision = "Да" if btn_id == "food_yes" else "Нет"
            last = user_states.get(phone, {})
            save_food_decision(
                phone,
                last.get("last_food_result", ""),
                last.get("last_food_score", 2),
                last.get("last_food_comment", "Комментарий отсутствует"),
                decision
            )
            feedback_buttons = [
                {"id": "food_feedback_yes", "title": "Да"},
                {"id": "food_feedback_no", "title": "Нет"},
            ]
            send_whatsapp_quick_reply(phone, "Вас устраивает ответ?", feedback_buttons)
            st = user_states.get(phone, {})
            st["awaiting_feedback"] = True
            user_states[phone] = st
            return {"status": "ok"}

        # == food feedback ==
        if btn_id in ["food_feedback_yes", "food_feedback_no"]:
            ok = (btn_id == "food_feedback_yes")
            last = user_states.get(phone, {})
            details = f"Score: {last.get('last_food_score',2)} | Comment: {last.get('last_food_comment','')}"
            save_feedback(phone, "food", ok, details)

            if ok:
                send_whatsapp_message(phone, "Спасибо за обратную связь!")
                _clear_mode(user_states, phone,
                            "photo_mode", "await_image", "awaiting_feedback",
                            "last_food_result", "last_food_score", "last_food_comment")
                show_menu(phone)
            else:
                send_whatsapp_message(phone, "Ваш вопрос направлен в поддержку!")
                send_to_telegram(
                    f"Недоволен анализом питания.\nТелефон: {phone}\n"
                    f"Результат:\n{last.get('last_food_result', '')}\n"
                    f"Оценка: {last.get('last_food_score', 2)}\n"
                    f"Комментарий: {last.get('last_food_comment', 'Комментарий отсутствует')}",
                    phone
                )
                _clear_mode(user_states, phone,
                            "photo_mode", "await_image", "awaiting_feedback",
                            "last_food_result", "last_food_score", "last_food_comment")
                show_menu(phone)
            return {"status": "ok"}

    # ==== ЛИЧНЫЙ СОВЕТНИК ====
    state = user_states.get(phone, {})
    if state.get("doctor_mode"):
        text = (message.get("text", {}) or {}).get("body", "") or ""
        text = text.strip()
        if text.lower() == "закрыть":
            _clear_mode(user_states, phone, "doctor_mode", "last_doctor_question", "last_doctor_answer")
            send_whatsapp_message(phone, "Чат с личным советником закрыт. Возвращаем вас в меню.")
            show_menu(phone)
            return {"status": "ok"}

        answer = ask_doctor_ai(text, phone)
        st = user_states.get(phone, {})
        st.update({
            "doctor_mode": True,
            "last_doctor_question": text,
            "last_doctor_answer": answer
        })
        user_states[phone] = st
        send_whatsapp_message(phone, f"Ответ советника: {answer}\n\nНапишите 'закрыть' чтобы завершить.")
        doctor_feedback_buttons = [
            {"id": "doctor_feedback_yes", "title": "Да"},
            {"id": "doctor_feedback_no", "title": "Нет"},
        ]
        send_whatsapp_quick_reply(phone, "Вас устраивает ответ советника?", doctor_feedback_buttons)
        return {"status": "ok"}

    # ==== ДНЕВНИК ПИТАНИЯ ====
    if state.get("photo_mode"):
        awaiting_retry = state.get("awaiting_retry", False)

        img_key = "image" if "image" in message else ("изображение" if "изображение" in message else None)
        if message.get("type") in ["image", "изображение"] and img_key:
            image_id = message[img_key].get("id")
            if not image_id:
                send_whatsapp_message(phone, "Не удалось получить изображение.")
                return {"status": "ok"}

            image_bytes = download_whatsapp_media(image_id)
            if not image_bytes:
                send_whatsapp_message(phone, "Ошибка при скачивании изображения.")
                return {"status": "ok"}

            result = analyze_food_photo(image_bytes, phone)
            food_text, score, comment, recognized = _unpack_food_result(result)

            if not recognized:
                if not awaiting_retry:
                    retry_buttons = [
                        {"id": "food_retry", "title": "Отправить снова"},
                        {"id": "food_exit",  "title": "Выход"},
                    ]
                    send_whatsapp_quick_reply(phone, "Не удалось распознать блюдо. Попробуете ещё раз?", retry_buttons)
                    st = user_states.get(phone, {})
                    st.update({"photo_mode": True, "awaiting_retry": True})
                    user_states[phone] = st
                return {"status": "ok"}

            st = user_states.get(phone, {})
            st.update({
                "photo_mode": True,
                "awaiting_retry": False,
                "last_food_result": food_text,
                "last_food_score": score,
                "last_food_comment": comment,
            })
            user_states[phone] = st

            msg = f"{food_text}\n\nОценка: {st['last_food_score']}/5\nКомментарий: {st['last_food_comment']}"
            send_whatsapp_message(phone, msg)
            food_decision_buttons = [
                {"id": "food_yes", "title": "Да"},
                {"id": "food_no", "title": "Нет"}
            ]
            send_whatsapp_quick_reply(phone, "Вы будете это есть?", food_decision_buttons)
            return {"status": "ok"}

        # ссылка
        text = (message.get("text", {}) or {}).get("body", "") or ""
        text = text.strip()
        if text.lower() == "закрыть":
            _clear_mode(user_states, phone,
                        "photo_mode", "await_image", "awaiting_retry",
                        "awaiting_feedback", "last_food_result", "last_food_score", "last_food_comment")
            send_whatsapp_message(phone, "Режим дневника питания завершён. Возвращаем вас в меню.")
            show_menu(phone)
            return {"status": "ok"}

        if text and (text.startswith("http://") or text.startswith("https://")):
            result = analyze_food_photo(text, phone)
            food_text, score, comment, recognized = _unpack_food_result(result)

            if not recognized:
                if not awaiting_retry:
                    retry_buttons = [
                        {"id": "food_retry", "title": "Отправить снова"},
                        {"id": "food_exit",  "title": "Выход"},
                    ]
                    send_whatsapp_quick_reply(phone, "Не удалось распознать блюдо. Попробуете ещё раз?", retry_buttons)
                    st = user_states.get(phone, {})
                    st.update({"photo_mode": True, "awaiting_retry": True})
                    user_states[phone] = st
                return {"status": "ok"}

            st = user_states.get(phone, {})
            st.update({
                "photo_mode": True,
                "awaiting_retry": False,
                "last_food_result": food_text,
                "last_food_score": score,
                "last_food_comment": comment,
            })
            user_states[phone] = st

            msg = f"{food_text}\n\nОценка: {st['last_food_score']}/5\nКомментарий: {st['last_food_comment']}"
            send_whatsapp_message(phone, msg)
            food_decision_buttons = [
                {"id": "food_yes", "title": "Да"},
                {"id": "food_no", "title": "Нет"}
            ]
            send_whatsapp_quick_reply(phone, "Вы будете это есть?", food_decision_buttons)
            return {"status": "ok"}

        send_whatsapp_message(phone, "Пожалуйста, отправьте изображение блюда или ссылку на фото.")
        return {"status": "ok"}

    # ==== Меню по ключевым словам ====
    text = (message.get("text", {}) or {}).get("body", "") or ""
    if text.strip().lower() in ["/start", "start", "меню", "menu", "назад", "инструкция"]:
        show_menu(phone)
        return {"status": "ok"}

    show_menu(phone)
    return {"status": "ok"}
