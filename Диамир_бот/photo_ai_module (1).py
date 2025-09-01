# photo_ai_module.py
# Мульти-распознавание еды/напитков на фото.
# Возвращает (result_block, score, comment, recognized_bool).
# Новое:
# - корректная оценка для низкого ГИ и низких углеводов (яйца и т.п.);
# - жёсткая ветка для сладких батончиков;
# - дедупликация одинаковых позиций (суммирование порции/макросов);
# - общий комментарий «Рекомендовано», если все пункты хорошие (<=2).

import re
import json
import base64
from typing import Tuple, Dict, Any, List

import requests

from config import OPENAI_API_KEY
from whatsapp_api import download_whatsapp_media
from sheets_api import get_personal_profile

# ---- Настройки модели ----
MODEL = "gpt-4o"  # при необходимости можно сменить на "gpt-5o"

# Эвристическая шкала (fallback), 1 — отлично, 3 — осторожно, 4–5 — хуже/нельзя
SCORES = [
    ("мясо", 1, "Отлично — белок, клетчатка, низкий ГИ."),
    ("говядина", 1, "Отлично — белок, клетчатка, низкий ГИ."),
    ("курица", 1, "Отлично — белок, клетчатка."),
    ("рыба", 1, "Хороший вариант для вечера."),
    ("овощ", 1, "Отлично: белок, клетчатка."),
    ("яйц", 1, "Отличный источник белка, низкий ГИ."),  # ← добавлено
    ("каша", 3, "Каша — осторожно, порция поменьше."),
    ("плов", 4, "Высокая нагрузка, осторожно."),
    ("рис", 4, "Высокая нагрузка, осторожно."),
    ("макароны", 4, "Высокая нагрузка, осторожно."),
    ("картошк", 4, "Высокая нагрузка, осторожно."),
    ("сырники", 4, "Быстрые углеводы и жир."),
    ("вафли", 5, "Высокий сахар и углеводы."),
    ("торт", 5, "Высокий сахар и углеводы."),
    ("десерт", 5, "Высокий сахар и углеводы."),
    ("булка", 5, "Высокий сахар и углеводы."),
    # сладкие фрукты
    ("арбуз", 3, "Высокий ГИ; маленькая порция, лучше с белком/клетчаткой."),
    ("дын", 3, "Сладкая дыня — маленькая порция, лучше с белком/клетчаткой."),
    ("виноград", 4, "Очень сладкий фрукт — маленькая порция."),
    ("банан", 4, "Сладкий фрукт — маленькая порция."),
    ("манго", 4, "Сладкий фрукт — маленькая порция."),
    ("ананас", 4, "Сладкий фрукт — маленькая порция."),
    ("финик", 5, "Сухофрукт — очень много сахара."),
    ("изюм", 5, "Сухофрукт — очень много сахара."),
    ("сухофрукт", 5, "Сухофрукты — очень много сахара."),
    # шоколадные батончики / конфеты
    ("сникерс", 5, "Шоколадный батончик — быстрые сахара и жиры, не рекомендовано."),
    ("snickers", 5, "Шоколадный батончик — быстрые сахара и жиры, не рекомендовано."),
    ("батончик", 5, "Сладкий шоколадный батончик — быстрые сахара и жиры, не рекомендовано."),
    ("шоколад", 4, "Сладкое — маленькая порция, лучше избегать при высоком сахаре."),
]

# Хинты
HIGH_GI_HINTS   = ("рис", "картоф", "вафл", "торт", "десерт", "булк", "слад", "сахар", "печень", "макарон", "белый хлеб")
LOW_GI_HINTS    = ("мясо", "куриц", "говядин", "рыба", "овощ", "зелень", "сыр", "яйц", "орех")
HIGH_FAT_HINTS  = ("жарен", "жирн", "масло", "майон", "бекон", "колбас", "сливоч", "крем", "фастфуд")
SALTY_HINTS     = ("солен", "колбас", "бекон", "чипс", "соевый соус")

# Напитки
SUGARY_SODA_HINTS  = ("кока", "кола", "coca", "cola", "фанта", "fanta", "спрайт", "sprite", "газиров", "лимонад")
ZERO_SODA_HINTS    = ("ноль сахара", "без сахара", "0 sugar", "zero", "sugar free", "безсахар", "лайт", "diet")
SUGARY_JUICE_HINTS = ("сок", "нектар", "фруктовый напиток", "морс")
ENERGY_DRINK_HINTS = ("энергетик", "energy drink", "red bull", "monster", "adrenaline", "burn")

# Фрукты
FRUITS_MILD_SWEET  = ("арбуз", "дын")
FRUITS_VERY_SWEET  = ("виноград", "банан", "манго", "ананас", "финик", "изюм", "сухофрукт")

# ===== helpers =====

def _is_candy_bar(text: str) -> bool:
    t = (text or "").lower()
    if "сникерс" in t or "snickers" in t:
        return True
    if "батончик" in t and ("шоколад" in t or "карамел" in t or "нуга" in t):
        return True
    if "mars" in t or "twix" in t or "bounty" in t:
        return True
    return False

def _norm(s: Any) -> str:
    return str(s or "").strip()

def _to_float(x) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", str(x))
    if not m: return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None

def _parse_gi_mark(gi_text: str) -> tuple[str | None, float | None]:
    """
    Возвращает (метка, число) где метка ∈ {'низкий','средний','высокий'} если найдена.
    """
    if not gi_text:
        return None, None
    t = gi_text.lower()
    val = _to_float(t)
    mark = None
    if "низк" in t: mark = "низкий"
    elif "средн" in t: mark = "средний"
    elif "выс" in t: mark = "высокий"
    return mark, val

def _looks_like(text: str, hints) -> bool:
    if not text:
        return False
    tl = text.lower()
    return any(h in tl for h in hints)

def _from_profile(profile: Dict[str, Any], *keys):
    if not profile:
        return ""
    for k in keys:
        for pk, pv in profile.items():
            if _norm(pk).lower() == _norm(k).lower() and _norm(pv):
                return _norm(pv)
    return ""

def _is_sugary_soda(text: str) -> bool:
    return _looks_like(text, SUGARY_SODA_HINTS) and not _looks_like(text, ZERO_SODA_HINTS)

def _is_zero_soda(text: str) -> bool:
    return _looks_like(text, SUGARY_SODA_HINTS) and _looks_like(text, ZERO_SODA_HINTS)

def _is_sugary_juice(text: str) -> bool:
    return _looks_like(text, SUGARY_JUICE_HINTS) and not _looks_like(text, ZERO_SODA_HINTS)

def _is_energy_drink(text: str) -> bool:
    return _looks_like(text, ENERGY_DRINK_HINTS)

def parse_score_comment(result_text: str):
    rl = (result_text or "").lower()
    scores, comments = [], []
    for kw, score, comment in SCORES:
        if kw in rl:
            scores.append(score)
            comments.append(comment)
    if scores:
        idx = scores.index(max(scores))  # самый строгий
        return scores[idx], comments[idx]
    return 3, "Оценка по фото рассчитана."  # по умолчанию осторожность

def _profile_based_recommendation(profile: Dict[str, Any], item_text: str, fallback_score: int) -> str:
    """Вердикт с учётом профиля для ОДНОГО продукта/названия."""
    dish_l = (item_text or "").lower()

    # особые случаи заранее
    if _is_candy_bar(dish_l):
        return "Не рекомендовано: шоколадный батончик — быстрые сахара и жиры."

    # Профиль
    diab   = _from_profile(profile, "Диабет", "Diabetes", "Тип диабета", "Diabetes Type")
    sugar  = _from_profile(profile, "Сахар", "Глюкоза", "Уровень сахара", "Glucose", "HbA1c")
    weight = _from_profile(profile, "Вес", "Weight", "Ожирение", "BMI", "ИМТ")
    ht     = _from_profile(profile, "Давление", "Гипертония", "Hypertension", "BP")
    allergies = _from_profile(profile, "Аллергии", "Allergies")

    has_diabetes = bool(diab) or "диабет" in sugar.lower()
    high_sugar   = any(t in sugar.lower() for t in ("высок", "повыш", "плох", "hba1c", "≥", ">", "↑"))
    obesity_risk = any(t in weight.lower() for t in ("ожир", "bmi", "имт", "лишн", "избыточ"))
    hypertension = any(t in ht.lower() for t in ("гиперто", "давлен", "hypert", "bp"))

    looks_high_gi  = _looks_like(dish_l, HIGH_GI_HINTS)
    looks_low_gi   = _looks_like(dish_l, LOW_GI_HINTS)
    looks_high_fat = _looks_like(dish_l, HIGH_FAT_HINTS)
    looks_salty    = _looks_like(dish_l, SALTY_HINTS)

    # Напитки
    if _is_sugary_soda(dish_l):
        if has_diabetes or high_sugar:
            return "Не рекомендовано: сладкая газировка — скачок глюкозы."
        return "Не рекомендовано: много сахара и калорий."

    if _is_zero_soda(dish_l):
        if hypertension:
            return "С осторожностью: без сахара, но кофеин/подсластители; при гипертонии ограничьте."
        return "С осторожностью: подсластители — контролируйте частоту."

    if _is_sugary_juice(dish_l):
        if has_diabetes or high_sugar:
            return "Не рекомендовано: сладкие соки повышают глюкозу."
        return "С осторожностью: много фруктозы/сахара."

    if _is_energy_drink(dish_l):
        if hypertension:
            return "Не рекомендовано: энергетики при гипертонии опасны."
        return "С осторожностью: стимуляторы — лучше избегать."

    # Фрукты (до общей логики)
    if _looks_like(dish_l, FRUITS_MILD_SWEET) or _looks_like(dish_l, FRUITS_VERY_SWEET):
        very_sweet = _looks_like(dish_l, FRUITS_VERY_SWEET)
        if has_diabetes or high_sugar:
            if very_sweet:
                return "С осторожностью: очень сладкий фрукт — порция 100–150 г, лучше после еды."
            return "С осторожностью: арбуз/дыня — порция 150–200 г, сочетать с белком/клетчаткой."
        if very_sweet:
            return "С осторожностью: очень сладкий фрукт — контролируйте порцию."
        return "С осторожностью: сладкая мякоть — небольшая порция после основного приёма пищи."

    # Общая логика
    if looks_high_gi and (has_diabetes or high_sugar):
        return "Не рекомендовано: высокий ГИ при диабете/повышенном сахаре."
    if looks_high_gi and obesity_risk:
        return "Не рекомендовано: высокоуглеводное блюдо при риске набора веса."
    if hypertension and (looks_high_fat or looks_salty):
        return "С осторожностью: при гипертонии ограничьте жир/соль."
    if allergies:
        al = allergies.lower()
        hits = [a for a in al.replace(",", " ").split() if a and a in dish_l]
        if hits:
            return f"Не рекомендовано: аллергия ({', '.join(hits)})."
    if looks_low_gi and not looks_high_gi and not looks_high_fat:
        return "Рекомендовано: белок/клетчатка, низкий ГИ — хороший выбор."

    # Фолбэк
    if fallback_score <= 2:
        return "Рекомендовано: сбалансированное блюдо."
    if fallback_score == 3:
        return "С осторожностью: следите за порцией и сочетайте с овощами/белком."
    return "Не рекомендовано: вероятно высокие сахар/жиры."

def _format_item_block(item: Dict[str, Any]) -> str:
    """
    item: {name, mass_g, kcal, protein_g, fat_g, carbs_g, gi}
    """
    def _fix_num(val, unit: str):
        if val is None or val == "":
            return "Не удалось распознать"
        if isinstance(val, (int, float)):
            if unit == "ккал":
                return str(int(round(val)))
            return f"{round(float(val), 1):g} {unit}"
        s = str(val)
        if re.search(r"\bккал\b", s.lower()) or re.search(r"\bг\b", s.lower()):
            return s
        num = _to_float(s)
        if num is None:
            return "Не удалось распознать"
        if unit == "ккал":
            return str(int(round(num)))
        return f"{round(num, 1):g} {unit}"

    name = _norm(item.get("name"))
    mass_g = _to_float(item.get("mass_g"))
    kcal = item.get("kcal")
    prt  = item.get("protein_g")
    fat  = item.get("fat_g")
    crb  = item.get("carbs_g")
    gi   = _norm(item.get("gi"))

    mass_line = "Не удалось распознать"
    if mass_g is not None:
        mass_line = f"{int(round(mass_g))} г"

    kcal_line = _fix_num(kcal, "ккал")
    prt_line  = _fix_num(prt, "г")
    fat_line  = _fix_num(fat, "г")
    crb_line  = _fix_num(crb, "г")
    gi_line   = gi if gi else "Не удалось распознать"

    return (
        f"Название блюда — {name or 'Не удалось распознать'}\n"
        f"Масса порции — {mass_line}\n"
        f"Калорийность — {kcal_line}\n"
        f"Белки — {prt_line}\n"
        f"Жиры — {fat_line}\n"
        f"Углеводы — {crb_line}\n"
        f"Гликемический индекс (ГИ) — {gi_line}"
    )

def _parse_json_items(model_text: str) -> List[Dict[str, Any]] | None:
    try:
        start = model_text.index("{")
        end = model_text.rindex("}") + 1
        chunk = model_text[start:end]
        data = json.loads(chunk)
        items = data.get("items")
        if isinstance(items, list) and items:
            return items
    except Exception:
        pass
    return None

def _dedup_and_sum(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Дедупликация по имени (lower, без двойных пробелов). Суммируем массу и макросы.
    """
    def key(name: str) -> str:
        n = (name or "").strip().lower()
        n = re.sub(r"\s+", " ", n)
        return n

    acc: Dict[str, Dict[str, Any]] = {}
    for it in items:
        k = key(_norm(it.get("name")))
        if not k:
            k = f"item_{len(acc)+1}"
        cur = acc.get(k, {"name": _norm(it.get("name") or k),
                          "mass_g": 0.0, "kcal": 0.0, "protein_g": 0.0,
                          "fat_g": 0.0, "carbs_g": 0.0, "gi": _norm(it.get("gi"))})
        # суммируем если есть числа
        for fld in ("mass_g", "kcal", "protein_g", "fat_g", "carbs_g"):
            v = _to_float(it.get(fld))
            if v is not None:
                cur[fld] = (cur.get(fld) or 0.0) + v
        # gi — если пусто в acc, берем из текущего
        if not _norm(cur.get("gi")) and _norm(it.get("gi")):
            cur["gi"] = _norm(it.get("gi"))
        acc[k] = cur
    return list(acc.values())

def _refine_item_score(name: str, gi_text: str, carbs_g: float | None, verdict: str, base: int) -> int:
    """
    Точная подстройка балла:
      - «Рекомендовано» → не выше 2
      - ГИ низкий (или <=40) и углеводы ≤5 г → 1
      - ГИ высокий (или >=70) или углеводы ≥40 г → ≥4
      - сладкие батончики → 5
    """
    tname = (name or "").lower()
    if _is_candy_bar(tname):
        return 5

    mark, gi_val = _parse_gi_mark(gi_text or "")

    score = int(base)

    # негативные триггеры первыми
    if (mark == "высокий") or (gi_val is not None and gi_val >= 70) or (carbs_g is not None and carbs_g >= 40):
        score = max(score, 4)

    # позитивные — после
    rec = (verdict or "").lower().startswith("рекомендовано")
    if rec:
        score = min(score, 2)

    if (mark == "низкий") or (gi_val is not None and gi_val <= 40):
        if carbs_g is None or carbs_g <= 5:
            score = min(score, 1)
        else:
            score = min(score, 2)

    return max(1, min(5, score))

# ===== основной пайплайн =====

def _prepare_image_url(media) -> Tuple[bool, str]:
    if isinstance(media, bytes):
        base64_image = base64.b64encode(media).decode()
        return True, f"data:image/jpeg;base64,{base64_image}"
    if isinstance(media, str):
        if media.startswith("http") or media.startswith("data:image/"):
            return True, media
        img_bytes = download_whatsapp_media(media)
        if not img_bytes:
            return False, "Ошибка: Не удалось скачать изображение из WhatsApp."
        base64_image = base64.b64encode(img_bytes).decode()
        return True, f"data:image/jpeg;base64,{base64_image}"
    return False, "Ошибка: неизвестный формат изображения"

def analyze_food_photo(media, phone: str | None = None):
    """
    Возвращает: (result_block, score, comment, recognized_bool)
      - result_block — текст с одним или несколькими блоками (по каждому продукту).
      - score — общий (наихудший по фото).
      - comment — общий вердикт.
      - recognized_bool — False, если не распознано вообще.
    """
    ok, image_url = _prepare_image_url(media)
    if not ok:
        return image_url, None, None, False

    profile = get_personal_profile(phone) if phone else None

    patient_info = ""
    if profile:
        prof_compact = "; ".join([f"{k}: {v}" for k, v in profile.items() if _norm(v)])
        patient_info = (
            "\n\nПациент (используй для оценки допустимости/рисков):\n"
            f"{prof_compact}\n"
            "Учитывай эти параметры и избегай ошибок!"
        )

    # Просим строго JSON, список items (по каждому продукту на фото)
    system_prompt = (
        "Ты опытный диетолог и эксперт по распознаванию еды и напитков по фото. "
        "Если на фото НЕСКОЛЬКО продуктов/блюд/напитков, перечисли КАЖДЫЙ отдельным элементом. "
        "ВСЕ значения — ЗА ПОРЦИЮ (НЕ на 100 г). Если масса неочевидна — оцени реалистично.\n\n"
        "Верни СТРОГО JSON (без комментариев, без пояснений) следующего вида:\n"
        "{\n"
        '  "items": [\n'
        '    {"name": "...", "mass_g": 0, "kcal": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0, "gi": "низкий/средний/высокий или число"}\n'
        "    ... (по каждому продукту/блюду/напитку)\n"
        "  ]\n"
        "}\n"
        "Если фото нечитаемо — верни: {\"items\": []}."
        + patient_info
    )

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Распознай продукты на фото и верни JSON по формату выше."},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
        "max_tokens": 600,
        "temperature": 0.2,
    }

    def _not_recognized_return():
        block = (
            "Название блюда — Не удалось распознать\n"
            "Масса порции — Не удалось распознать\n"
            "Калорийность — Не удалось распознать\n"
            "Белки — Не удалось распознать\n"
            "Жиры — Не удалось распознать\n"
            "Углеводы — Не удалось распознать\n"
            "Гликемический индекс (ГИ) — Не удалось распознать"
        )
        comment = "Не удалось корректно распознать по фото."
        return block, 3, comment, False

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=50)
        if resp.status_code != 200:
            return _not_recognized_return()

        model_text = resp.json()["choices"][0]["message"]["content"].strip()
        items = _parse_json_items(model_text)

        # Если JSON не удалось разобрать — fallback в одиночный блок
        if not items:
            single_block = _fallback_single_block(model_text)
            score_guess, _ = parse_score_comment(model_text)
            comment = _profile_based_recommendation(profile or {}, model_text, score_guess)
            not_ok = all("Не удалось распознать" in line for line in single_block.splitlines())
            if not_ok:
                return single_block, 3, "Не удалось корректно распознать по фото.", False
            # корректировка на случай низкого ГИ в тексте
            mark, val = _parse_gi_mark(model_text)
            carbs = None
            score_final = _refine_item_score("fallback", mark or "", carbs, comment, score_guess)
            if comment.lower().startswith("рекомендовано"):
                score_final = min(score_final, 2)
            return single_block, score_final, comment, True

        # Дедуп одинаковых названий
        items = _dedup_and_sum(items)

        # Преобразуем каждый item в блок и вычислим общий score/вердикт
        blocks: List[str] = []
        item_scores: List[int] = []
        any_not_recommended = False
        worst_reason = None

        for it in items:
            block = _format_item_block(it)
            blocks.append(block)

            name = _norm(it.get("name"))
            gi_text = _norm(it.get("gi"))
            carbs_g = _to_float(it.get("carbs_g"))

            # эвристический базовый score по названию
            base_score, _ = parse_score_comment(name)
            # персонализированный вердикт
            verdict = _profile_based_recommendation(profile or {}, name, base_score)

            # тонкая корректировка score с учетом ГИ/углеводов/вердикта
            score_final = _refine_item_score(name, gi_text, carbs_g, verdict, base_score)

            if verdict.lower().startswith("не рекомендовано"):
                any_not_recommended = True
                if (worst_reason is None) or score_final >= 5:
                    worst_reason = f"{verdict} — {name}"

            item_scores.append(score_final)

        result_block = "\n\n".join(blocks)

        # Общий балл и комментарий
        if any_not_recommended or (max(item_scores) >= 5):
            comment = worst_reason or "Не рекомендовано: высокий риск из-за состава/сахаров."
            total = 5
        elif max(item_scores) == 4:
            comment = "С осторожностью: есть продукты с высокой углеводной нагрузкой."
            total = 4
        elif max(item_scores) == 3:
            comment = "С осторожностью: часть продуктов может повышать сахар — контролируйте порцию."
            total = 3
        else:
            comment = "Рекомендовано: в целом выбор умеренный, контролируйте порции."
            total = max(item_scores) if item_scores else 1

        return result_block, total, comment, True

    except Exception as e:
        print("Ошибка при анализе еды:", e)
        return _not_recognized_return()

# === fallback для одиночного текста (когда модель не вернула JSON) ===
def _convert_value_for_portion(value_line: str, portion_g: float | None, unit_suffix: str) -> str:
    if not value_line:
        return ""
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", value_line)
    if not m:
        return value_line
    val = float(m.group(1).replace(",", "."))
    has_per100 = bool(re.search(r"\b(100 ?г|на 100|per 100)\b", value_line.lower()))
    if portion_g and has_per100:
        total = val * portion_g / 100.0
        if unit_suffix == "ккал":
            shown = str(int(round(total)))
        else:
            shown = f"{round(total, 1):g}"
        return f"{shown} {unit_suffix}"
    if re.search(r"\bккал\b", value_line.lower()) or re.search(r"\bг\b", value_line.lower()):
        return value_line
    return f"{val:g} {unit_suffix}"

def _parse_float(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None

def _fallback_single_block(vision_text: str) -> str:
    want = {
        "Название блюда": "",
        "Масса порции": "",
        "Калорийность": "",
        "Белки": "",
        "Жиры": "",
        "Углеводы": "",
        "Гликемический индекс (ГИ)": "",
    }
    aliases = {
        "название блюда": "Название блюда",
        "масса порции": "Масса порции",
        "вес порции": "Масса порции",
        "порция (г)": "Масса порции",
        "вес блюда": "Масса порции",
        "portion size": "Масса порции",
        "portion weight": "Масса порции",
        "калорийность": "Калорийность",
        "пищевая ценность (калорийность)": "Калорийность",
        "энергетическая ценность": "Калорийность",
        "белки": "Белки",
        "жиры": "Жиры",
        "углеводы": "Углеводы",
        "гликемический индекс (ги)": "Гликемический индекс (ГИ)",
        "гликемический индекс": "Гликемический индекс (ГИ)",
    }
    raw = dict(want)
    for raw_line in (vision_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        key = None
        for a, nk in aliases.items():
            if low.startswith(a):
                key = nk
                break
        if not key:
            continue
        val = line
        for sep in ["—", "-", ":"]:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    val = parts[1].strip()
                    break
        raw[key] = val

    portion_g = _parse_float(raw.get("Масса порции", ""))
    cal = _convert_value_for_portion(raw.get("Калорийность", ""), portion_g, "ккал")
    prt = _convert_value_for_portion(raw.get("Белки", ""), portion_g, "г")
    fat = _convert_value_for_portion(raw.get("Жиры", ""), portion_g, "г")
    crb = _convert_value_for_portion(raw.get("Углеводы", ""), portion_g, "г")

    mass_line = raw.get("Масса порции", "")
    if portion_g:
        mass_line = f"{int(round(portion_g))} г"
    elif mass_line and not re.search(r"\bг\b", mass_line.lower()):
        mnum = _parse_float(mass_line)
        if mnum is not None:
            mass_line = f"{int(round(mnum))} г"

    out = {
        "Название блюда": raw.get("Название блюда", "").strip() or "Не удалось распознать",
        "Масса порции": mass_line.strip() or "Не удалось распознать",
        "Калорийность": cal.strip() or "Не удалось распознать",
        "Белки": prt.strip() or "Не удалось распознать",
        "Жиры": fat.strip() or "Не удалось распознать",
        "Углеводы": crb.strip() or "Не удалось распознать",
        "Гликемический индекс (ГИ)": raw.get("Гликемический индекс (ГИ)", "").strip() or "Не удалось распознать",
    }

    return (
        f"Название блюда — {out['Название блюда']}\n"
        f"Масса порции — {out['Масса порции']}\n"
        f"Калорийность — {out['Калорийность']}\n"
        f"Белки — {out['Белки']}\n"
        f"Жиры — {out['Жиры']}\n"
        f"Углеводы — {out['Углеводы']}\n"
        f"Гликемический индекс (ГИ) — {out['Гликемический индекс (ГИ)']}"
    )
