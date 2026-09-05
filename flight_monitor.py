import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime


TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Наши реальные даты поездки
DEPARTURE_DATES = [
    "28/12/2026",
    "29/12/2026",
    "30/12/2026",
]

RETURN_DATES = [
    "20/01/2027",
    "21/01/2027",
    "22/01/2027",
    "23/01/2027",
    "24/01/2027",
    "25/01/2027",
]

# Города назначения
DESTINATIONS = {
    "Bangkok": "BKK",
    "U-Tapao": "UTP",
}

# Страница Air Arabia с опубликованными предложениями
AIR_ARABIA_BKK_URL = (
    "https://flights.airarabia.com/en-ru/"
    "flights-from-moscow-to-bangkok"
)


def get_page(url):
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
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    return response.text


def extract_round_trip_fares(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    results = []

    pattern = re.compile(
        r"Moscow\s*\(([^)]+)\)\s*to\s*"
        r"Bangkok\s*\(([^)]+)\)"
        r".{0,500}?"
        r"(\d{2}/\d{2}/\d{4})\s*-\s*"
        r"(\d{2}/\d{2}/\d{4})"
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


def filter_our_dates(fares):
    selected = []

    for fare in fares:
        if (
            fare["departure"] in DEPARTURE_DATES
            and fare["return"] in RETURN_DATES
        ):
            selected.append(fare)

    return selected


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

    print("Target departure dates:")
    for date in DEPARTURE_DATES:
        print(f"  {date}")

    print("Target return dates:")
    for date in RETURN_DATES:
        print(f"  {date}")

    html = get_page(AIR_ARABIA_BKK_URL)

    print(
        f"Downloaded Air Arabia page: "
        f"{len(html)} bytes"
    )

    all_fares = extract_round_trip_fares(html)

    print(
        f"Round-trip fares found on page: "
        f"{len(all_fares)}"
    )

    selected = filter_our_dates(all_fares)

    print(
        f"Fares matching our exact dates: "
        f"{len(selected)}"
    )

    if selected:
        selected.sort(key=lambda x: x["price"])

        lines = [
            "✈️ FLIGHT MONITOR",
            "",
            "Москва → Бангкок",
            "Air Arabia",
            "",
            "Подходящие даты:",
            "",
        ]

        for fare in selected:
            lines.append(
                f"{fare['departure']} → "
                f"{fare['return']} — "
                f"{fare['price']:,} ₽".replace(",", " ")
            )

        lines.extend(
            [
                "",
                f"Найдено: {len(selected)}",
                "",
                "⚠️ Это опубликованные тарифы Air Arabia.",
                "Перед покупкой цена может измениться.",
                "",
                "Проверено:",
                datetime.now().strftime(
                    "%d.%m.%Y %H:%M"
                ),
            ]
        )

        send_telegram("\n".join(lines))

    else:
        message = (
            "🔎 FLIGHT MONITOR\n\n"
            "Air Arabia открылась успешно, "
            "но опубликованного тарифа на наши "
            "точные даты сейчас не найдено.\n\n"
            "Вылет: 28–30.12.2026\n"
            "Возврат: 20–25.01.2027\n\n"
            "Проверено: "
            + datetime.now().strftime(
                "%d.%m.%Y %H:%M"
            )
        )

        send_telegram(message)


if __name__ == "__main__":
    main()
