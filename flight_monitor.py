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
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )

        print("Opening Air Arabia...")
        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=90000,
        )

        page.wait_for_timeout(10000)

        print("PAGE URL:", page.url)
        print("PAGE TITLE:", page.title())

        messages = []

        frames = page.frames

        print("FRAME COUNT:", len(frames))

        for frame_index, frame in enumerate(frames):
            print("")
            print("===== FRAME", frame_index, "=====")
            print("FRAME URL:", frame.url)

            try:
                inputs = frame.locator("input")
                buttons = frame.locator("button")

                input_count = inputs.count()
                button_count = buttons.count()

                print("INPUT COUNT:", input_count)
                print("BUTTON COUNT:", button_count)

                messages.append(
                    f"FRAME {frame_index}\n"
                    f"URL: {frame.url[:180]}\n"
                    f"INPUTS: {input_count}\n"
                    f"BUTTONS: {button_count}"
                )

                for i in range(min(input_count, 20)):
                    element = inputs.nth(i)

                    info = (
                        f"INPUT {i}: "
                        f"type={element.get_attribute('type')} | "
                        f"name={element.get_attribute('name')} | "
                        f"id={element.get_attribute('id')} | "
                        f"placeholder={element.get_attribute('placeholder')} | "
                        f"aria={element.get_attribute('aria-label')}"
                    )

                    print(info)
                    messages.append(info)

                for i in range(min(button_count, 20)):
                    element = buttons.nth(i)

                    try:
                        text = element.inner_text().strip()
                    except Exception:
                        text = ""

                    info = (
                        f"BUTTON {i}: "
                        f"text={text[:100]} | "
                        f"aria={element.get_attribute('aria-label')} | "
                        f"type={element.get_attribute('type')}"
                    )

                    print(info)
                    messages.append(info)

            except Exception as e:
                print("FRAME ERROR:", str(e))
                messages.append(
                    f"FRAME {frame_index} ERROR: {str(e)[:200]}"
                )

        diagnostic = "\n".join(messages)

        # Telegram has a 4096 character limit.
        diagnostic = diagnostic[:3800]

        send_telegram(
            "✈️ FLIGHT MONITOR\n\n"
            "Диагностика формы Air Arabia.\n\n"
            f"{diagnostic}"
        )

        browser.close()


if __name__ == "__main__":
    main()
