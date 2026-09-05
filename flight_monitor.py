import os
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

URL = "https://www.airarabia.com/en/plan/reservation/book-flight"


def send_telegram(message):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        },
        timeout=30,
    )
    response.raise_for_status()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
        )

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )

        print("Opening Air Arabia...")
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)

        print("URL:", page.url)
        print("TITLE:", page.title())

        # Return / туда-обратно
        return_option = page.get_by_text("Return", exact=True)

        if return_option.count() > 0:
            return_option.first.click()
            print("Return selected")
        else:
            print("Return option not found")

        # Показываем доступные input'ы для диагностики
        inputs = page.locator("input")
        print("INPUT COUNT:", inputs.count())

        for i in range(inputs.count()):
            try:
                element = inputs.nth(i)
                print(
                    "INPUT",
                    i,
                    "placeholder=",
                    element.get_attribute("placeholder"),
                    "aria-label=",
                    element.get_attribute("aria-label"),
                )
            except Exception:
                pass

        # Показываем кнопки
        buttons = page.locator("button")
        print("BUTTON COUNT:", buttons.count())

        for i in range(min(buttons.count(), 30)):
            try:
                print(
                    "BUTTON",
                    i,
                    "TEXT=",
                    buttons.nth(i).inner_text()
                )
            except Exception:
                pass

        send_telegram(
            "✈️ FLIGHT MONITOR\n\n"
            "Реальный тест Air Arabia запущен.\n\n"
            "Браузер открыл форму бронирования.\n"
            "Форма Return обработана.\n\n"
            "Следующий результат будет содержать "
            "точные элементы формы, которые видит "
            "автоматический браузер."
        )

        browser.close()


if __name__ == "__main__":
    main()
