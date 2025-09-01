import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_SUPPORT_CHAT_IDS
from whatsapp_api import send_whatsapp_message

def send_to_telegram(text, phone):
    """
    Отправляет сообщение в Telegram всем операторам поддержки.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message = f"Пользователь WhatsApp: {phone}\n\n{text}"
    for chat_id in TELEGRAM_SUPPORT_CHAT_IDS:
        data = {"chat_id": chat_id, "text": message}
        resp = requests.post(url, data=data)
        print("Ответ Telegram:", chat_id, resp.status_code, resp.text)
    return True

import telebot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def extract_wa_phone(text):
    for line in text.splitlines():
        if ":" in line:
            left, right = line.split(":", 1)
            if "whatsapp" in left.lower() or "телефон" in left.lower():
                return right.strip()
    return None

@bot.message_handler(func=lambda m: m.reply_to_message is not None)
def reply_handler(message):
    print("Получено reply-сообщение. Текст исходного сообщения:")
    print(message.reply_to_message.text)
    wa_phone = extract_wa_phone(message.reply_to_message.text)
    print("Извлечённый номер WhatsApp:", wa_phone)
    if wa_phone:
        resp = send_whatsapp_message(wa_phone, f"Ответ поддержки:\n{message.text}")
        print("Ответ от WhatsApp API:", resp.status_code, resp.text)
        if resp.status_code == 200 or resp.status_code == 201:
            bot.reply_to(message, "✅ Ответ отправлен пользователю WhatsApp!")
        else:
            bot.reply_to(message, f"❗ Ошибка отправки в WhatsApp: {resp.status_code} {resp.text}")
    else:
        bot.reply_to(message, "❗ Не найден номер WhatsApp для ответа.")

@bot.message_handler(commands=['ответ'])
def manual_reply_handler(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) == 3:
        wa_phone, reply_text = parts[1], parts[2]
        print(f"Обработка команды /ответ: номер {wa_phone}, текст: {reply_text}")
        resp = send_whatsapp_message(wa_phone, f"Ответ поддержки:\n{reply_text}")
        print("Ответ от WhatsApp API:", resp.status_code, resp.text)
        if resp.status_code == 200 or resp.status_code == 201:
            bot.reply_to(message, "✅ Ответ отправлен пользователю WhatsApp!")
        else:
            bot.reply_to(message, f"❗ Ошибка отправки в WhatsApp: {resp.status_code} {resp.text}")
    else:
        bot.reply_to(message, "Используйте: /ответ <номер> <текст>")

if __name__ == "__main__":
    print("Telegram поддержка-бот запущен.")
    bot.polling(none_stop=True)
