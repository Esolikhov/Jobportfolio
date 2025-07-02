# --- УСТАНОВКА ЗАВИСИМОСТЕЙ ---
!apt-get -y install tesseract-ocr libtesseract-dev tesseract-ocr-rus tesseract-ocr-eng
!wget -O /usr/share/tesseract-ocr/4.00/tessdata/tgk.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/tgk.traineddata
!pip install --upgrade gradio pdfplumber pillow

# --- ИМПОРТЫ ---
import gradio as gr
import pytesseract
from PIL import Image
import pdfplumber
import re

# --- ЯЗЫКИ ДЛЯ ОРС ---
LANG_MAP = {
    "Русский": "rus",
    "Таджикский": "tgk",
    "Английский": "eng",
    "Авто (рус+тадж+англ)": "rus+tgk+eng"
}

# --- OCR ---
def extract_text(file, lang):
    if file.name.lower().endswith(".pdf"):
        with pdfplumber.open(file.name) as pdf:
            text = ""
            for page in pdf.pages:
                img = page.to_image(resolution=300)
                text += pytesseract.image_to_string(img.original, lang=lang) + "\n"
        return text
    else:
        image = Image.open(file.name)
        text = pytesseract.image_to_string(image, lang=lang)
        return text

# --- НОРМАЛИЗАЦИЯ ПОЛЕЙ ---
def normalize_label(label):
    label = label.lower()
    replace_map = {
        "номер транзакции": "transaction_id",
        "transaction id": "transaction_id",
        "номер операции": "transaction_id",
        "счёт зачисления": "account_to",
        "account to": "account_to",
        "счет отправителя": "account_from",
        "from account": "account_from",
        "счет получателя": "account_to",
        "to account": "account_to",
        "дата и время": "datetime",
        "дата операции": "date",
        "время операции": "time",
        "дата": "date",
        "время": "time",
        "сумма операции": "amount",
        "сумма": "amount",
        "итого": "total",
        "комиссия": "commission",
        "способ оплаты": "payment_method",
        "статус": "status",
        "comment": "comment",
        "комментарий": "comment",
        "инн": "inn",
        "бик": "bik",
        "лицензия": "license",
        "получатель": "recipient",
        "поставщик": "recipient",
        "электронный платеж": "is_electronic",
        "исполнено": "status",
        "успешный": "status",
        "оплачено": "status",
    }
    for k, v in replace_map.items():
        if k in label:
            return v
    return label.replace(":", "").replace(".", "").replace(" ", "_")

# --- УНИВЕРСАЛЬНЫЙ ПАРСЕР ЧЕКОВ ---
def universal_parse(text):
    result = {}
    lines = text.splitlines()
    for line in lines:
        # Находим пары "Метка: Значение" или "Label - Value"
        m = re.match(r"\s*([\w\s\.\:№\(\)\*]+)[\:\-\—]\s*(.+)", line, re.IGNORECASE)
        if not m:
            # Пробуем альтернативно "Label Value"
            m = re.match(r"\s*([\w\s\.\:№\(\)\*]+)\s+([^\s]+)", line, re.IGNORECASE)
        if m:
            label = normalize_label(m.group(1).strip())
            value = m.group(2).strip()
            if label in result:
                result[label] += ', ' + value
            else:
                result[label] = value
        else:
            # Смотрим статус, даты, суммы отдельными регулярками
            if re.search(r"успешн(ый|о)|исполнено|paid|оплачено|operation done|success", line, re.IGNORECASE):
                result["status"] = "SUCCESS"
            elif re.search(r"\d{4}\-\d{2}\-\d{2}", line):  # 2025-07-02
                result["date"] = line.strip()
            elif re.search(r"\d{2}:\d{2}(:\d{2})?", line):
                result["time"] = line.strip()
            elif re.search(r"[0-9]+\s*[сc]", line):
                result["amount"] = line.strip()
    # "дата и время"
    if "datetime" in result:
        dt = result.pop("datetime")
        parts = dt.split(",")
        if len(parts) == 2:
            result["date"] = parts[0].strip()
            result["time"] = parts[1].strip()
    # Находим счета/телефоны/карты (12+ цифр подряд, если ещё не найдено)
    m = re.search(r'\b(\d{12,})\b', text)
    if m and "account_to" not in result:
        result["account_to"] = m.group(1)
    return result

def parse_check(text):
    parsed = universal_parse(text)
    # Если не найдено ни одного поля — возвращаем весь текст
    if not parsed or len(parsed) < 2:
        return {"raw_text": text.strip()}
    return parsed

# --- ОСНОВНОЙ GRADIO ИНТЕРФЕЙС ---
def process(file, lang_sel):
    lang = LANG_MAP[lang_sel]
    text = extract_text(file, lang)
    parsed = parse_check(text)
    return parsed, text

with gr.Blocks() as demo:
    gr.Markdown("## 🧾 Универсальный парсер чеков Таджикистана (PDF, JPG, PNG, любые банки)")
    with gr.Row():
        file_in = gr.File(label="Загрузите чек (PDF или изображение)", file_types=["image", ".pdf"], type="filepath")
        lang_sel = gr.Radio(list(LANG_MAP.keys()), value="Авто (рус+тадж+англ)", label="Язык для OCR")
    with gr.Row():
        json_out = gr.JSON(label="JSON результат")
        text_out = gr.Textbox(label="Распознанный текст", lines=15)
    btn_clear = gr.Button("Clear")
    btn_submit = gr.Button("Submit")
    btn_submit.click(
        process,
        inputs=[file_in, lang_sel],
        outputs=[json_out, text_out]
    )
    btn_clear.click(
        lambda: ({}, ""), None, [json_out, text_out]
    )

demo.launch(share=True)
