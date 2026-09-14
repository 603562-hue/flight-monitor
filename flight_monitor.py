import os
import json
import traceback
from pathlib import Path

import requests

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
# AVIASALES
# ============================================================

AVIASALES_TOKEN = os.environ.get(
    "AVIASALES_API_TOKEN",
    ""
)

AVIASALES_API_URL = (
    "https://api.travelpayouts.com/"
    "aviasales/v3/prices_for_dates"
)


# ============================================================
# ОСНОВНЫЕ НАСТРОЙКИ
# ============================================================

PRICE_LIMIT_RUB = 100000

RUB_PER_USD = 86.59

PRICE_LIMIT_USD = (
    PRICE_LIMIT_RUB / RUB_PER_USD
)


# ============================================================
# ДАТЫ ПОИСКА
# ============================================================

OUTBOUND_DATES = [
    "2026-12-26",
    "2026-12-27",
]

RETURN_DATES = [
    "2027-01-09",
    "2027-01-10",
    "2027-01-11",
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
# ФАЙЛ СОСТОЯНИЯ
# ============================================================

STATE_FILE = Path(
    "flight_state.json"
)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Maxim-Flight-Monitor/1.0"
    )
})


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):

    try:

        response = SESSION.post(
            (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/sendMessage"
            ),
            data={
                "chat_id":
                    TELEGRAM_CHAT_ID,

                "text":
                    text[:4000],

                "disable_web_page_preview":
                    True,
            },
            timeout=30,
        )

        print(
            "Telegram:",
            response.status_code
        )

        if not response.ok:

            print(
                "Telegram error:",
                response.text
            )

        return response.ok

    except Exception as error:

        print(
            "TELEGRAM ERROR:",
            type(error).__name__,
            str(error),
        )

        return False


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
# GOOGLE FLIGHTS
# ============================================================

def search_google_flights(
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
# GOOGLE PRICE
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
# GOOGLE AIRLINES
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


# ============================================================
# GOOGLE SEGMENTS
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
            "airline":
                str(airline),

            "number":
                str(number),

            "departure":
                str(departure),

            "arrival":
                str(arrival),

            "duration":
                str(duration),
        })

    return result


# ============================================================
# AVIASALES SEARCH
# ============================================================

def search_aviasales(
    outbound_date,
    return_date,
    from_airport,
    destination,
):

    if not AVIASALES_TOKEN:

        raise RuntimeError(
            "AVIASALES_API_TOKEN is not configured"
        )

    params = {

        "origin":
            from_airport,

        "destination":
            destination,

        "departure_at":
            outbound_date,

        "return_at":
            return_date,

        "unique":
            "false",

        "sorting":
            "price",

        "direct":
            "false",

        "currency":
            "rub",

        "limit":
            30,

        "page":
            1,

        "one_way":
            "false",

        "token":
            AVIASALES_TOKEN,
    }

    response = SESSION.get(
        AVIASALES_API_URL,
        params=params,
        timeout=60,
    )

    print(
        "Aviasales HTTP:",
        response.status_code
    )

    if not response.ok:

        raise RuntimeError(
            (
                "Aviasales HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )
        )

    data = response.json()

    if not data.get("success", False):

        raise RuntimeError(
            "Aviasales API error: "
            + str(data.get("error"))
        )

    return data.get(
        "data",
        []
    )


# ============================================================
# ДОБАВЛЕНИЕ GOOGLE РЕЗУЛЬТАТА
# ============================================================

def add_google_result(
    results,
    outbound,
    return_date,
    airport,
    destination_code,
    flight,
):

    price = get_price(flight)

    if price is None:

        return

    if price > PRICE_LIMIT_RUB:

        return

    airlines = get_airlines(
        flight
    )

    results.append({

        "source":
            "Google Flights",

        "outbound":
            outbound,

        "return":
            return_date,

        "airport":
            airport,

        "destination":
            destination_code,

        "destination_name":
            DESTINATIONS[
                destination_code
            ],

        "price":
            price,

        "airlines":
            airlines,

        "segments":
            get_segments(flight),

        "transfers":
            None,

    })


# ============================================================
# ДОБАВЛЕНИЕ AVIASALES РЕЗУЛЬТАТА
# ============================================================

def add_aviasales_result(
    results,
    outbound,
    return_date,
    airport,
    destination_code,
    item,
):

    try:

        price = int(
            item.get(
                "price",
                0
            )
        )

    except Exception:

        return

    if price <= 0:

        return

    if price > PRICE_LIMIT_RUB:

        return

    transfers = item.get(
        "transfers"
    )

    return_transfers = item.get(
        "return_transfers"
    )

    if transfers is None:

        transfers = 0

    if return_transfers is None:

        return_transfers = 0

    try:

        transfers = int(
            transfers
        )

    except Exception:

        transfers = 99

    try:

        return_transfers = int(
            return_transfers
        )

    except Exception:

        return_transfers = 99

    # Не принимаем варианты
    # с более чем одной пересадкой
    if transfers > 1:

        return

    if return_transfers > 1:

        return

    airline = str(
        item.get(
            "airline",
            ""
        )
    )

    flight_number = str(
        item.get(
            "flight_number",
            ""
        )
    )

    origin_airport = str(
        item.get(
            "origin_airport",
            airport
        )
    )

    destination_airport = str(
        item.get(
            "destination_airport",
            destination_code
        )
    )

    link = str(
        item.get(
            "link",
            ""
        )
    )

    results.append({

        "source":
            "Aviasales",

        "outbound":
            outbound,

        "return":
            return_date,

        "airport":
            origin_airport,

        "destination":
            destination_code,

        "destination_name":
            DESTINATIONS[
                destination_code
            ],

        "price":
            price,

        "airlines":
            airline,

        "segments": [
            {
                "airline":
                    airline,

                "number":
                    flight_number,

                "departure":
                    str(
                        item.get(
                            "departure_at",
                            ""
                        )
                    ),

                "arrival":
                    str(
                        item.get(
                            "return_at",
                            ""
                        )
                    ),

                "duration":
                    str(
                        item.get(
                            "duration",
                            ""
                        )
                    ),
            }
        ],

        "transfers":
            transfers,

        "return_transfers":
            return_transfers,

        "link":
            link,

        "origin_airport":
            origin_airport,

        "destination_airport":
            destination_airport,
    })


# ============================================================
# ОБЩИЙ ПОИСК
# ============================================================

def search_all(
    results,
    errors,
):

    total_searches = 0

    successful_searches = 0

    aviasales_successes = 0

    aviasales_errors = 0

    print(
        "================================"
    )

    print(
        "GENERAL FLIGHT SEARCH"
    )

    print(
        "Google Flights + Aviasales"
    )

    print(
        "================================"
    )

    for outbound in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            for airport in MOSCOW_AIRPORTS:

                for destination_code in DESTINATIONS:

                    total_searches += 1

                    print(
                        f"\nSEARCH "
                        f"{total_searches}: "
                        f"{airport}->"
                        f"{destination_code} "
                        f"{outbound}->"
                        f"{return_date}"
                    )

                    # ----------------------------------------
                    # GOOGLE
                    # ----------------------------------------

                    try:

                        flights = (
                            search_google_flights(
                                outbound,
                                return_date,
                                airport,
                                destination_code,
                            )
                        )

                        successful_searches += 1

                        print(
                            "Google results:",
                            len(flights)
                        )

                        for flight in flights:

                            add_google_result(
                                results,
                                outbound,
                                return_date,
                                airport,
                                destination_code,
                                flight,
                            )

                    except Exception as error:

                        error_text = (
                            "Google | "
                            f"{airport}->"
                            f"{destination_code} "
                            f"{outbound}->"
                            f"{return_date}: "
                            f"{type(error).__name__}: "
                            f"{error}"
                        )

                        print(
                            "GOOGLE ERROR:",
                            error_text
                        )

                        errors.append(
                            error_text
                        )

                    # ----------------------------------------
                    # AVIASALES
                    # ----------------------------------------

                    try:

                        aviasales_items = (
                            search_aviasales(
                                outbound,
                                return_date,
                                airport,
                                destination_code,
                            )
                        )

                        aviasales_successes += 1

                        print(
                            "Aviasales results:",
                            len(
                                aviasales_items
                            )
                        )

                        for item in (
                            aviasales_items
                        ):

                            add_aviasales_result(
                                results,
                                outbound,
                                return_date,
                                airport,
                                destination_code,
                                item,
                            )

                    except Exception as error:

                        aviasales_errors += 1

                        error_text = (
                            "Aviasales | "
                            f"{airport}->"
                            f"{destination_code} "
                            f"{outbound}->"
                            f"{return_date}: "
                            f"{type(error).__name__}: "
                            f"{error}"
                        )

                        print(
                            "AVIASALES ERROR:",
                            error_text
                        )

                        errors.append(
                            error_text
                        )

    return (
        total_searches,
        successful_searches,
        aviasales_successes,
        aviasales_errors,
    )


# ============================================================
# ДУБЛИКАТЫ
# ============================================================

def remove_duplicates(results):

    unique = []

    seen = set()

    for item in results:

        key = (
            item.get(
                "source",
                ""
            ),

            item.get(
                "outbound",
                ""
            ),

            item.get(
                "return",
                ""
            ),

            item.get(
                "airport",
                ""
            ),

            item.get(
                "destination",
                ""
            ),

            item.get(
                "price",
                0
            ),

            item.get(
                "airlines",
                ""
            ),
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
        f"{item.get('source', '')}|"
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

    usd = (
        price / RUB_PER_USD
    )

    return (
        f"${usd:,.0f}"
        .replace(",", " ")
    )


# ============================================================
# ТЕКСТ РЕЙСА
# ============================================================

def build_flight_text(item):

    text = ""

    for segment in item.get(
        "segments",
        []
    ):

        airline = segment.get(
            "airline",
            ""
        )

        number = segment.get(
            "number",
            ""
        )

        departure = segment.get(
            "departure",
            ""
        )

        arrival = segment.get(
            "arrival",
            ""
        )

        text += airline

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
# ПОЛНОЕ СООБЩЕНИЕ О БИЛЕТЕ
# ============================================================

def build_flight_message(item):

    message = (
        "✈️ Найден билет\n\n"

        f"🔎 Источник: "
        f"{item.get('source', '')}\n\n"

        f"💰 "
        f"{format_rub(item['price'])} "
        f"({format_usd(item['price'])})\n"

        f"📅 {item['outbound']} → "
        f"{item['return']}\n"

        f"🛫 {item['airport']}\n"

        f"🛬 "
        f"{item['destination_name']} "
        f"({item['destination']})\n"

        f"✈️ {item['airlines']}\n\n"
    )

    flight_text = (
        build_flight_text(item)
    )

    if flight_text:

        message += flight_text

    transfers = item.get(
        "transfers"
    )

    return_transfers = item.get(
        "return_transfers"
    )

    if transfers is not None:

        message += (
            "\n🔄 Пересадки: "
            f"{transfers} / "
            f"{return_transfers}\n"
        )

    link = item.get(
        "link",
        ""
    )

    if link:

        message += (
            "\n🔗 Aviasales:\n"
            f"https://www.aviasales.ru/"
            f"search/{link}\n"
        )

    message += (
        "\n🎯 Лимит: "
        f"{format_rub(PRICE_LIMIT_RUB)} "
        f"(≈ {format_usd(PRICE_LIMIT_RUB)})\n\n"

        f"Источник данных: "
        f"{item.get('source', '')}."
    )

    return message


# ============================================================
# СВОДКА
# ============================================================

def build_run_summary(
    results,
    errors,
    total_searches,
    successful_searches,
    aviasales_successes,
    aviasales_errors,
    new_count,
    cheaper_count,
):

    google_results = [
        item
        for item in results
        if item.get("source")
        == "Google Flights"
    ]

    aviasales_results = [
        item
        for item in results
        if item.get("source")
        == "Aviasales"
    ]

    message = (
        "🔎 Maxim Flight Monitor\n\n"

        "Запуск завершён.\n\n"

        "📅 Вылет:\n"
        "26 или 27 декабря 2026\n\n"

        "📅 Возврат:\n"
        "9, 10 или 11 января 2027\n\n"

        "🛫 Москва: SVO / DME / VKO\n"
        "🛬 BKK / UTP\n"
        "👤 1 взрослый\n"
        "💺 Economy\n"
        "🔄 Максимум 1 пересадка\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "🔎 GOOGLE FLIGHTS\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"Поисков: "
        f"{total_searches}\n"

        f"Успешно: "
        f"{successful_searches}\n"

        f"Ошибок: "
        f"{total_searches - successful_searches}\n"

        f"Вариантов ≤ "
        f"{format_rub(PRICE_LIMIT_RUB)}: "
        f"{len(google_results)}\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "🔎 AVIASALES\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"Поисков: "
        f"{total_searches}\n"

        f"Успешно: "
        f"{aviasales_successes}\n"

        f"Ошибок: "
        f"{aviasales_errors}\n"

        f"Вариантов ≤ "
        f"{format_rub(PRICE_LIMIT_RUB)}: "
        f"{len(aviasales_results)}\n\n"
    )

    if results:

        message += (
            "💰 ЛУЧШИЕ ВАРИАНТЫ\n\n"
        )

        for index, item in enumerate(
            sorted(
                results,
                key=lambda x:
                    x["price"]
            )[:10],
            start=1,
        ):

            message += (
                f"{index}. "
                f"{format_rub(item['price'])} "
                f"({format_usd(item['price'])})\n"

                f"   🔎 "
                f"{item.get('source', '')}\n"

                f"   📅 "
                f"{item['outbound']} → "
                f"{item['return']}\n"

                f"   🛫 "
                f"{item['airport']} → "
                f"{item['destination']}\n"

                f"   ✈️ "
                f"{item['airlines']}\n\n"
            )

    else:

        message += (
            f"❌ Билетов дешевле "
            f"{format_rub(PRICE_LIMIT_RUB)} "
            "не найдено.\n\n"
        )

    message += (
        f"🆕 Новых вариантов: "
        f"{new_count}\n"

        f"📉 Снижения цены: "
        f"{cheaper_count}\n"
    )

    if errors:

        message += (
            "\n⚠️ ОШИБКИ ПОИСКА\n\n"
        )

        for index, error in enumerate(
            errors,
            start=1,
        ):

            message += (
                f"{index}. "
                f"{error}\n"
            )

    return message


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "================================"
    )

    print(
        "FLIGHT MONITOR START"
    )

    print(
        "================================"
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

    if AVIASALES_TOKEN:

        print(
            "Aviasales API: CONFIGURED"
        )

    else:

        print(
            "Aviasales API: "
            "NOT CONFIGURED"
        )

    state = load_state()

    all_results = []

    errors = []

    try:

        (
            total_searches,
            successful_searches,
            aviasales_successes,
            aviasales_errors,
        ) = search_all(
            all_results,
            errors,
        )

    except Exception as error:

        error_text = (
            f"{type(error).__name__}: "
            f"{error}"
        )

        errors.append(
            error_text
        )

        print(
            "FATAL SEARCH ERROR:",
            error_text,
        )

        traceback.print_exc()

        total_searches = 0

        successful_searches = 0

        aviasales_successes = 0

        aviasales_errors = 0

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

    # ========================================================
    # ОБНОВЛЕНИЕ СОСТОЯНИЯ
    # ========================================================

    new_count = 0

    cheaper_count = 0

    for item in all_results:

        key = make_key(item)

        new_price = item["price"]

        old_price = state.get(
            key
        )

        if old_price is None:

            new_count += 1

            state[key] = new_price

            continue

        if new_price < old_price:

            cheaper_count += 1

            state[key] = new_price

        elif new_price > old_price:

            state[key] = new_price

    # ========================================================
    # СОХРАНЕНИЕ
    # ========================================================

    save_state(state)

    # ========================================================
    # TELEGRAM SUMMARY
    # ========================================================

    summary = build_run_summary(
        all_results,
        errors,
        total_searches,
        successful_searches,
        aviasales_successes,
        aviasales_errors,
        new_count,
        cheaper_count,
    )

    send_telegram(
        summary
    )

    # ========================================================
    # ОТДЕЛЬНЫЕ СООБЩЕНИЯ О ЛУЧШИХ ВАРИАНТАХ
    # ========================================================

    for item in all_results[:5]:

        send_telegram(
            build_flight_message(
                item
            )
        )

    print(
        "================================"
    )

    print(
        "FLIGHT MONITOR FINISHED"
    )

    print(
        f"Notifications: "
        f"{1 + min(5, len(all_results))}"
    )

    print(
        "================================"
    )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print(
            "FATAL ERROR:",
            type(error).__name__,
            str(error),
        )

        traceback.print_exc()

        send_telegram(
            "🚨 Maxim Flight Monitor\n\n"
            "КРИТИЧЕСКАЯ ОШИБКА.\n\n"
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise
