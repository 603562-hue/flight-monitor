import os
import requests
from fast_flights import FlightQuery, Passengers, create_query, get_flights


TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


# Our exact dates
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


# Moscow airports
MOSCOW_AIRPORTS = [
    "SVO",
    "DME",
    "VKO",
]

# Bangkok and Pattaya
DESTINATIONS = [
    ("BKK", "Bangkok"),
    ("UTP", "Pattaya / U-Tapao"),
]


def send_telegram(text):

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4000],
            "disable_web_page_preview": True,
        },
        timeout=30,
    )


def search_one(
    outbound_date,
    return_date,
    from_airport,
    destination,
):

    outbound = FlightQuery(
        date=outbound_date,
        from_airport=from_airport,
        to_airport=destination,
        max_stops=1,
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
        language="ru",
        carry_on_bags=0,
        checked_bags=0,
    )

    return get_flights(query)


def flight_airlines(flight):

    airlines = getattr(flight, "airlines", [])

    if isinstance(airlines, list):
        return ", ".join(str(x) for x in airlines)

    return str(airlines)


def flight_details(flight):

    result = []

    segments = getattr(flight, "flights", [])

    for segment in segments:

        airline = getattr(segment, "airline", "")
        flight_number = getattr(segment, "flight_number", "")
        departure = getattr(segment, "departure", "")
        arrival = getattr(segment, "arrival", "")
        duration = getattr(segment, "duration", "")
        stops = getattr(segment, "stops", 0)

        result.append(
            f"{airline} {flight_number} "
            f"{departure} -> {arrival} "
            f"({duration} min, stops={stops})"
        )

    return "\n".join(result)


def main():

    results = []

    total = (
        len(OUTBOUND_DATES)
        * len(RETURN_DATES)
        * len(MOSCOW_AIRPORTS)
        * len(DESTINATIONS)
    )

    print(f"Total searches: {total}")

    for outbound_date in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            for from_airport in MOSCOW_AIRPORTS:

                for destination, destination_name in DESTINATIONS:

                    print(
                        f"SEARCH "
                        f"{from_airport}->{destination} "
                        f"{outbound_date}->{return_date}"
                    )

                    try:

                        result = search_one(
                            outbound_date,
                            return_date,
                            from_airport,
                            destination,
                        )

                        print(
                            "RESULT TYPE:",
                            type(result).__name__
                        )

                        print(
                            "RESULT COUNT:",
                            len(result)
                        )

                        for flight in result:

                            price = getattr(
                                flight,
                                "price",
                                None
                            )

                            if price is None:
                                continue

                            airlines = flight_airlines(
                                flight
                            )

                            results.append({
                                "outbound": outbound_date,
                                "return": return_date,
                                "from": from_airport,
                                "destination": destination_name,
                                "price": int(price),
                                "airlines": airlines,
                                "flight": flight,
                            })

                    except Exception as error:

                        print(
                            "SEARCH ERROR:",
                            type(error).__name__,
                            str(error),
                        )


    if not results:

        send_telegram(
            "FLIGHT MONITOR\n\n"
            "Google Flights returned no results.\n\n"
            "The workflow completed, but no flight "
            "records were received.\n\n"
            "Check the GitHub Actions log for "
            "SEARCH ERROR details."
        )

        return


    # Sort by price
    results.sort(
        key=lambda item: item["price"]
    )


    # Remove exact duplicates
    unique_results = []
    seen = set()

    for item in results:

        key = (
            item["outbound"],
            item["return"],
            item["from"],
            item["destination"],
            item["price"],
            item["airlines"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique_results.append(item)


    results = unique_results


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
            f"🛫 {item['from']}\n"
            f"🛬 {item['destination']}\n"
            f"✈️ {item['airlines']}\n"
            f"{flight_details(item['flight'])}\n\n"
        ).replace(",", " ")


    message += (
        "Источник: Google Flights / fast-flights.\n"
        "Проверены все заданные даты."
    )


    send_telegram(message)

    print(
        f"DONE. Found {len(results)} unique results."
    )


if __name__ == "__main__":
    main()
