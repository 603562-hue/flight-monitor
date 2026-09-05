import os
import requests
from fast_flights import FlightQuery, Passengers, create_query, get_flights


TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


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


MOSCOW_AIRPORTS = [
    "SVO",
    "DME",
    "VKO",
]


DESTINATIONS = {
    "BKK": "Bangkok",
    "UTP": "Pattaya / U-Tapao",
}


TARGET_AIRLINES = {
    "G9": "Air Arabia",
    "CA": "Air China",
    "WY": "Oman Air",
}


def send_telegram(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4000],
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    print("Telegram:", response.status_code)


def search_flights(
    outbound_date,
    return_date,
    from_airport,
    destination,
    airline_codes=None,
):

    outbound = FlightQuery(
        date=outbound_date,
        from_airport=from_airport,
        to_airport=destination,
        max_stops=1,
        airlines=airline_codes,
    )

    inbound = FlightQuery(
        date=return_date,
        from_airport=destination,
        to_airport=from_airport,
        max_stops=1,
    )

    query = create_query(
        flights=[
            outbound,
            inbound,
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1),
        currency="RUB",
        language="ru-RU",
        carry_on_bags=0,
        checked_bags=0,
    )

    return get_flights(query)


def get_price(flight):
    value = getattr(flight, "price", None)

    if value is None:
        return None

    try:
        return int(value)
    except Exception:
        return None


def get_airlines(flight):
    value = getattr(flight, "airlines", [])

    if isinstance(value, list):
        return ", ".join(str(x) for x in value)

    return str(value)


def get_flight_lines(flight):
    lines = []

    segments = getattr(flight, "flights", [])

    for segment in segments:

        airline = getattr(segment, "airline", "")
        number = getattr(segment, "flight_number", "")
        departure = getattr(segment, "departure", "")
        arrival = getattr(segment, "arrival", "")
        duration = getattr(segment, "duration", "")
        stops = getattr(segment, "stops", 0)

        lines.append(
            f"{airline} {number}: "
            f"{departure} -> {arrival} "
            f"({duration} min, stops={stops})"
        )

    return lines


def add_result(
    results,
    outbound,
    return_date,
    airport,
    destination_name,
    flight,
    category,
):

    price = get_price(flight)

    if price is None:
        return

    results.append({
        "outbound": outbound,
        "return": return_date,
        "airport": airport,
        "destination": destination_name,
        "price": price,
        "airlines": get_airlines(flight),
        "flight": flight,
        "category": category,
    })


def search_all_airlines(results):

    print("=== GENERAL SEARCH ===")

    for outbound in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            for airport in MOSCOW_AIRPORTS:

                for destination, destination_name in DESTINATIONS.items():

                    print(
                        f"ALL "
                        f"{airport}->{destination} "
                        f"{outbound}->{return_date}"
                    )

                    try:

                        flights = search_flights(
                            outbound,
                            return_date,
                            airport,
                            destination,
                        )

                        print(
                            "Found:",
                            len(flights)
                        )

                        for flight in flights:

                            add_result(
                                results,
                                outbound,
                                return_date,
                                airport,
                                destination_name,
                                flight,
                                "ALL",
                            )

                    except Exception as error:

                        print(
                            "GENERAL ERROR:",
                            type(error).__name__,
                            str(error),
                        )


def search_target_airlines(results):

    print("=== TARGET AIRLINES ===")

    for code, airline_name in TARGET_AIRLINES.items():

        print(
            f"=== {airline_name} ({code}) ==="
        )

        for outbound in OUTBOUND_DATES:

            for return_date in RETURN_DATES:

                # For the airline-specific search we check
                # Bangkok, which is the main target.
                destination = "BKK"
                destination_name = "Bangkok"

                for airport in MOSCOW_AIRPORTS:

                    print(
                        f"{airline_name} "
                        f"{airport}->BKK "
                        f"{outbound}->{return_date}"
                    )

                    try:

                        flights = search_flights(
                            outbound,
                            return_date,
                            airport,
                            destination,
                            airline_codes=[code],
                        )

                        print(
                            "Found:",
                            len(flights)
                        )

                        for flight in flights:

                            add_result(
                                results,
                                outbound,
                                return_date,
                                airport,
                                destination_name,
                                flight,
                                code,
                            )

                    except Exception as error:

                        print(
                            "AIRLINE ERROR:",
                            code,
                            type(error).__name__,
                            str(error),
                        )


def remove_duplicates(results):

    unique = []
    seen = set()

    for item in results:

        key = (
            item["outbound"],
            item["return"],
            item["airport"],
            item["destination"],
            item["price"],
            item["airlines"],
            item["category"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


def build_message(results):

    results.sort(
        key=lambda item: item["price"]
    )

    message = (
        "✈️ МОСКВА → БАНГКОК / ПАТТАЙЯ\n\n"
        "Вылет: 28–30.12.2026\n"
        "Возврат: 20–25.01.2027\n"
        "1 взрослый • Economy\n"
        "Максимум 1 пересадка\n"
        "Без багажа\n\n"
    )

    message += "🏆 САМЫЕ ДЕШЁВЫЕ ВАРИАНТЫ\n\n"

    for item in results[:10]:

        message += (
            f"💰 {item['price']:,} ₽\n"
            f"📅 {item['outbound']} → "
            f"{item['return']}\n"
            f"🛫 {item['airport']}\n"
            f"🛬 {item['destination']}\n"
            f"✈️ {item['airlines']}\n"
        ).replace(",", " ")

        lines = get_flight_lines(
            item["flight"]
        )

        for line in lines:
            message += f"{line}\n"

        message += "\n"


    message += "⭐ AIR ARABIA / AIR CHINA / OMAN AIR\n\n"


    for code, airline_name in TARGET_AIRLINES.items():

        matches = [
            item
            for item in results
            if item["category"] == code
        ]

        matches.sort(
            key=lambda item: item["price"]
        )

        if not matches:

            message += (
                f"🔹 {airline_name} ({code})\n"
                f"В заданных датах не найдено.\n\n"
            )

            continue


        # Show up to three different date combinations
        shown = 0
        seen_dates = set()

        message += (
            f"🔹 {airline_name} ({code})\n"
        )

        for item in matches:

            date_key = (
                item["outbound"],
                item["return"],
                item["airport"],
            )

            if date_key in seen_dates:
                continue

            seen_dates.add(date_key)

            message += (
                f"💰 {item['price']:,} ₽\n"
                f"📅 {item['outbound']} → "
                f"{item['return']}\n"
                f"🛫 {item['airport']}\n"
            ).replace(",", " ")

            shown += 1

            if shown >= 3:
                break

        message += "\n"


    message += (
        "Источник: Google Flights / fast-flights.\n"
        "Проверены все заданные даты."
    )

    return message


def main():

    print("================================")
    print("FLIGHT MONITOR START")
    print("================================")

    all_results = []

    search_all_airlines(
        all_results
    )

    search_target_airlines(
        all_results
    )

    print(
        "Raw results:",
        len(all_results)
    )

    all_results = remove_duplicates(
        all_results
    )

    print(
        "Unique results:",
        len(all_results)
    )

    if not all_results:

        send_telegram(
            "✈️ FLIGHT MONITOR\n\n"
            "Google Flights не вернул "
            "ни одного результата.\n\n"
            "Подробная причина находится "
            "в GitHub Actions log."
        )

        return


    message = build_message(
        all_results
    )

    send_telegram(
        message
    )

    print("================================")
    print("FLIGHT MONITOR FINISHED")
    print("================================")


if __name__ == "__main__":
    main()
