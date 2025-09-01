import re
import time  # Для пауз
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://test.online.bima.tj/")
    time.sleep(0.5)  # Пауза в 0.5 секунды

    page.get_by_role("navigation").get_by_role("button").click()
    time.sleep(0.5)  # Пауза после клика
    page.get_by_role("link", name="Автострахование").click()
    time.sleep(0.5)  # Пауза перед выбором элемента

    locator = page.locator("a:nth-child(4) > .auto-card__wrapper > .slider-products__links > a").first
    locator.scroll_into_view_if_needed()
    time.sleep(0.5)  # Пауза, чтобы увидеть элемент
    locator.click()  # Клик по элементу
    time.sleep(0.5)

    page.locator(".ymaps-2-1-79-events-pane").click()
    time.sleep(0.5)  # Пауза перед следующей операцией
    page.get_by_role("button", name="Оставить заявку").click()
    time.sleep(0.5)

    page.get_by_placeholder("(992) 99-999-").click()
    time.sleep(0.5)
    page.get_by_placeholder("(992) 99-999-").fill("(992) 68-768-76878")
    time.sleep(0.5)
    page.get_by_role("button", name="Отправить").click()
    time.sleep(0.5)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
