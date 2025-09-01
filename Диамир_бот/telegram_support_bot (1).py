import telebot
from config import TELEGRAM_BOT_TOKEN
from whatsapp_api import send_whatsapp_message

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def extract_wa_phone(message_text):
    for line in message_text.splitlines():
        if ":" in line:
            left, right = line.split(":", 1)
            if "whatsapp" in left.lower() or "телефон" in left.lower():
                return right.strip()
    return None

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    if message.reply_to_message:
        wa_phone = extract_wa_phone(message.reply_to_message.text)
        print("Текст сообщения, на которое отвечаем:")
        print(message.reply_to_message.text)
        print("Извлечённый номер WhatsApp:", wa_phone)
        if wa_phone:
            resp = send_whatsapp_message(wa_phone, f"Ответ поддержки: {message.text}")
            print("Результат отправки в WhatsApp:", resp.status_code, resp.text)
            if resp.status_code == 200:
                bot.reply_to(message, "✅ Ответ отправлен в WhatsApp!")
            else:
                bot.reply_to(
                    message,
                    f"❗ Не удалось отправить сообщение в WhatsApp. Ошибка: {resp.status_code} {resp.text}"
                )
            return
        else:
            bot.reply_to(message, "❗ Не удалось найти номер WhatsApp для ответа!")
            return

    if message.text.startswith("/ответ"):
        parts = message.text.split(maxsplit=2)
        if len(parts) == 3:
            wa_phone, reply_text = parts[1], parts[2]
            print(f"Команда /ответ: номер {wa_phone}, текст: {reply_text}")
            resp = send_whatsapp_message(wa_phone, f"Ответ поддержки: {reply_text}")
            print("Результат отправки в WhatsApp:", resp.status_code, resp.text)
            if resp.status_code == 200:
                bot.reply_to(message, "✅ Ответ отправлен в WhatsApp!")
            else:
                bot.reply_to(
                    message,
                    f"❗ Не удалось отправить сообщение в WhatsApp. Ошибка: {resp.status_code} {resp.text}"
                )
        else:
            bot.reply_to(message, "Используйте: /ответ <номер> <текст>")

if __name__ == "__main__":
    print("Telegram поддержка-бот запущен.")
    bot.polling(none_stop=True)
