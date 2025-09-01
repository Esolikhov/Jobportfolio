import requests
import hashlib
from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

# Диагностика при импорте
print(f"[BOOT][WA_API] PHONE_ID={WHATSAPP_PHONE_ID}")
print(f"[BOOT][WA_API] TOKEN_SHA1={hashlib.sha1(WHATSAPP_TOKEN.encode()).hexdigest()[:8]}")

def normalize_phone(phone: str) -> str:
    """Приводим +992... к 992..., убираем пробелы/плюсы."""
    phone = str(phone).strip().replace("+", "").replace(" ", "")
    return phone

def send_whatsapp_message(phone: str, text: str):
    """
    Обычное текстовое сообщение (работает внутри 24ч окна).
    Для сообщений вне окна — использовать шаблоны.
    """
    phone = normalize_phone(phone)
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(url, headers=headers, json=data)
        print(f"[WA][{phone}] {resp.status_code}: {resp.text}")
        if resp.status_code != 200:
            print(f"[WA][ERROR] Не удалось отправить сообщение {phone}. Текст: {text}")
        return resp
    except Exception as e:
        print(f"[WA][EXCEPTION] {e}")
        return None

def send_whatsapp_quick_reply(phone: str, text: str, buttons: list[dict]):
    """
    Кнопки быстрого ответа (interactive/button).
    buttons: [{"id":"...", "title":"..."}], title <= 20 символов.
    """
    phone = normalize_phone(phone)
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    quick_replies = [
        {"type": "reply", "reply": {"id": btn["id"], "title": str(btn["title"])[:20]}}
        for btn in buttons
    ]
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {"buttons": quick_replies},
        },
    }
    try:
        resp = requests.post(url, headers=headers, json=data)
        print(f"[WA][{phone}][QuickReply] {resp.status_code}: {resp.text}")
        if resp.status_code != 200:
            print(f"[WA][ERROR] Не удалось отправить quick-reply {phone}")
        return resp
    except Exception as e:
        print(f"[WA][EXCEPTION] {e}")
        return None

def send_whatsapp_image(phone: str, image_url: str, caption: str | None = None):
    """Отправка изображения по ссылке с необязательной подписью."""
    phone = normalize_phone(phone)
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "image",
        "image": {"link": image_url},
    }
    if caption:
        data["image"]["caption"] = caption
    try:
        resp = requests.post(url, headers=headers, json=data)
        print(f"[WA][{phone}][Image] {resp.status_code}: {resp.text}")
        return resp
    except Exception as e:
        print(f"[WA][EXCEPTION] {e}")
        return None

def download_whatsapp_media(media_id: str):
    """
    Скачивание медиа по media_id:
      1) GET /{media_id} -> metadata с 'url'
      2) GET media_url    -> контент
    """
    meta_url = f"https://graph.facebook.com/v19.0/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    print(f"Пробуем получить метаданные для media_id: {media_id}")
    try:
        resp = requests.get(meta_url, headers=headers)
        print(f"Ответ на metadata: {resp.status_code} {resp.text}")
        if resp.status_code != 200:
            print(f"Ошибка получения URL медиа: {resp.status_code} {resp.text}")
            return None

        media_url = resp.json().get("url")
        print(f"media_url = {media_url}")
        if not media_url:
            print("URL медиафайла не найден")
            return None

        media_resp = requests.get(media_url, headers=headers)
        print(f"Ответ на скачивание файла: {media_resp.status_code}")
        if media_resp.status_code == 200:
            print("Медиа успешно скачан, размер:", len(media_resp.content))
            return media_resp.content

        print(f"Ошибка скачивания медиа: {media_resp.status_code} {media_resp.text}")
        return None
    except Exception as e:
        print(f"[WA][EXCEPTION][DOWNLOAD] {e}")
        return None
