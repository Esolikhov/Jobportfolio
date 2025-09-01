# --- УСТАНОВКА ЗАВИСИМОСТЕЙ (для ноутбуков/Colab; в проде можно убрать) ---
!apt-get -y install tesseract-ocr libtesseract-dev tesseract-ocr-rus tesseract-ocr-eng >/dev/null
!wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/tgk.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/tgk.traineddata
!pip -q install --upgrade gradio pdfplumber pillow pytesseract

# --- ИМПОРТЫ ---
import gradio as gr
import pytesseract
from PIL import Image
import pdfplumber
import re
import os
from decimal import Decimal, InvalidOperation
from datetime import datetime

# Путь к tesseract (Ubuntu)
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract" if os.path.exists("/usr/bin/tesseract") else pytesseract.pytesseract.tesseract_cmd

# --- ЯЗЫКИ ДЛЯ OCR ---
LANG_MAP = {
    "Русский": "rus",
    "Таджикский": "tgk",
    "Английский": "eng",
    "Авто (рус+тадж+англ)": "rus+tgk+eng"
}

# --- ХЕЛПЕРЫ ---
def _lat_to_cyr(s: str) -> str:
    # мягкая коррекция (только для ПОИСКА/меток)
    return s.translate(str.maketrans({
        "c":"с","o":"о","p":"р","a":"а","e":"е","x":"х","y":"у","k":"к","m":"м","t":"т","h":"н","b":"в","i":"і","j":"ј"
    }))

def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _norm_date_ddmmyyyy(s: str) -> str:
    m = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", s)
    if not m: return ""
    dd, mm, yyyy = m.groups()
    return f"{yyyy}-{mm}-{dd}"

_RU_MONTHS = {
    "января":"01","февраля":"02","марта":"03","апреля":"04","мая":"05","июня":"06",
    "июля":"07","августа":"08","сентября":"09","октября":"10","ноября":"11","декабря":"12"
}
def _norm_date_ru_words(s: str):
    # '20 августа, 09:33' -> ('YYYY-08-20','09:33') с текущим годом
    m = re.search(r'\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b[, ]*\s*(\d{1,2}:\d{2}(?::\d{2})?)?', s.lower())
    if not m: return None, None
    dd = int(m.group(1)); mm = _RU_MONTHS[m.group(2)]; t = m.group(3) or None
    return f"{datetime.now().year}-{mm}-{dd:02d}", t

def _to_decimal(s: str) -> str:
    if s is None: return ""
    s = re.sub(r"[^\d\.,-]", "", str(s)).replace(",", ".")
    try:
        return str(Decimal(s))
    except InvalidOperation:
        return re.sub(r"[^\d\.]", "", s)

def _pick_money(text: str) -> str:
    # сперва десятичные, затем целые >=2 знаков; одиночная цифра — крайний случай
    decs = re.findall(r"(?<!\d)(\d{1,3}(?:[ \u00A0]\d{3})*|\d+)[\.,]\d{2,3}(?!\d)", text)
    if decs:
        return decs[-1].replace(" ", "").replace("\u00A0", "")
    ints = re.findall(r"(?<!\d)(\d{2,})(?!\d)", text)
    if ints:
        return ints[-1]
    ones = re.findall(r"(?<!\d)(\d)(?!\d)", text)
    if ones:
        return ones[-1]
    return ""

# --- Валюта ---
def _detect_currency(line: str) -> str | None:
    U = line.upper()
    if re.search(r'\bT\s*J\s*S\b', U) or "T]S" in U or "T]5" in U: return "TJS"
    if re.search(r"\bTJS\b", U) or re.search(r"\bТJS\b", U): return "TJS"
    if re.search(r"\b(СОМОНИ|СОМОН|SOMONI|СОМ|SOM)\b", U): return "TJS"
    if re.search(r"\b[SCС]\.?\b", U): return "TJS"  # 'с'/'c' с точкой и без
    if "RUB" in U or "₽" in U or "РУБ" in U: return "RUB"
    if "EUR" in U or "€" in U: return "EUR"
    if "USD" in U or re.search(r"\$\s*\d", U): return "USD"
    return None

def _contains_currency_token(line: str) -> bool:
    return _detect_currency(line) is not None

def _norm_colon_as_decimal(line: str) -> str:
    # заменяем двоеточие на точку ТОЛЬКО когда между цифрами и похоже на денежный разделитель (не время)
    return re.sub(r'(?<=\d):(?=\d{2,3}\b)', '.', line)

CUR_TJS = r'(?:T\s*J\s*S|T]S|T]5|TJS|ТJS|СОМОНИ|СОМОН|SOMONI|СОМ|SOM|[SCС]\.?)'
def _extract_amount_currency(line: str, allow_colon_decimal: bool = False, require_currency: bool = False, favor_near_currency: bool = True):
    """
    Извлечь сумму и валюту из строки.
    1) Пробуем число рядом с валютой (надёжно для '168.67 с.').
    2) Потом общий поиск денег ('.'/'','', и при allow_colon_decimal — '1:67').
    3) Если require_currency=True — только при наличии токена валюты.
    """
    src = _norm_colon_as_decimal(line) if allow_colon_decimal else line
    U = src.upper()

    # 1) вокруг валютных токенов
    if favor_near_currency:
        m = re.search(rf'(?P<num>(?:\d{{1,3}}(?:[ \u00A0]\d{{3}})*|\d+)(?:[.,]\d{{1,3}})?)\s*{CUR_TJS}\b', U)
        if m:
            num = m.group("num").replace("\u00A0", " ").replace(" ", "").replace(",", ".")
            return num, "TJS" if re.search(CUR_TJS, U) else None
    # валюта перед числом
    m2 = re.search(rf'\b{CUR_TJS}\s*(?P<num>(?:\d{{1,3}}(?:[ \u00A0]\d{{3}})*|\d+)(?:[.,]\d{{1,3}})?)', U)
    if m2:
        num = m2.group("num").replace("\u00A0", " ").replace(" ", "").replace(",", ".")
        return num, "TJS"

    if require_currency and not _contains_currency_token(U):
        return None, None

    # спец: иногда OCR рвёт на '1 67'
    if allow_colon_decimal:
        msp = re.search(r'(?<!\d)(\d+)\s+(\d{2,3})(?!\d)', src)
        if msp:
            return f"{msp.group(1)}.{msp.group(2)}", _detect_currency(U)

    num = _pick_money(src if not require_currency else U)
    cur = _detect_currency(U)
    return (num.replace(",", ".") if num else None), cur

def _fix_card_brand_mask(s: str):
    # VASL***1750 -> VISA***1750
    return re.sub(r'^VASL(\*{2,}\d{4})$', r'VISA\1', s.strip(), flags=re.IGNORECASE)

def _date_max(iso_a: str, iso_b: str) -> str:
    if not iso_a: return iso_b
    if not iso_b: return iso_a
    try:
        da = datetime.fromisoformat(iso_a); db = datetime.fromisoformat(iso_b)
        return iso_a if da >= db else iso_b
    except Exception:
        return iso_a

# --- НОРМАЛИЗАЦИЯ БАНКОВ/ПРОДАВЦА ---
def _normalize_bank_name(s: str) -> str:
    raw = _lat_to_cyr(s.lower())
    if ("бонк" in raw or "банк" in raw) and ("байналмилал" in raw or "международн" in raw) and ("точикистон" in raw or "таджикист" in raw):
        return "Бонки байналмилалии Тоҷикистон"
    if "банк" not in raw and "бонк" not in raw:
        return s
    return "Банк"

def _normalize_seller_name(line: str) -> str | None:
    l = _lat_to_cyr(line.lower())
    l = re.sub(r'\b0{3}\b', 'ооо', l)
    l = l.replace('“','"').replace('”','"').replace("«","\"").replace("»","\"")
    if any(org in l for org in ("ооо","зао","ао")):
        m = re.search(r'\b(ооо|зао|ао)\b\s*"?\s*([A-Za-zА-Яа-яёЁ\- ]+)"?', l, re.IGNORECASE)
        if m:
            form = m.group(1).upper()
            name = _clean_spaces(m.group(2)).title()
            return f'{form} «{name}»'
    if "азс" in l:
        m = re.search(r'азс\s*"?\s*([A-Za-zА-Яа-яёЁ\- ]+)"?', l)
        if m:
            return f'АЗС «{_clean_spaces(m.group(1)).title()}»'
    return None

# --- OCR ---
def extract_text(file, lang):
    path = file if isinstance(file, str) else getattr(file, "name", None)
    if not path:
        return ""
    if path.lower().endswith(".pdf"):
        chunks = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=300)
                chunks.append(pytesseract.image_to_string(img.original, lang=lang))
        return "\n".join(chunks)
    image = Image.open(path)
    return pytesseract.image_to_string(image, lang=lang)

# --- НОРМАЛИЗАЦИЯ МЕТОК ---
def normalize_label(label):
    label = _lat_to_cyr(label.lower())
    label = label.replace("+", "ғ").replace("ё", "е").replace("ӣ", "и").replace("қ", "к").replace("ҳ", "х").replace("ғ", "г")

    if "воридшуда" in label and ("маблаг" in label or "маблағ" in label): return "received_amount"
    if "хонат" in label or "холат" in label: return "status"

    replace_map = {
        # суммы / итоги
        "итого":"total","итог":"total","всего":"total","total":"total","маблаки хоричшуда":"total",
        "сумма":"amount","amount":"amount","количество":"qty","кол-во":"qty","маблаг":"amount","маблағ":"amount","комиссия":"commission",
        # ид/контракты/банки
        "номер транзакции":"transaction_id","номер операции":"transaction_id","номер":"transaction_id","раками интикол":"transaction_id",
        "шартнома":"contract_number","банк":"bank","бонк":"bank",
        # дата/время
        "дата":"date","время":"time","дата операции":"op_datetime","санаи ичроиши амалиет":"date","санаи_ичроиши_амалиёт":"date",
        # счета/карты/получатель
        "счет получателя":"account_to","счет отправителя":"account_from","суратхисоби харочоти":"account_from",
        "карта":"card","намуди суратхисоб":"card_type",
        "получатель":"recipient","маълумот клиент":"recipient",
        # прочее
        "комментарий":"comment","comment":"comment",
        # фискальные
        "смена":"shift","продажа":"sale_no","зак":"order_no","кассир":"cashier","сайт фнс":"fns_site","фн":"fn","фд":"fd","фп":"fp",
        "безналичными":"payment_method","наличными":"payment_method",
        # шум — игнор
        "чсп":"", "q_э_байналмилалии_эл":"", "хизматрасони_ос":"", "рма":"", "рмб":""
    }
    for k, v in replace_map.items():
        if k in label: return v
    return label.replace(":", "").replace(".", "").replace(" ", "_")

# --- ФИЛЬТРЫ МУСОРА/ИНТЕРФЕЙСА ---
DROP_SUBSTR = ["в избранное","избранное","повторить","онлайн чек","подробности операции","eg i","ie","сі","ле ed","le ed"]
def is_garbage_line(line: str) -> bool:
    l = line.lower()
    if any(s in l for s in DROP_SUBSTR): return True
    if re.match(r'^\s*\d{1,2}:\d{2}\b.*:\s*$', line): return True  # "10:48 LE ED:"
    return False

def is_trailing_count_line(line: str) -> bool:
    """Игнор строк, оканчивающихся на одиночное число (например, 'Деньги дошли! 7')."""
    s = _clean_spaces(line)
    if re.search(r'\b\d{2}:\d{2}(:\d{2})?\b', s): return False
    if re.search(r'\d+[.,]\d+', s): return False
    if re.search(r'(tjs|сомон|somoni|сом|som|[scс]\.?)', s, re.IGNORECASE): return False
    if ':' in s: return False
    return bool(re.search(r'.*\b\d{1,2}\b$', s))

# --- СКЛЕЙКА "ПОРВАННЫХ" СТРОК ---
def _is_currency_only(line: str) -> bool:
    l = _clean_spaces(line)
    return bool(re.fullmatch(r'(?i)(t\s*j\s*s|t]s|t]5|tjs|тjs|сомони|сомон|somoni|сом|som|[scс]\.?)', l))

def _ends_with_number(line: str) -> bool:
    return bool(re.search(r'(\d{1,3}(?:[ \u00A0]\d{3})*|\d+)(?:[.,]\d{2,3})?$', line))

def _merge_broken_lines(lines_raw):
    """Склеиваем случаи: [число] + [валюта на следующей строке]; а также '1' + '67' после метки."""
    lines = []
    i = 0
    while i < len(lines_raw):
        s = _clean_spaces(lines_raw[i])
        if not s or is_garbage_line(s) or is_trailing_count_line(s):
            i += 1
            continue

        # число в конце + валюта отдельной строкой
        if _ends_with_number(s) and i+1 < len(lines_raw):
            nxt = _clean_spaces(lines_raw[i+1])
            if _is_currency_only(nxt):
                s = f"{s} {nxt}"
                i += 1  # проглотили валюту

        # 'Комиссия'/'Итог'/'Сумма' -> '1' + '67' (две строки)
        if re.fullmatch(r'(?i)(комиссия|итого?|total|сумма)', s) and i+2 < len(lines_raw):
            a = _clean_spaces(lines_raw[i+1])
            b = _clean_spaces(lines_raw[i+2])
            if re.fullmatch(r'\d{1,3}', a) and re.fullmatch(r'\d{2,3}', b):
                # преобразуем в одну строку после метки: "1.67"
                lines.append(s)           # метка
                lines.append(f"{a}.{b}")  # слитная дробь
                i += 3
                continue

        lines.append(s)
        i += 1
    return lines

# --- РОЗНИЧНЫЕ ПОЗИЦИИ (qty × price) ---
ITEM_PATTERN = re.compile(r'^(?P<name>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s*[xх×]\s*(?P<price>\d+(?:[.,]\d+)?)\b', re.IGNORECASE)
def try_parse_item(line: str):
    m = ITEM_PATTERN.search(_clean_spaces(line))
    if not m: return None
    name = m.group("name").strip(' ."«»')
    qty = _to_decimal(m.group("qty"))
    price = _to_decimal(m.group("price"))
    try:
        total = str(Decimal(qty) * Decimal(price))
    except Exception:
        total = ""
    return {"name": name, "qty": qty, "unit_price": price, "line_total": total}

# --- ЧИСТКА JSON ---
def clean_json(parsed):
    out = {}
    for k, v in parsed.items():
        if v is None: continue
        if isinstance(v, str) and v.strip() in (":","с","-","","—"): continue

        k_norm = k
        if k in ("итог","итого","всего"): k_norm="total"
        if k in ("количество",):          k_norm="qty"
        if k in ("статус",):              k_norm="status"
        if k in ("банк","бонк"):          k_norm="bank"
        if k in ("дата",):                k_norm="date"
        if k in ("время","Время"):        k_norm="time"
        if k == "op_datetime":            k_norm="op_datetime"

        val = str(v)

        if k_norm == "transaction_id":
            val = re.sub(r"\D+", "", val)  # '9733392 0' -> '97333920'

        if k_norm in ("commission","amount","total","sum_without_vat","sum_with_vat","received_amount"):
            val = _to_decimal(val)
        elif k_norm == "phone":
            val = re.sub(r"[^\d\+\s\-]", "", val)
        elif k_norm == "status":
            val = "SUCCESS" if re.search(r"дошл|на балансе|перевод отправлен безопасно|успешн|success|испол|оплачено|paid|done|выполнен|шуд", val, re.IGNORECASE) else val.strip()
        elif k_norm == "date":
            iso = _norm_date_ddmmyyyy(val)
            if iso: val = iso

        out[k_norm] = val

    # Разворачиваем op_datetime -> date/time, не затирая более свежую дату
    if "op_datetime" in out:
        m = re.search(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})', out["op_datetime"])
        if m:
            out["date"] = _date_max(out.get("date",""), m.group(1))
            if "time" not in out: out["time"] = m.group(2)
        out.pop("op_datetime", None)

    return out

# --- ПАРСЕР ЧЕКОВ ---
def universal_parse(text):
    result, items = {}, []
    currency = None
    pending_label = None
    notif_hit = False

    # 0) Предочистка + склейка "порванных" строк
    lines_raw = text.splitlines()
    lines = _merge_broken_lines(lines_raw)

    # 1) Основной проход (индексный, чтобы видеть next-строки при необходимости)
    i = 0
    while i < len(lines):
        raw = lines[i]
        line_norm = _lat_to_cyr(raw)
        l = line_norm.lower()

        # Русская словесная дата
        d_ru, t_ru = _norm_date_ru_words(raw)
        if d_ru:
            result["date"] = _date_max(result.get("date",""), d_ru)
            if t_ru and "time" not in result: result["time"] = t_ru

        # "Дата операции: 2025-08-18 18:19:29"
        if "дата операции" in l:
            val = re.split(r'дата\s+операции', raw, flags=re.IGNORECASE)[-1]
            ts = re.search(r'(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?', val)
            if ts:
                result["date"] = _date_max(result.get("date",""), ts.group(1))
                if ts.group(2) and "time" not in result:
                    result["time"] = ts.group(2)
            i += 1
            continue

        # Карта + маска
        if re.search(r'\bкарта\b', l) and re.search(r'\*{2,}\d{4}\b', raw):
            mask = re.search(r'([A-Za-z]+[*\d]{6,})', raw)
            if mask:
                result["card_mask"] = _fix_card_brand_mask(mask.group(1))
                result.setdefault("card_type", "Карта")

        # Получатель (+ телефон)
        if re.search(r'\bполучател[ья]\b', l):
            val = re.split(r'получател[ья]', raw, flags=re.IGNORECASE)[-1].strip(" :–-")
            if val: result["recipient"] = val
        m_phone = re.search(r'(\+\d[\d\s\-]{7,})', raw)
        if m_phone:
            result["recipient_phone"] = _clean_spaces(m_phone.group(1))

        # Номер транзакции
        if "номер транзакции" in l:
            val = re.split(r'номер\s+транзакции', raw, flags=re.IGNORECASE)[-1]
            val = re.sub(r"\D+", "", val)
            if val: result["transaction_id"] = val
            i += 1
            continue

        # Комиссия/Итог/Сумма — допускаем ':' и разрыв "1 67" (склейка уже сделана в _merge_broken_lines)
        if re.fullmatch(r'(?i)комиссия', raw):
            pending_label = "commission"; i += 1; continue
        if re.fullmatch(r'(?i)(итого?|total)', raw):
            pending_label = "total"; i += 1; continue
        if re.fullmatch(r'(?i)сумма', raw):
            pending_label = "amount"; i += 1; continue

        if pending_label:
            num, cur = _extract_amount_currency(raw, allow_colon_decimal=True, require_currency=False)
            if num:
                result[pending_label] = num
                if cur and currency is None: currency = cur
                pending_label = None
                i += 1
                continue

        # Якоря сумм в одной строке
        if re.search(r'\b(комиссия|итого?|total|сумма)\b', l):
            num, cur = _extract_amount_currency(raw, allow_colon_decimal=True, require_currency=False)
            if num:
                if "комиссия" in l:
                    result["commission"] = num
                elif re.search(r'\bитого?|total\b', l):
                    result["total"] = num
                elif "сумма" in l and "amount" not in result:
                    result["amount"] = num
            if cur and currency is None:
                currency = cur

        # Денежная строка без метки — берём как amount ТОЛЬКО если видна валюта
        if "amount" not in result and _contains_currency_token(raw):
            num, cur = _extract_amount_currency(raw, allow_colon_decimal=True, require_currency=True)
            if num: result["amount"] = num
            if cur and currency is None: currency = cur

        # Статус (уведомления)
        if re.search(r"дошл|на балансе|перевод отправлен безопасно|успешн|success|испол|оплачено|paid|done|выполнен|шуд", l, re.IGNORECASE):
            result["status"] = "SUCCESS"; notif_hit = True

        # Банк
        if ("банк" in l) or ("бонк" in l):
            new_name = _normalize_bank_name(raw)
            if ("bank" not in result) or (result.get("bank") == "Банк" and new_name != "Банк"):
                result["bank"] = new_name

        # Организация
        if any(key in l for key in ("ооо","зао","ао","000","азс")):
            seller = _normalize_seller_name(raw)
            if seller: result["seller"] = seller

        # Отдельные дата/время
        d = _norm_date_ddmmyyyy(raw)
        if d: result["date"] = _date_max(result.get("date",""), d)
        t = re.search(r"\b\d{2}:\d{2}(?::\d{2})?\b", raw)
        if t and "time" not in result: result["time"] = t.group(0)

        # Позиции (розница)
        it = try_parse_item(raw)
        if it: items.append(it)

        # Общий случай "метка: значение"/"метка — значение"/двойные пробелы
        m = re.match(r"\s*([\w\s\.\:№\(\)\*\"«»]+)\s*[:\-—]\s*(.+)", line_norm, re.IGNORECASE) or \
            re.match(r"\s*([\w\s\.\:№\(\)\*\"«»]+?)\s{2,}(.+)", line_norm, re.IGNORECASE)
        if m:
            label_raw = m.group(1).strip().strip("«»\"")
            if not re.search(r'[A-Za-zА-Яа-яЁё]', label_raw):
                pass
            else:
                value = m.group(2).strip().strip("«»\"")
                label = normalize_label(label_raw)
                if label:
                    if label == "bank":
                        result["bank"] = _normalize_bank_name(value or label_raw)
                    elif label == "card":
                        mask = re.search(r'([A-Za-z]+[*\d]{6,})', value)
                        if mask:
                            result["card_mask"] = _fix_card_brand_mask(mask.group(1))
                            result.setdefault("card_type", "Карта")
                    elif label == "op_datetime":
                        ts = re.search(r'(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?', value)
                        if ts:
                            result["date"] = _date_max(result.get("date",""), ts.group(1))
                            if ts.group(2) and "time" not in result:
                                result["time"] = ts.group(2)
                    else:
                        result[label] = (result[label] + ", " + value) if label in result else value

        i += 1

    # Итоги по позициям (если были)
    if items:
        try:
            total_calc = str(sum(Decimal(it["line_total"]) for it in items if it.get("line_total")))
        except Exception:
            total_calc = ""
        if "total" not in result and total_calc: result["total"] = total_calc
        if "amount" not in result and "total" in result: result["amount"] = result["total"]
        result["items"] = items

    # Валюта
    if currency: result["currency"] = currency

    # Уведомление: убрать случайный qty
    if notif_hit and "items" not in result and "qty" in result:
        result.pop("qty", None)

    return result

def parse_check(text):
    parsed = universal_parse(text)
    parsed = clean_json(parsed)
    if not parsed or len(parsed) < 2:
        return {"raw_text": text.strip()}
    return parsed

# --- GRADIO ИНТЕРФЕЙС ---
def process(file, lang_sel):
    lang = LANG_MAP[lang_sel]
    text = extract_text(file, lang)
    parsed = parse_check(text)
    return parsed, text

with gr.Blocks() as demo:
    gr.Markdown("## 🧾 Универсальный парсер чеков (PDF, JPG, PNG, рус/тадж/англ, уведомления/банки/фискальные)")
    with gr.Row():
        file_in = gr.File(label="Загрузите чек (PDF или изображение)", file_types=["image", ".pdf"], type="filepath")
        lang_sel = gr.Radio(list(LANG_MAP.keys()), value="Авто (рус+тадж+англ)", label="Язык для OCR")
    with gr.Row():
        json_out = gr.JSON(label="JSON результат")
        text_out = gr.Textbox(label="Распознанный текст", lines=15)
    btn_clear = gr.Button("Clear")
    btn_submit = gr.Button("Submit")
    btn_submit.click(process, inputs=[file_in, lang_sel], outputs=[json_out, text_out])
    btn_clear.click(lambda: ({}, ""), None, [json_out, text_out])

demo.launch(share=True)
