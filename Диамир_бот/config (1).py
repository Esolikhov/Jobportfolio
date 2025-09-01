WHATSAPP_TOKEN = ""
WHATSAPP_PHONE_ID = ""
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

VERIFY_TOKEN = ""
SHEET_ID = ""
SERVICE_ACCOUNT_FILE = ""

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_SUPPORT_CHAT_IDS = [623765402, 766484819]
# OpenAI
OPENAI_API_KEY = ""
#OpenAI API ключ
# === Стартовая инструкция (3 шага) ===
START_IMAGE_URLS = [
    "https://files.catbox.moe/ikblab.png",  # Шаг 1
    "https://files.catbox.moe/ejbcy0.png",  # Шаг 2
    "https://files.catbox.moe/233020.png",  # Шаг 3
]
print(
    f"[CFG] WA_PHONE_ID={WHATSAPP_PHONE_ID} | WA_TOKEN_LAST8={WHATSAPP_TOKEN[-8:] if WHATSAPP_TOKEN else 'NONE'}",
    flush=True
)

