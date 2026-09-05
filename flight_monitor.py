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
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )

        print("Opening Air Arabia...")
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(15000)

        print("TITLE:", page.title())
        print("URL:", page.url)

        # Получаем весь видимый текст страницы
        text = page.locator("body").inner_text()

        print("BODY TEXT LENGTH:", len(text))
        print(text[:5000])

        # Ищем элементы по тексту
        checks = [
            "One way",
            "Return",
            "Departure",
            "Passengers",
            "Economy class",
            "Search & Book",
        ]

        result = []

        for item in checks:
            found = item in text
            line = f"{item}: {'FOUND' if found else 'NOT FOUND'}"
            print(line)
            result.append(line)

        # Ищем web components
        components = page.locator("*")
        count = components.count()

        print("TOTAL ELEMENTS:", count)

        interesting = []

        for i in range(min(count, 3000)):
            try:
                element = components.nth(i)
                tag = element.evaluate("(e) => e.tagName")
                shadow = element.evaluate(
                    "(e) => e.shadowRoot ? true : false"
                )

                if shadow:
                    line = f"SHADOW: {tag}"
                    print(line)
                    interesting.append(line)

            except Exception:
                pass

        message = (
            "✈️ AIR ARABIA DIAGNOSTICS\n\n"
            + "\n".join(result)
            + "\n\n"
            + "\n".join(interesting[:30])
        )

        send_telegram(message[:3900])

        browser.close()


if __name__ == "__main__":
    main()
