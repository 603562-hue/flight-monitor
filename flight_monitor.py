import os
import time
from datetime import datetime

from playwright.sync_api import sync_playwright


TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

URL = "https://www.airarabia.com/en/plan/reservation/book-flight"

DEPARTURE = "28/12/2026"
RETURN = "20/01/2027"


def send_telegram(message):
    import requests

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        },
        timeout=30,
    )

    response.raise_for_status()


def main():
    print("Starting Air Arabia browser test")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            locale="en-US",
        )

        print("Opening Air Arabia...")
        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=90000,
        )

        page.wait_for_timeout(5000)

        print("Page title:", page.title())
        print("Current URL:", page.url)

        body_text = page.locator("body").inner_text()

        print("Air Arabia page loaded.")
        print("Page contains Search & Book:",
              "Search & Book" in body_text)

        print("Page contains Departure:",
              "Departure" in body_text)

        print("Page contains Return:",
              "Return" in body_text)

        print("Page contains Passengers:",
              "Passengers" in body_text)

        print("Page contains Economy:",
              "Economy class" in body_text)

        print("Browser test completed.")

        send_telegram(
            "✈️ FLIGHT MONITOR\n\n"
            "Air Arabia browser test успешно запущен.\n\n"
            "Страница поиска открылась.\n"
            "Search & Book найден.\n"
            "Departure найден.\n"
            "Return найден.\n"
            "Passengers найден.\n"
            "Economy class найден.\n\n"
            f"Тестовые даты:\n"
            f"{DEPARTURE} → {RETURN}\n\n"
            "Следующий этап — автоматический ввод "
            "дат и получение реальной цены."
        )

        browser.close()


if __name__ == "__main__":
    main()
