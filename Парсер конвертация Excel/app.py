import pdfplumber
import pandas as pd
import re
import gradio as gr


# Путь к файлу для сохранения результата
def process_pdf(pdf_path):
    excel_path = pdf_path.replace('.pdf', '.xlsx')

    # Списки для хранения данных
    codes_top = []  # Код верх (бывший Артикул)
    codes_bottom = []  # Код низ (бывший Код)
    items = []  # Предмет (название)
    art_numbers = []  # Номер артикула
    sizes = []  # Размеры
    colors = []  # Цвета
    has_at = []  # Признак @
    has_background_color = []  # Признак background-color

    def find_long_number(text):
        """Найти первый номер длиннее 4 цифр"""
        matches = re.findall(r'\d{5,}', text)
        return matches[0] if matches else None

    def find_size(text):
        """Найти размер с точным соответствием"""
        sizes_list = ['XXS', '3XS', '4XS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '3XL', '4XL']
        text_upper = text.upper()
        for size in sizes_list:
            if re.search(r'\b{}\b'.format(size), text_upper):
                return size
        return None

    def find_item_name(text):
        """Извлекает название предмета"""
        item_list = [
            'КУРТКА', 'ДЖЕМПЕР', 'РУБАШКА', 'БРЮКИ', 'ЮБКА', 'ФУТБОЛКА', 'ШОРТЫ', 'ПАЛЬТО', 'ГЕТРЫ',
            'СВИТЕР', 'ТОЛСТОВКА', 'БЛУЗКА', 'ВЕТРОВКА', 'КУРТКА УТЕПЛЕННАЯ', 'КУРТКА СПОРТИВНАЯ',
            'СУМКА', 'РЮКЗАК', 'ШАПКА', 'БЕЙСБОЛКА', 'ПЕРЧАТКИ', 'ЖИЛЕТ', 'МАНИШКА', 'ПОЛО', 'ФОРМА',
            'СВИТЕР ТРЕНИРОВОЧНЫЙ', 'ТАЙТСЫ', 'ТОП', 'МЯЧ', 'НАКОЛЕННИКИ'
        ]
        for item in item_list:
            match = re.search(rf'({item}\s+[A-ZА-ЯЁ]+)', text.upper())
            if match:
                return match.group(0)
        return ''

    def find_colors(text):
        """Извлекает цвета из текста"""
        color_matches = []
        colors_list = [
            'ЧЕРНЫЙ', 'БЕЛЫЙ', 'КРАСНЫЙ', 'ЖЕЛТЫЙ', 'СИНИЙ', 'ЗЕЛЕНЫЙ', 'ОРАНЖЕВЫЙ', 'ФИОЛЕТОВЫЙ', 'РОЗОВЫЙ', 'СЕРЫЙ',
            'КОРИЧНЕВЫЙ',
            'АНТРАЦИТ', 'ГОЛУБОЙ', 'НЕОН-ГОЛУБОЙ', 'НЕОН-ЗЕЛЕНЫЙ', 'НЕОН-ЖЕЛТЫЙ', 'НЕОН-ОРАНЖЕВЫЙ', 'ГРАНАТОВЫЙ',
            'БИРЮЗОВЫЙ'
        ]
        for color in colors_list:
            match = re.search(rf'ЦВЕТ:\s+.*?{color}', text.upper())
            if match:
                color_matches.append(color)
        return ', '.join(color_matches) if color_matches else ''

    def clean_code_bottom(code):
        """Удаляет лишние цифры, например, '1 3 14' или последовательности 1 2 3 4 5 6 7 8 9 справа от кода"""
        return re.sub(r'\s+[\d\s]+$', '', code)

    # Открываем PDF файл
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Извлекаем текст со страницы с сохранением форматирования
            text = page.extract_text(layout=True)
            if not text:
                continue  # Если текст пустой, переходим к следующей странице

            # Объединяем весь текст в одну строку
            text = ' '.join(text.splitlines())

            # Переменные для сбора данных
            code_top = None
            code_bottom = None
            item = None
            art_number = None
            size = None
            color = None

            # Ищем коды верх и низ
            code_top_match = re.search(r'\(01\)\s*(\d+@?|\d+)', text)
            code_bottom_match = re.search(r'\(21\)\s*([^\n\r]*)', text)

            if code_top_match:
                code_top = code_top_match.group(1)
            if code_bottom_match:
                code_bottom = clean_code_bottom(code_bottom_match.group(1))

            # Извлекаем номер артикула и размер
            art_number = find_long_number(text)
            size = find_size(text)

            # Извлекаем название предмета
            item = find_item_name(text)

            # Извлекаем цвета
            color = find_colors(text)

            # Проверяем наличие background-color
            background_color = 'Да' if re.search(r'background-color\s*=\s*\"0xFFE6E6E6\"', text) else 'Нет'

            # Добавляем данные в списки
            if code_top and code_bottom:
                codes_top.append(code_top.replace('@', ''))
                codes_bottom.append(code_bottom)
                items.append(item if item else '')
                art_numbers.append(art_number if art_number else '')
                sizes.append(size if size else '')
                colors.append(color if color else '')
                has_at.append('Да' if '@' in str(code_top) else 'Нет')
                has_background_color.append(background_color)

    # Создаем DataFrame
    df = pd.DataFrame({
        'Код верх': codes_top,
        'Код низ': codes_bottom,
        'Предмет': items,
        'АРТ': art_numbers,
        'Размер': sizes,
        'Цвет': colors,
        'Наличие @': has_at,
        'Наличие background-color': has_background_color
    })

    # Сохраняем в Excel
    df.to_excel(excel_path, index=False)

    return excel_path


# Интерфейс Gradio
def interface(pdf_file):
    try:
        result = process_pdf(pdf_file.name)  # Обрабатываем файл
        return result  # Возвращаем путь к обработанному файлу
    except Exception as e:
        return f"Ошибка в интерфейсе: {str(e)}"


# Запуск интерфейса Gradio
if __name__ == "__main__":
    gr.Interface(
        fn=interface,
        inputs=gr.File(label="Загрузите PDF-файл"),
        outputs=gr.File(label="Скачать обработанный файл"),
        title="Обработка PDF в Excel",
        description="Загрузите PDF-файл, и обработанный Excel-файл будет автоматически загружен на ваш ПК."
    ).launch(share=True)
