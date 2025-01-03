import re
from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://test.online.bima.tj/")
    page.locator("div:nth-child(8) > .main-popular__item > .main-popular__info > .main-popular__links > a").first.click()
    page.get_by_placeholder("Фамилия").first.click()
    page.get_by_placeholder("Фамилия").first.fill("Test")
    page.get_by_placeholder("Фамилия").first.press("Tab")
    page.get_by_placeholder("Имя").first.fill("Test")
    page.get_by_placeholder("Имя").first.press("Tab")
    page.get_by_placeholder("Отчество").first.fill("Test")
    page.get_by_text("Мужской").first.click()
    page.get_by_text("Женский").first.click()
    page.get_by_label("Дата рождения").first.fill("2004-05-18")
    page.get_by_text("Таджикистан").first.click()
    page.get_by_text("Азербайджан").click()
    page.get_by_placeholder("00 00 00").click()
    page.get_by_placeholder("00 00 00").fill("987 97 98 789")
    page.get_by_placeholder("00 00 00").press("Tab")
    page.get_by_placeholder("E-Mail").fill("Test@bima.tj")
    page.get_by_placeholder("Номер ИНН").click()
    page.get_by_placeholder("Номер ИНН").fill("123456789")
    page.get_by_text("Таджикский паспорт").first.click()
    page.get_by_text("Таджикский загран. паспорт").click()
    page.get_by_placeholder("Серия паспорта").click()
    page.get_by_placeholder("Серия паспорта").fill("A")
    page.get_by_placeholder("Номер паспорта").click()
    page.get_by_placeholder("Номер паспорта").fill("12345678")
    page.get_by_placeholder("Кем выдан паспорт").click()
    page.get_by_placeholder("Кем выдан паспорт").fill("Testvydan")
    page.get_by_label("Дата выдачи").fill("2024-12-14")
    page.locator("div:nth-child(4) > .policy__wrapper > div > label > .label__input > .light-select").click()
    page.get_by_text("Хатлон").first.click()
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГород$")).get_by_placeholder("Укажите город").click()
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГород$")).get_by_placeholder("Укажите город").fill("Shahrituz")
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГородУлицаДомКвартираСкопировать$")).get_by_placeholder("Укажите улицу").click()
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГородУлицаДомКвартираСкопировать$")).get_by_placeholder("Укажите улицу").fill("Teststreet")
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГородУлицаДомКвартираСкопировать$")).get_by_placeholder("Укажите номер дома").click()
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГородУлицаДомКвартираСкопировать$")).get_by_placeholder("Укажите номер дома").fill("12")
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГородУлицаДомКвартираСкопировать$")).get_by_placeholder("Укажите номер квартиры").click()
    page.locator("div").filter(has_text=re.compile(r"^ОбластьХатлонРРП и ДушанбеСОГДХатлонГБАОГородУлицаДомКвартираСкопировать$")).get_by_placeholder("Укажите номер квартиры").fill("1212")
    page.get_by_role("button", name="Скопировать").click()
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
