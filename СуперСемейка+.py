import re
import time  # Для пауз
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto("https://test.online.bima.tj/")
        page.get_by_role("navigation").get_by_role("button").click()
        page.get_by_role("link", name="Коробочные продукты").click()
        page.locator("div:nth-child(14) > .main-popular__item > .slider-products__info > .slider-products__links > a").first.click()
        page.get_by_placeholder("Фамилия").click()
        page.get_by_placeholder("Фамилия").fill("Test")
        page.get_by_placeholder("Фамилия").press("Tab")
        page.get_by_placeholder("Имя").fill("Test")
        page.get_by_placeholder("Имя").press("Tab")
        page.get_by_placeholder("Отчество").fill("Testovich")
        page.get_by_text("Мужской").first.click()
        page.get_by_text("Женский").click()
        page.get_by_label("Дата рождения").fill("2003-06-10")
        page.get_by_text("Таджикистан").first.click()
        page.get_by_text("Азербайджан").click()
        page.get_by_placeholder("00 00 00").click()
        page.get_by_placeholder("00 00 00").fill("987 89 78 788")
        page.get_by_placeholder("00 00 00").press("Tab")
        page.get_by_placeholder("E-Mail").fill("test@bima.tj")
        page.get_by_placeholder("E-Mail").press("Tab")
        page.get_by_placeholder("Номер ИНН").fill("123456789")
        page.get_by_text("Таджикский паспорт").first.click()
        page.get_by_text("Таджикский паспорт").nth(1).click()
        page.get_by_placeholder("Серия паспорта").click()
        page.get_by_placeholder("Серия паспорта").fill("AA")
        page.get_by_placeholder("Номер паспорта").click()
        page.get_by_placeholder("Номер паспорта").fill("12345678")
        page.get_by_placeholder("Кем выдан паспорт").click()
        page.get_by_placeholder("Кем выдан паспорт").fill("Testvydan")
        page.get_by_label("Дата выдачи").fill("2024-12-12")
        page.locator("div:nth-child(4) > .policy__wrapper > div > label > .label__input > .light-select").click()
        page.get_by_text("РРП и Душанбе").click()
        page.get_by_placeholder("Укажите город").click()
        page.get_by_placeholder("Укажите город").fill("Testcity")
        page.get_by_placeholder("Укажите улицу").click()
        page.get_by_placeholder("Укажите улицу").fill("teststreet")
        page.get_by_placeholder("Укажите улицу").press("Tab")
        page.get_by_placeholder("Укажите номер дома").fill("12")
        page.get_by_placeholder("Укажите номер дома").press("Tab")
        page.get_by_placeholder("Укажите номер квартиры").fill("12")

        # Скроллинг вниз перед установкой галочки
        print("Скроллинг вниз...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Пауза для ручной установки галочки
        print("Пожалуйста, вручную установите галочку в пользовательском соглашении.")
        input("Нажмите Enter, чтобы продолжить...")

        # Нажатие кнопки "Перейти к оплате"
        print("Попытка активации кнопки 'Перейти к оплате'...")
        pay_button = page.get_by_role("button", name="Перейти к оплате")
        page.evaluate("button => button.removeAttribute('disabled')", pay_button.element_handle())
        page.evaluate("button => button.classList.remove('disabled')", pay_button.element_handle())
        print("Кнопка 'Перейти к оплате' активирована.")
        pay_button.click()
        print("Кнопка 'Перейти к оплате' нажата.")

        # Ожидание формы способа оплаты с выводом всех форм
        print("Ожидание появления формы способа оплаты...")
        time.sleep(3)  # Ожидание 3 секунды
        payment_form = page.locator("form.payment-form")
        if payment_form.is_visible():
            print("Форма способа оплаты успешно загружена.")
        else:
            print("Форма способа оплаты не появилась.")

    except Exception as e:
        print(f"Общая ошибка: {e}")

    finally:
        # Закрытие браузера
        context.close()
        browser.close()


with sync_playwright() as playwright:
    run(playwright)
