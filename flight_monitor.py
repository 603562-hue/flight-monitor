import os
import requests

API_KEY = os.environ["SEARCHAPI_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

API_URL = "https://www.searchapi.io/api/v1/search"

DEPARTURE = "SVO,DME,VKO"
ARRIVAL = "BKK,UTP"

OUTBOUND_DATES = [
    "2026-12-28",
    "2026-12-29",
    "2026-12-30",
]

RETURN_DATES = [
    "2027-01-20",
    "2027-01-21",
    "2027-01-22",
    "2027-01-23",
    "2027-01-24",
    "2027-01-25",
]

AIRLINES = {
    "G9": "Air Arabia",
    "CA": "Air China",
    "WY": "Oman Air",
}


def api_request(params):
    response = requests.get(
        API_URL,
        params=params,
        timeout=90
    )

    print("HTTP:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        return {}

    return response.json()


def search_flights(outbound, return_date, airline=None):

    params = {
        "engine": "google_flights",
        "api_key": API_KEY,

        "flight_type": "round_trip",

        "departure_id": DEPARTURE,
        "arrival_id": ARRIVAL,

        "outbound_date": outbound,
        "return_date": return_date,

        "travel_class": "economy",

        "stops": "one_stop_or_fewer",

        "sort_by": "price",

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

    if airline:
        params["airline"] = airline

    return api_request(params)


def extract_flights(data):

    flights = data.get("best_flights", [])

    if not flights:
        flights = data.get("other_flights", [])

    flights = [
        f for f in flights
        if f.get("price") is not None
    ]

    flights.sort(
        key=lambda x: x.get("price", 999999999)
    )

    return flights


def flight_text(flight):

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

    for layover in flight.get("layovers", []):

        name = layover.get("name", "")
        duration = layover.get("duration", "")

        lines.append(
            f"Пересадка: {name} {duration} мин."
        )

    return "\n".join(lines)


def telegram(message):

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )


def main():

    print("START FLIGHT MONITOR")

    all_results = []

    # Общий поиск
    print("Searching all airlines...")

    for outbound in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            print(
                "ALL:",
                outbound,
                return_date
            )

            data = search_flights(
                outbound,
                return_date
            )

            flights = extract_flights(data)

            if flights:

                all_results.append({
                    "type": "ALL",
                    "airline": "Все авиакомпании",
                    "outbound": outbound,
                    "return": return_date,
                    "flight": flights[0],
                })

    # Отдельный поиск Air Arabia / Air China / Oman Air
    airline_results = []

    for code, name in AIRLINES.items():

        print("AIRLINE:", name)

        for outbound in OUTBOUND_DATES:

            for return_date in RETURN_DATES:

                print(
                    name,
                    outbound,
                    return_date
                )

                data = search_flights(
                    outbound,
                    return_date,
                    code
                )

                flights = extract_flights(data)

                if flights:

                    airline_results.append({
                        "type": code,
                        "airline": name,
                        "outbound": outbound,
                        "return": return_date,
                        "flight": flights[0],
                    })

    # Сортировка
    all_results.sort(
        key=lambda x: x["flight"].get("price", 999999999)
    )

    airline_results.sort(
        key=lambda x: x["flight"].get("price", 999999999)
    )

    message = (
        "✈️ МОСКВА → БАНГКОК\n\n"
        "Даты вылета: 28–30.12.2026\n"
        "Возврат: 20–25.01.2027\n"
        "1 взрослый • Economy\n"
        "Максимум 1 пересадка\n"
        "Без багажа\n\n"
    )

    # Самые дешевые общие варианты
    message += "🏆 САМЫЕ ДЕШЕВЫЕ ВАРИАНТЫ\n\n"

    for item in all_results[:5]:

        price = item["flight"].get("price", 0)

        message += (
            f"💰 {price:,} ₽\n"
            f"📅 {item['outbound']} → {item['return']}\n"
            f"{flight_text(item['flight'])}\n\n"
        )

    # Лучшие среди конкретных авиакомпаний
    message += "✈️ КОНКРЕТНЫЕ АВИАКОМПАНИИ\n\n"

    for code, name in AIRLINES.items():

        matches = [
            x for x in airline_results
            if x["type"] == code
        ]

        if not matches:

            message += (
                f"{name}: вариантов не найдено\n\n"
            )

            continue

        best = matches[0]

        price = best["flight"].get("price", 0)

        message += (
            f"🔹 {name}\n"
            f"💰 {price:,} ₽\n"
            f"📅 {best['outbound']} → {best['return']}\n"
            f"{flight_text(best['flight'])}\n\n"
        )

    message += (
        "Источник: Google Flights через SearchApi."
    )

    telegram(message)

    print("DONE")


if __name__ == "__main__":
    main()
