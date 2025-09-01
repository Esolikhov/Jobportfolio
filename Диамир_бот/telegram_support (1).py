import requests

TELEGRAM_BOT_TOKEN = "8035255326:AAF8xgiOwAJoGvFVi9i-KhiCRqoqiaGyktI"
SUPPORT_CHAT_IDS = [623765402, 766484819]

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in SUPPORT_CHAT_IDS:
        data = {
            "chat_id": chat_id,
            "text": text
        }
        requests.post(url, data=data)

def send_to_telegram_with_info(phone, user_message):
    text = f"Вопрос от WhatsApp пользователя {phone}:\n{user_message}\n\nОтветьте на это сообщение — ваш ответ уйдет пользователю!"
    send_to_telegram(text)

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 60}
    if offset:
        params["offset"] = offset
    return requests.get(url, params=params).json()

def send_message_to_whatsapp(phone, text):
    from whatsapp_api import send_whatsapp_message
    send_whatsapp_message(phone, text)
