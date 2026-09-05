import os
import json
import requests
from pathlib import Path

from fast_flights import (
    FlightQuery,
    Passengers,
    create_query,
    get_flights,
)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


# ============================================================
# ОСНОВНЫЕ НАСТРОЙКИ
# ============================================================

# Максимальная цена билета
PRICE_LIMIT_RUB = 70000

# Ориентировочный курс для отображения цены в долларах.
# Сам поиск всё равно выполняется в RUB.
RUB_PER_USD = 86.59

# Рассчитанный долларовый лимит
PRICE_LIMIT_USD = PRICE_LIMIT_RUB / RUB_PER_USD


# ============================================================
# ДАТЫ
# ============================================================

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


# ============================================================
# АЭРОПОРТЫ МОСКВЫ
# ============================================================

MOSCOW_AIRPORTS = [
    "SVO",
    "DME",
    "VKO",
]


# ============================================================
# ПУНКТЫ НАЗНАЧЕНИЯ
# ============================================================

DESTINATIONS = {
    "BKK": "Bangkok",
    "UTP": "Pattaya / U-Tapao",
}


# ============================================================
# АВИАКОМПАНИИ
# ============================================================

TARGET_AIRLINES = {
    "G9": "Air Arabia",
    "CA": "Air China",
    "WY": "Oman Air",
    "EY": "Etihad Airways",
    "TK": "Turkish Airlines",
    "FZ": "flydubai",
    "CZ": "China Southern",
    "MU": "China Eastern",
    "QR": "Qatar Airways",
    "EK": "Emirates",
}


# ============================================================
# ФАЙЛ СОСТОЯНИЯ
# ============================================================

STATE_FILE = Path("flight_state.json")


# ============================================================
# TELEGRAM
# ============================================================

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

    print(
        "Telegram:",
        response.status_code,
    )


# ============================================================
# СОСТОЯНИЕ
# ============================================================

def load_state():

    if not STATE_FILE.exists():
        return {}

    try:

        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:

        print(
            "STATE LOAD ERROR:",
            type(error).__name__,
            str(error),
        )

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


# ============================================================
# ПОИСК
# ============================================================

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
        passengers=Passengers(
            adults=1
        ),
        currency="RUB",
        language="ru-RU",
        carry_on_bags=0,
        checked_bags=0,
    )

    return get_flights(query)


# ============================================================
# ЦЕНА
# ============================================================

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


# ============================================================
# АВИАКОМПАНИИ
# ============================================================

def get_airlines(flight):

    value = getattr(
        flight,
        "airlines",
        [],
    )

    if isinstance(value, list):

        return ", ".join(
            str(x)
            for x in value
        )

    return str(value)


def identify_target_airlines(
    airlines_text
):

    text = airlines_text.lower()

    aliases = {

        "G9": [
            "air arabia",
            "g9",
        ],

        "CA": [
            "air china",
            "ca",
        ],

        "WY": [
            "oman air",
            "wy",
        ],

        "EY": [
            "etihad",
            "etihad airways",
            "ey",
        ],

        "TK": [
            "turkish airlines",
            "turkish",
            "tk",
        ],

        "FZ": [
            "flydubai",
            "fly dubai",
            "fz",
        ],

        "CZ": [
            "china southern",
            "cz",
        ],

        "MU": [
            "china eastern",
            "mu",
        ],

        "QR": [
            "qatar airways",
            "qatar",
            "qr",
        ],

        "EK": [
            "emirates",
            "ek",
        ],
    }

    found = []

    for code, names in aliases.items():

        for name in names:

            if name in text:

                found.append(
                    TARGET_AIRLINES[code]
                )

                break

    return found


# ============================================================
# СЕГМЕНТЫ
# ============================================================

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

        duration = getattr(
            segment,
            "duration",
            "",
        )

        result.append({
            "airline": str(airline),
            "number": str(number),
            "departure": str(departure),
            "arrival": str(arrival),
            "duration": str(duration),
        })

    return result


# ============================================================
# ДОБАВЛЕНИЕ РЕЗУЛЬТАТА
# ============================================================

def add_result(
    results,
    outbound,
    return_date,
    airport,
    destination,
    flight,
    search_type,
):

    price = get_price(flight)

    if price is None:
        return

    # Главный фильтр:
    # всё дороже 70 000 ₽ игнорируем
    if price > PRICE_LIMIT_RUB:
        return

    airlines = get_airlines(
        flight
    )

    target_airlines = (
        identify_target_airlines(
            airlines
        )
    )

    results.append({

        "outbound": outbound,

        "return": return_date,

        "airport": airport,

        "destination": destination,

        "price": price,

        "airlines": airlines,

        "target_airlines":
            target_airlines,

        "segments":
            get_segments(
                flight
            ),

        "search_type":
            search_type,
    })


# ============================================================
# ОБЩИЙ ПОИСК
# ============================================================

def search_general(results):

    print(
        "================================"
    )

    print(
        "GENERAL GOOGLE FLIGHTS SEARCH"
    )

    print(
        "================================"
    )

    for outbound in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            for airport in MOSCOW_AIRPORTS:

                for destination, destination_name in DESTINATIONS.items():

                    print(
                        f"GENERAL: "
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
                            "Results:",
                            len(flights),
                        )

                        for flight in flights:

                            add_result(
                                results,
                                outbound,
                                return_date,
                                airport,
                                destination_name,
                                flight,
                                "GENERAL",
                            )

                    except Exception as error:

                        print(
                            "GENERAL ERROR:",
                            type(error).__name__,
                            str(error),
                        )


# ============================================================
# СПЕЦИАЛЬНЫЙ ПОИСК АВИАКОМПАНИЙ
# ============================================================

def search_target_airlines(results):

    print(
        "================================"
    )

    print(
        "TARGET AIRLINE SEARCH"
    )

    print(
        "================================"
    )

    for code, airline_name in TARGET_AIRLINES.items():

        print(
            f"\n>>> {airline_name} ({code})"
        )

        for outbound in OUTBOUND_DATES:

            for return_date in RETURN_DATES:

                for airport in MOSCOW_AIRPORTS:

                    destination = "BKK"

                    print(
                        f"{airline_name}: "
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
                            "Results:",
                            len(flights),
                        )

                        for flight in flights:

                            add_result(
                                results,
                                outbound,
                                return_date,
                                airport,
                                "Bangkok",
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


# ============================================================
# ДУБЛИКАТЫ
# ============================================================

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


# ============================================================
# КЛЮЧ ВАРИАНТА
# ============================================================

def make_key(item):

    return (
        f"{item['outbound']}|"
        f"{item['return']}|"
        f"{item['airport']}|"
        f"{item['destination']}|"
        f"{item['airlines']}"
    )


# ============================================================
# ФОРМАТИРОВАНИЕ
# ============================================================

def format_rub(price):

    return (
        f"{price:,}"
        .replace(",", " ")
        + " ₽"
    )


def format_usd(price):

    usd = price / RUB_PER_USD

    return (
        f"${usd:,.0f}"
        .replace(",", " ")
    )


# ============================================================
# ТЕКСТ РЕЙСА
# ============================================================

def build_flight_text(item):

    text = ""

    for segment in item["segments"]:

        airline = segment[
            "airline"
        ]

        number = segment[
            "number"
        ]

        departure = segment[
            "departure"
        ]

        arrival = segment[
            "arrival"
        ]

        text += (
            f"{airline}"
        )

        if number:

            text += (
                f" {number}"
            )

        text += (
            f": {departure} → "
            f"{arrival}\n"
        )

    return text


# ============================================================
# TELEGRAM
# ============================================================

def build_message(item):

    price_rub = format_rub(
        item["price"]
    )

    price_usd = format_usd(
        item["price"]
    )

    limit_usd = format_usd(
        PRICE_LIMIT_RUB
    )

    message = (
        "🚨 ДЕШЁВЫЙ БИЛЕТ!\n\n"

        f"💰 {price_rub} "
        f"({price_usd})\n"

        f"📅 {item['outbound']} → "
        f"{item['return']}\n"

        f"🛫 {item['airport']}\n"

        f"🛬 {item['destination']}\n"

        f"✈️ {item['airlines']}\n\n"
    )

    if item["target_airlines"]:

        message += (
            "⭐ "
            + ", ".join(
                item[
                    "target_airlines"
                ]
            )
            + "\n\n"
        )

    message += (
        build_flight_text(
            item
        )
    )

    message += (
        "\n🎯 Лимит: "
        f"{format_rub(PRICE_LIMIT_RUB)} "
        f"(≈ {limit_usd})\n"

        "Источник: Google Flights / "
        "fast-flights."
    )

    return message


# ============================================================
# ОСНОВНАЯ ПРОГРАММА
# ============================================================

def main():

    print(
        "================================"
    )

    print(
        "FLIGHT MONITOR START"
    )

    print(
        f"Price limit: "
        f"{PRICE_LIMIT_RUB} RUB"
    )

    print(
        f"Approx USD limit: "
        f"${PRICE_LIMIT_USD:.0f}"
    )

    print(
        f"RUB/USD rate: "
        f"{RUB_PER_USD}"
    )

    print(
        "================================"
    )

    state = load_state()

    all_results = []


    # Общий поиск
    search_general(
        all_results
    )


    # Поиск целевых авиакомпаний
    search_target_airlines(
        all_results
    )


    print(
        "Raw results:",
        len(all_results)
    )


    all_results = (
        remove_duplicates(
            all_results
        )
    )


    all_results.sort(
        key=lambda item:
            item["price"]
    )


    print(
        "Unique results:",
        len(all_results)
    )


    notifications = 0


    # ========================================================
    # УВЕДОМЛЕНИЯ
    # ========================================================

    for item in all_results:

        key = make_key(
            item
        )

        new_price = item[
            "price"
        ]

        old_price = state.get(
            key
        )


        # Новый вариант
        if old_price is None:

            send_telegram(
                build_message(
                    item
                )
            )

            notifications += 1

            state[key] = new_price

            continue


        # Цена снизилась
        if new_price < old_price:

            difference = (
                old_price
                - new_price
            )

            message = (
                "📉 ЦЕНА УПАЛА!\n\n"

                f"Было: "
                f"{format_rub(old_price)} "
                f"({format_usd(old_price)})\n"

                f"Стало: "
                f"{format_rub(new_price)} "
                f"({format_usd(new_price)})\n"

                f"Экономия: "
                f"{format_rub(difference)} "
                f"({format_usd(difference)})\n\n"
            )

            message += (
                build_message(
                    item
                )
            )

            send_telegram(
                message
            )

            notifications += 1

            state[key] = new_price


        # Если цена не изменилась —
        # ничего не отправляем.

        # Если цена выросла —
        # тоже ничего не отправляем.


    # Сохраняем состояние
    save_state(
        state
    )


    print(
        "Notifications sent:",
        notifications
    )

    print(
        "================================"
    )

    print(
        "FLIGHT MONITOR FINISHED"
    )

    print(
        "================================"
    )


if __name__ == "__main__":

    main()
