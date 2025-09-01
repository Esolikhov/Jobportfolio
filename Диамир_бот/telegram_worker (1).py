import time
from telegram_support import get_updates, send_message_to_whatsapp

def main():
    print("== Telegram support worker started ==")
    last_update_id = None
    while True:
        updates = get_updates(offset=last_update_id)
        for update in updates.get("result", []):
            last_update_id = update["update_id"] + 1
            message = update.get("message", {})
            if not message or "reply_to_message" not in message:
                continue
            reply_to = message["reply_to_message"]
            text = reply_to.get("text", "")
            if text.startswith("Вопрос от WhatsApp пользователя"):
                # Достаем телефон пользователя
                phone = text.split()[4].replace(":", "")
                answer = message.get("text")
                send_message_to_whatsapp(phone, f"Ответ поддержки: {answer}")
        time.sleep(2)

if __name__ == "__main__":
    main()
