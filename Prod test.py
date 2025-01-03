from playwright.sync_api import sync_playwright, expect
import random
import re
import time

def test_bima_form_manual_checkbox():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=False, args=["--ignore-certificate-errors"])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = context.new_page()

            # Переход на сайт с увеличенным таймаутом
            print("Переход на сайт...")
            page.goto("https://bima.tj/", timeout=60000, wait_until="domcontentloaded")

            # Выбор популярного элемента
            print("Выбор популярного элемента...")
            page.locator("div:nth-child(6) > .main-popular__item > .main-popular__image > .main-popular__img").click()

            # Нажатие на кнопку "Купить"
            print("Нажатие на кнопку 'Купить'...")
            page.get_by_role("link", name="Купить").first.click()

            # Заполнение полей формы
            print("Заполнение полей формы...")

            # Ожидание завершения загрузки
            print("Ожидание завершения загрузки...")
            page.wait_for_selector("div.loader", state="detached", timeout=30000)
            print("Загрузчик исчез.")

            # Дополнительная проверка на отсутствие перекрытий
            loader_locator = page.locator("div.loader")
            if loader_locator.is_visible():
                loader_locator.wait_for(state="hidden", timeout=10000)
                print("Перекрывающий загрузчик полностью исчез.")

            # Пауза для гарантированного исчезновения перекрытий
            print("Ожидание перед кликом на элемент 'Мужской'...")
            time.sleep(2)

            # Клик на элемент "Мужской" с повторной попыткой
            print("Клик на элемент 'Мужской'...")
            for attempt in range(3):
                try:
                    if page.get_by_text("Мужской").first.is_visible():
                        page.get_by_text("Мужской").first.click()
                        print("Элемент 'Мужской' успешно нажат.")
                        break
                except Exception as e:
                    print(f"Попытка {attempt + 1} не удалась: {e}")
                    time.sleep(2)

            page.get_by_placeholder("Фамилия").type("Тест", delay=random.uniform(100, 200))
            page.get_by_placeholder("Имя").type("Иест", delay=random.uniform(100, 200))
            page.get_by_placeholder("Отчество").type("Тест", delay=random.uniform(100, 200))
            page.get_by_label("Дата рождения").type("12-12-1980", delay=random.uniform(100, 200))
            page.get_by_text("Таджикистан").first.click()
            page.get_by_text("Австрия").click()
            page.get_by_placeholder("00 00 00").type("987 98 78 979", delay=random.uniform(100, 200))
            page.get_by_placeholder("E-Mail").type("Test@bima.tj", delay=random.uniform(100, 200))
            page.get_by_placeholder("Номер ИНН").type("123456789", delay=random.uniform(100, 200))
            page.get_by_text("Таджикский паспорт").first.click()
            page.get_by_text("Таджикский загран. паспорт").click()
            page.get_by_placeholder("Серия паспорта").type("12", delay=random.uniform(100, 200))
            page.get_by_placeholder("Номер паспорта").type("12345678", delay=random.uniform(100, 200))
            page.get_by_placeholder("Кем выдан паспорт").type("Test", delay=random.uniform(100, 200))
            page.get_by_label("Дата выдачи").type("20-12-2020", delay=random.uniform(100, 200))

            # Заполнение адреса
            print("Заполнение адреса...")
            page.locator("div:nth-child(4) > .policy__wrapper > div > label > .label__input > .light-select").click()
            page.get_by_text("РРП и Душанбе").first.click()
            page.locator("div").filter(has_text=re.compile(r"^Область.*$")).get_by_placeholder("Укажите город").nth(0).type("Test", delay=random.uniform(100, 200))
            page.locator("div").filter(has_text=re.compile(r"^Область.*$")).get_by_placeholder("Укажите улицу").nth(0).type("Test", delay=random.uniform(100, 200))
            page.locator("div").filter(has_text=re.compile(r"^Область.*$")).get_by_placeholder("Укажите номер дома").nth(0).type("12", delay=random.uniform(100, 200))
            page.locator("div").filter(has_text=re.compile(r"^Область.*$")).get_by_placeholder("Укажите номер квартиры").nth(0).type("1212", delay=random.uniform(100, 200))

            # Нажатие кнопки "Скопировать"
            print("Нажатие кнопки 'Скопировать'...")
            copy_button = page.get_by_role("button", name="Скопировать")
            expect(copy_button).to_be_visible(timeout=10000)
            copy_button.click()
            print("Кнопка 'Скопировать' нажата.")

            # Пауза для ручной установки галочки
            print("Пожалуйста, вручную установите галочку в пользовательском соглашении.")
            input("Нажмите Enter, чтобы продолжить...")

            # Нажатие кнопки "Перейти к оплате"
            try:
                print("Попытка активации кнопки 'Перейти к оплате'...")
                pay_button = page.get_by_role("button", name="Перейти к оплате")
                page.evaluate("button => button.removeAttribute('disabled')", pay_button.element_handle())
                page.evaluate("button => button.classList.remove('disabled')", pay_button.element_handle())
                print("Кнопка 'Перейти к оплате' активирована.")
                pay_button.click()
                print("Кнопка 'Перейти к оплате' нажата.")
            except Exception as e:
                print(f"Ошибка при активации кнопки: {e}")

            # Ожидание формы способа оплаты с выводом всех форм
            try:
                print("Ожидание появления формы способа оплаты...")
                forms = page.locator("form").all()
                print(f"Найдено {len(forms)} форм на странице.")
                for i, form in enumerate(forms):
                    print(f"Форма {i + 1}: {form.inner_html()}")
                payment_form = page.locator("form.payment-form")
                if not payment_form.is_visible():
                    alternative_form = page.locator("#pay")
                    if alternative_form.is_visible():
                        alternative_form.wait_for(state="visible", timeout=15000)
                        print("Альтернативная форма способа оплаты найдена.")
                        print("Ожидание завершено, изучите отображённую форму.")
                        input("Нажмите Enter, чтобы завершить работу...")
                    else:
                        card_form = page.get_by_text("xСпособ оплатыVisa/MasterCard")
                        card_form.wait_for(state="visible", timeout=15000)
                        print("Форма способа оплаты Visa/MasterCard найдена.")
                        print("Ожидание завершено, изучите отображённую форму.")
                        input("Нажмите Enter, чтобы завершить работу...")
                else:
                    payment_form.wait_for(state="visible", timeout=15000)
                    print("Форма способа оплаты успешно загружена.")
                    print("Ожидание завершено, изучите отображённую форму.")
                    input("Нажмите Enter, чтобы завершить работу...")
            except Exception as e:
                print(f"Форма способа оплаты не появилась: {e}")

        except Exception as e:
            print(f"Общая ошибка: {e}")
        finally:
            # Закрытие браузера
            context.close()
            browser.close()

if __name__ == "__main__":
    test_bima_form_manual_checkbox()
