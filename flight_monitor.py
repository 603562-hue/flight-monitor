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

DESTINATIONS = {
    "BKK": "Bangkok BKK",
    "UTP": "Pattaya UTP",
}

TARGET_AIRLINES = {
    "G9": "Air Arabia",
    "CA": "Air China",
    "WY": "Oman Air",
}


def telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4000],
            "disable_web_page_preview": True,
        },
        timeout=30,
    )


def search_flight(outbound, return_date, destination):
    outbound_leg = FlightQuery(
        date=outbound,
        from_airport="MOW",
        to_airport=destination,
        max_stops=1,
    )

    return_leg = FlightQuery(
        date=return_date,
        from_airport=destination,
        to_airport="MOW",
        max_stops=1,
    )

    query = create_query(
        flights=[outbound_leg, return_leg],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1),
        currency="RUB",
        language="ru-RU",
        carry_on_bags=0,
        checked_bags=0,
    )

    return get_flights(query)


def airline_name(text):
    text = str(text).lower()

    if "air arabia" in text:
        return "Air Arabia"
    if "air china" in text:
        return "Air China"
    if "oman air" in text:
        return "Oman Air"

    return None


def main():

    results = []

    total = len(DESTINATIONS) * len(OUTBOUND_DATES) * len(RETURN_DATES)

    print(f"Search combinations: {total}")

    for destination, destination_name in DESTINATIONS.items():

        for outbound in OUTBOUND_DATES:

            for return_date in RETURN_DATES:

                print(
                    f"Searching {outbound} -> {return_date} "
                    f"{destination}"
                )

                try:
                    flights = search_flight(
                        outbound,
                        return_date,
                        destination,
                    )

                    for flight in flights:

                        price = getattr(flight, "price", None)

                        if price is None:
                            continue

                        airlines = getattr(
                            flight,
                            "airlines",
                            ""
                        )

                        results.append({
                            "destination": destination_name,
                            "outbound": outbound,
                            "return": return_date,
                            "price": price,
                            "airlines": str(airlines),
                            "flight": flight,
                        })

                except Exception as e:

                    print(
                        "ERROR:",
                        outbound,
                        return_date,
                        destination,
                        repr(e),
                    )


    if not results:
        telegram(
            "Flight Monitor\n\n"
            "Google Flights did not return any results."
        )
        return


    results.sort(
        key=lambda x: x["price"]
    )


    # Remove exact duplicates
    unique = []
    seen = set()

    for item in results:

        key = (
            item["destination"],
            item["outbound"],
            item["return"],
            item["price"],
            item["airlines"],
        )

        if key not in seen:
            seen.add(key)
            unique.append(item)


    results = unique


    message = (
        "✈️ МОСКВА → БАНГКОК / ПАТТАЙЯ\n\n"
        "Вылет: 28–30.12.2026\n"
        "Возврат: 20–25.01.2027\n"
        "1 взрослый • Economy\n"
        "Максимум 1 пересадка\n"
        "Без багажа\n\n"
    )


    message += "🏆 САМЫЕ ДЕШЁВЫЕ\n\n"


    for item in results[:10]:

        price = item["price"]

        message += (
            f"💰 {price:,} ₽\n"
            f"📅 {item['outbound']} → {item['return']}\n"
            f"📍 {item['destination']}\n"
            f"✈️ {item['airlines']}\n\n"
        ).replace(",", " ")


    message += "\n⭐ ЦЕЛЕВЫЕ АВИАКОМПАНИИ\n\n"


    found_airlines = set()


    for item in results:

        name = airline_name(item["airlines"])

        if name and name not in found_airlines:

            found_airlines.add(name)

            message += (
                f"🔹 {name}\n"
                f"💰 {item['price']:,} ₽\n"
                f"📅 {item['outbound']} → "
                f"{item['return']}\n"
                f"📍 {item['destination']}\n"
                f"✈️ {item['airlines']}\n\n"
            ).replace(",", " ")


    message += (
        "Источник: Google Flights "
        "через бесплатный fast-flights."
    )


    telegram(message)


if __name__ == "__main__":
    main()
