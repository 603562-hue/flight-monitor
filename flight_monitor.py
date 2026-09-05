import os
import json
import requests
from pathlib import Path
from fast_flights import FlightQuery, Passengers, create_query, get_flights


TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PRICE_LIMIT = 60000
STATE_FILE = Path("flight_state.json")

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
    "Air Arabia": "G9",
    "Air China": "CA",
    "Oman Air": "WY",
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


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def search_flights(
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
        language="ru-RU",
        carry_on_bags=0,
        checked_bags=0,
    )

    return get_flights(query)


def get_price(flight):
    value = getattr(
        flight,
        "price",
        None,
    )

    if value is None:
        return None

    try:
        return int(value)
    except Exception:
        return None


def get_airlines(flight):
    value = getattr(
        flight,
        "airlines",
        [],
    )

    if isinstance(value, list):
        return ", ".join(
            str(x) for x in value
        )

    return str(value)


def airline_match(airlines, target):
    text = airlines.lower()
    target = target.lower()

    aliases = {
        "air arabia": [
            "air arabia",
            "g9",
        ],
        "air china": [
            "air china",
            "ca",
        ],
        "oman air": [
            "oman air",
            "wy",
        ],
    }

    for alias in aliases.get(
        target,
        [target],
    ):
        if alias in text:
            return True

    return False


def get_segments(flight):
    segments = getattr(
        flight,
        "flights",
        [],
    )

    result = []

    for segment in segments:

        airline = getattr(
            segment,
            "airline",
            "",
        )

        number = getattr(
            segment,
            "flight_number",
            "",
        )

        departure = getattr(
            segment,
            "departure",
            "",
        )

        arrival = getattr(
            segment,
            "arrival",
            "",
        )

        result.append(
            f"{airline} {number}: "
            f"{departure} -> {arrival}"
        )

    return result


def search_all():

    results = []

    for outbound in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            for airport in MOSCOW_AIRPORTS:

                for destination, destination_name in DESTINATIONS.items():

                    print(
                        f"SEARCH "
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

                        for flight in flights:

                            price = get_price(
                                flight
                            )

                            if price is None:
                                continue

                            if price > PRICE_LIMIT:
                                continue

                            airlines = get_airlines(
                                flight
                            )

                            results.append({
                                "outbound": outbound,
                                "return": return_date,
                                "airport": airport,
                                "destination": destination_name,
                                "price": price,
                                "airlines": airlines,
                                "segments": get_segments(
                                    flight
                                ),
                            })

                    except Exception as error:

                        print(
                            "SEARCH ERROR:",
                            type(error).__name__,
                            str(error),
                        )

    return results


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
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


def make_key(item):

    return (
        f"{item['outbound']}|"
        f"{item['return']}|"
        f"{item['airport']}|"
        f"{item['destination']}|"
        f"{item['airlines']}"
    )


def build_message(item):

    message = (
        "🚨 ДЕШЁВЫЙ БИЛЕТ!\n\n"
        f"💰 {item['price']:,} ₽\n"
        f"📅 {item['outbound']} → "
        f"{item['return']}\n"
        f"🛫 {item['airport']}\n"
        f"🛬 {item['destination']}\n"
        f"✈️ {item['airlines']}\n\n"
    ).replace(",", " ")

    for segment in item["segments"]:
        message += f"{segment}\n"

    message += (
        "\nУсловие: ≤ 60 000 ₽\n"
        "Источник: Google Flights / fast-flights."
    )

    return message


def main():

    print("FLIGHT MONITOR START")
    print(
        f"Price limit: {PRICE_LIMIT} RUB"
    )

    state = load_state()

    results = search_all()

    results = remove_duplicates(
        results
    )

    results.sort(
        key=lambda x: x["price"]
    )

    print(
        f"Found under limit: {len(results)}"
    )

    if not results:

        print(
            "No flights at or below "
            f"{PRICE_LIMIT} RUB."
        )

        save_state(state)
        return


    notifications = 0

    for item in results:

        key = make_key(item)

        old_price = state.get(key)

        new_price = item["price"]

        # Notify if:
        # 1. this itinerary is new
        # 2. price became lower
        if (
            old_price is None
            or new_price < old_price
        ):

            send_telegram(
                build_message(item)
            )

            notifications += 1

        state[key] = new_price


    save_state(state)

    print(
        f"Notifications sent: "
        f"{notifications}"
    )

    print("FLIGHT MONITOR FINISHED")


if __name__ == "__main__":
    main()
