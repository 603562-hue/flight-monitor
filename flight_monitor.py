import os
import requests

API_KEY = os.environ["SEARCHAPI_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

API_URL = "https://www.searchapi.io/api/v1/search"

DEPARTURE = "SVO,DME,VKO"
ARRIVAL = "BKK,UTP"

OUTBOUND_START = "2026-12-28"
OUTBOUND_END = "2026-12-30"

RETURN_START = "2027-01-20"
RETURN_END = "2027-01-25"


def search_calendar():
    params = {
        "engine": "google_flights_calendar",
        "api_key": API_KEY,
        "flight_type": "round_trip",

        "departure_id": DEPARTURE,
        "arrival_id": ARRIVAL,

        "outbound_date": OUTBOUND_START,
        "outbound_date_start": OUTBOUND_START,
        "outbound_date_end": OUTBOUND_END,

        "return_date": RETURN_START,
        "return_date_start": RETURN_START,
        "return_date_end": RETURN_END,

        "travel_class": "economy",
        "stops": "one_stop_or_fewer",

        "adults": "1",
        "children": "0",
        "infants_in_seat": "0",
        "infants_on_lap": "0",

        "carry_on_bags": "0",
        "checked_bags": "0",

        "currency": "RUB",
        "gl": "ru",
        "hl": "ru",
    }

    response = requests.get(API_URL, params=params, timeout=90)

    print("HTTP:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        return []

    data = response.json()
    return data.get("calendar", [])


def search_flights(departure_date, return_date):
    params = {
        "engine": "google_flights",
        "api_key": API_KEY,
        "flight_type": "round_trip",

        "departure_id": DEPARTURE,
        "arrival_id": ARRIVAL,

        "outbound_date": departure_date,
        "return_date": return_date,

        "travel_class": "economy",
        "stops": "one_stop_or_fewer",
        "sort_by": "price",
        "show_cheapest_flights": "true",
        "expanded_search": "true",

        "adults": "1",
        "children": "0",
        "infants_in_seat": "0",
        "infants_on_lap": "0",

        "carry_on_bags": "0",
        "checked_bags": "0",

        "currency": "RUB",
        "gl": "ru",
        "hl": "ru",
    }

    response = requests.get(API_URL, params=params, timeout=90)

    if response.status_code != 200:
        print("Flight search error:", response.text)
        return {}

    return response.json()


def telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )


def flight_summary(flight):
    lines = []

    for segment in flight.get("flights", []):
        dep = segment.get("departure_airport", {})
        arr = segment.get("arrival_airport", {})

        airline = segment.get("airline", "")
        number = segment.get("flight_number", "")

        lines.append(
            f"{airline} {number}: "
            f"{dep.get('id')} {dep.get('time')} -> "
            f"{arr.get('id')} {arr.get('time')}"
        )

    layovers = flight.get("layovers", [])

    if layovers:
        for layover in layovers:
            lines.append(
                f"Пересадка: {layover.get('name')} "
                f"{layover.get('duration')} мин."
            )

    return "\n".join(lines)


def main():
    print("Searching date combinations...")

    calendar = search_calendar()

    if not calendar:
        telegram(
            "Flight Monitor\n\n"
            "Не удалось получить календарь цен SearchApi."
        )
        return

    valid = []

    for item in calendar:
        if item.get("has_no_flights"):
            continue

        price = item.get("price")

        if price is None:
            continue

        valid.append(item)

    valid.sort(key=lambda x: x["price"])

    if not valid:
        telegram(
            "Flight Monitor\n\n"
            "На заданные даты подходящих вариантов не найдено."
        )
        return

    # Проверяем только 3 самых дешевых комбинации.
    # Это экономит бесплатные API-запросы.
    best_dates = valid[:3]

    results = []

    for item in best_dates:
        departure = item["departure"]
        return_date = item["return"]

        print(
            "Checking:",
            departure,
            return_date,
            item["price"]
        )

        data = search_flights(departure, return_date)

        flights = data.get("best_flights", [])

        if not flights:
            flights = data.get("other_flights", [])

        if flights:
            flights.sort(key=lambda x: x.get("price", 10**9))
            results.append(
                (departure, return_date, flights[0])
            )

    results.sort(key=lambda x: x[2].get("price", 10**9))

    message = "✈️ МОСКВА → БАНГКОК\n\n"
    message += "Проверено:\n"
    message += "28–30.12.2026 → 20–25.01.2027\n"
    message += "1 взрослый • Economy • максимум 1 пересадка\n"
    message += "Без багажа\n\n"

    if not results:
        message += "Конкретные рейсы получить не удалось."
        telegram(message)
        return

    for departure, return_date, flight in results[:3]:
        price = flight.get("price", "—")

        message += (
            f"💰 {price:,} ₽\n"
            f"📅 {departure} → {return_date}\n"
        ).replace(",", " ")

        message += flight_summary(flight)
        message += "\n\n"

    message += (
        "Источник: Google Flights через SearchApi.\n"
        "Следующая проверка покажет новую цену."
    )

    telegram(message)


if __name__ == "__main__":
    main()
