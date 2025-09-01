from whatsapp_api import send_whatsapp_quick_reply, send_whatsapp_message

def show_menu(phone):
    buttons = [
        {"id": "cmd_vrach", "title": "Личный советник"},
        {"id": "cmd_support", "title": "Поддержка"},
        {"id": "cmd_food", "title": "Советы по питанию"},
        {"id": "cmd_photo", "title": "Дневник питания"},
        {"id": "cmd_ban", "title": "Запрещённые продукты"},
    ]
    chunk = buttons[:3]
    has_more = len(buttons) > 3
    if has_more:
        chunk.append({"id": "cmd_next", "title": "Ещё"})
    send_whatsapp_quick_reply(phone, "Главное меню. Выберите действие:", chunk)

def process_button(message, phone):
    btn_id = message["interactive"]["button_reply"]["id"]
    if btn_id == "cmd_vrach":
        send_whatsapp_message(phone, "Вы подключены к личному советнику. Задайте вопрос.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_support":
        send_whatsapp_message(phone, "Связь с поддержкой: +992 900 00 00 00")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_food":
        buttons = [
            {"id": "cmd_breakfast", "title": "Завтрак"},
            {"id": "cmd_lunch", "title": "Обед"},
            {"id": "cmd_dinner", "title": "Ужин"},
            {"id": "cmd_snack", "title": "Перекус"},
            {"id": "cmd_back", "title": "Назад"},
        ]
        send_whatsapp_quick_reply(phone, "Выберите приём пищи:",
                                  buttons[:3] + ([{"id": "cmd_nextfood", "title": "Ещё"}] if len(buttons) > 3 else []))
        return {"status": "ok"}
    elif btn_id == "cmd_next":
        buttons = [
            {"id": "cmd_photo", "title": "Дневник питания"},
            {"id": "cmd_ban", "title": "Запрещённые продукты"},
            {"id": "cmd_back", "title": "Назад"},
        ]
        send_whatsapp_quick_reply(phone, "Продолжение меню:", buttons)
        return {"status": "ok"}
    elif btn_id == "cmd_photo":
        send_whatsapp_message(phone, "Пришлите фото еды. Я постараюсь оценить блюдо.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_ban":
        send_whatsapp_message(phone, "Запрещённые продукты: сладости, сдоба, газировка и т.д.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_breakfast":
        send_whatsapp_message(phone, "Завтрак: каши, омлеты, творог и т.д.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_lunch":
        send_whatsapp_message(phone, "Обед: супы, мясо, овощи, гарниры и т.д.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_dinner":
        send_whatsapp_message(phone, "Ужин: рыба, овощи, кисломолочные продукты и т.д.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_snack":
        send_whatsapp_message(phone, "Перекус: орехи, фрукты, кефир и т.д.")
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_back":
        show_menu(phone)
        return {"status": "ok"}
    elif btn_id == "cmd_nextfood":
        buttons = [
            {"id": "cmd_snack", "title": "Перекус"},
            {"id": "cmd_back", "title": "Назад"},
        ]
        send_whatsapp_quick_reply(phone, "Выберите приём пищи:", buttons)
        return {"status": "ok"}
    show_menu(phone)
    return {"status": "ok"}
