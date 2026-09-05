import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime


AIR_ARABIA_URL = (
    "https://flights.airarabia.com/en-ru/flights-from-moscow-to-bangkok"
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def get_air_arabia_page():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    }

    response = requests.get(
        AIR_ARABIA_URL,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    return response.text


def extract_fares(html):
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(" ", strip=True)

    results = []

    # Round-trip offers such as:
    # Moscow (DME)to Bangkok (BKK)
    # 13/12/2026 - 23/01/2027
    # Round-trip / Economy
    # From RUB 66,007

    pattern = re.compile(
        r"Moscow\s*\(([^)]+)\)\s*to\s*Bangkok\s*\(([^)]+)\)"
        r".{0,500}?"
        r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})"
        r".{0,300}?"
        r"Round-trip"
        r".{0,150}?"
        r"From\s+RUB\s*([\d\s,]+)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(text):
        origin_airport = match.group(1)
        destination = match.group(2)
        departure = match.group(3)
        return_date = match.group(4)
        price_text = match.group(5)

        price = int(
            re.sub(r"[^\d]", "", price_text)
        )

        results.append(
            {
                "origin": origin_airport,
                "destination": destination,
                "departure": departure,
                "return": return_date,
                "price": price,
            }
        )

    return results


def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

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
    print("Flight Monitor started")

    html = get_air_arabia_page()

    print(f"Downloaded Air Arabia page: {len(html)} bytes")

    fares = extract_fares(html)

    print(f"Round-trip fares found: {len(fares)}")

    if not fares:
        message = (
            "⚠️ Flight Monitor\n\n"
            "Air Arabia page was opened successfully, "
            "but no round-trip fares could be extracted.\n\n"
            f"Checked: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        send_telegram(message)
        return

    fares.sort(key=lambda x: x["price"])

    lines = [
        "✈️ Flight Monitor — Air Arabia",
        "",
        "Москва → Бангкок",
        "Официальная страница Air Arabia",
        "",
        "Найденные опубликованные варианты:",
        "",
    ]

    for fare in fares[:10]:
        lines.append(
            f"{fare['departure']} → {fare['return']}  "
            f"— {fare['price']:,} ₽".replace(",", " ")
        )

    lines.extend(
        [
            "",
            f"Всего найдено: {len(fares)}",
            "",
            f"Проверено: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        ]
    )

    send_telegram("\n".join(lines))

    print("Telegram notification sent")


if __name__ == "__main__":
    main()
