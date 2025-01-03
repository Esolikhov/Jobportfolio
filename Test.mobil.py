import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://test.online.bima.tj/")

    # Действия на странице
    page.locator(
        "div:nth-child(7) > .main-popular__item > .main-popular__info > .main-popular__links > a").first.click()
    page.get_by_placeholder("Фамилия").click()
    page.get_by_placeholder("Фамилия").fill("Тест")
    page.get_by_placeholder("Фамилия").press("Tab")
    page.get_by_placeholder("Имя").fill("Тест")
    page.get_by_placeholder("Имя").press("Tab")
    page.get_by_placeholder("Отчество").fill("Тест")
    page.get_by_text("Мужской").first.click()
    page.get_by_text("Мужской").nth(1).click()
    page.get_by_label("Дата рождения").fill("2006-12-08")
    page.get_by_text("Таджикистан").first.click()
    page.get_by_text("Азербайджан").click()
    page.get_by_placeholder("00 00 00").click()
    page.get_by_placeholder("00 00 00").fill("997 98 79 799")
    page.get_by_placeholder("00 00 00").press("Tab")
    page.get_by_placeholder("E-Mail").fill("Test@bima.tj")
    page.get_by_placeholder("E-Mail").press("Tab")
    page.get_by_placeholder("Номер ИНН").fill("123456789")
    page.get_by_text("Таджикский паспорт").first.click()
    page.get_by_text("Иностранный паспорт").click()
    page.get_by_placeholder("Серия паспорта").click()
    page.get_by_placeholder("Серия паспорта").fill("A")
    page.get_by_placeholder("Номер паспорта").click()
    page.get_by_placeholder("Номер паспорта").fill("12345678")
    page.get_by_placeholder("Кем выдан паспорт").click()
    page.get_by_placeholder("Кем выдан паспорт").fill("Test")
    page.get_by_label("Дата выдачи").fill("2024-12-04")
    page.locator("div:nth-child(4) > .policy__wrapper > div > label > .label__input > .light-select").click()
    page.get_by_text("СОГД").click()
    page.get_by_placeholder("Укажите город").click()
    page.get_by_placeholder("Укажите город").fill("Test City")
    page.get_by_placeholder("Укажите улицу").click()
    page.get_by_placeholder("Укажите улицу").fill("Test street")
    page.get_by_placeholder("Укажите номер дома").click()
    page.get_by_placeholder("Укажите номер дома").fill("12")
    page.get_by_placeholder("Укажите номер дома").press("Tab")
    page.get_by_placeholder("Укажите номер квартиры").fill("123")
    page.locator("div:nth-child(6) > div > label > .label__input > .light-select").click()
    page.get_by_text("Телефоны").click()
    page.locator(".column__wrapper-3 > .label > .label__input > .light-select").click()
    page.get_by_placeholder(" Модель").click()
    page.get_by_placeholder(" Модель").fill("13")
    page.get_by_placeholder(" IMEI/Серийный номер").click()
    page.get_by_placeholder(" IMEI/Серийный номер").fill("GJHGHJGt676756767")
    page.get_by_label("Дата покупки").fill("2024-12-05")
    page.get_by_placeholder(" Стоимость").click()
    page.get_by_placeholder(" Стоимость").fill("100000")

    # Скроллинг вниз и ручная установка галочки
    print("Скроллинг вниз...")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
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

    # Дополнительные шаги после "Перейти к оплате"
    try:
        page.get_by_text("xСпособ оплатыVisa/MasterCard").click()
        page.locator("div").filter(has_text="xСпособ оплатыVisa/MasterCard").nth(2).click()
        page.locator("label").filter(has_text="Visa/MasterCard/МИР").click()
        page.locator("#pay").get_by_role("button", name="Перейти к оплате").click()
        print("Процесс оплаты завершен.")
    except Exception as e:
        print(f"Ошибка во время оплаты: {e}")

    # Закрытие контекста и браузера
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
