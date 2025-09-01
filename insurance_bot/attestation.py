# attestation.py

import re

QUESTIONS = [
    "1. Для чего нужно страхование?",
    "2. Назовите два основных вида страхования.",
    "3. Что нужно знать перед оформлением страхового полиса?"
]

PROMO_CODE = "INSUR2024"

# Состояния для этапов аттестации и собеседования
STATE_ATT_QUESTION = "att_question"
STATE_INTERVIEW = "interview"

def start_attestation(context, user_id):
    context.user_data[user_id] = {'state': STATE_ATT_QUESTION, 'step': 0, 'answers': []}
    return QUESTIONS[0]

def process_attestation(context, user_id, answer):
    user_data = context.user_data[user_id]
    user_data['answers'].append(answer)
    user_data['step'] += 1
    if user_data['step'] < len(QUESTIONS):
        return QUESTIONS[user_data['step']]
    else:
        user_data['state'] = STATE_INTERVIEW
        return (f"Поздравляем! Вы успешно прошли итоговую аттестацию!\n"
                f"Ваш промокод: {PROMO_CODE}\n\n"
                "Для записи на собеседование напишите свои ФИО и номер телефона (можно в любом порядке, пример: Иванов Иван +992900000000).")

def process_interview(context, user_id, text):
    # Ищем телефон в любом формате (начинается с + или с 8/9 и длина от 9 до 13 цифр)
    phone_match = re.search(r'(\+?\d[\d\-\s]{8,})', text)
    if phone_match:
        phone = phone_match.group(1).replace(' ', '').replace('-', '')
    else:
        return "Пожалуйста, укажите номер телефона — он не найден в сообщении."

    # ФИО — всё кроме телефона (чистим из текста найденный телефон)
    name = text.replace(phone_match.group(1), '').replace(',', '').strip()

    # Если совсем пусто — просим ввести имя
    if not name:
        return "Пожалуйста, укажите ваше имя вместе с номером телефона."

    with open("interviews.csv", "a", encoding="utf-8") as f:
        f.write(f"{user_id},{name},{phone}\n")
    context.user_data[user_id]['state'] = None
    return f"Спасибо, {name}! Ваша заявка на собеседование принята.\nС вами свяжутся в ближайшее время."

def get_state(context, user_id):
    return context.user_data.get(user_id, {}).get('state')
