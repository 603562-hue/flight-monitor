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
# ОСНОВНЫЕ НАСТРОЙКИ
# ============================================================

PRICE_LIMIT_RUB = 70000

RUB_PER_USD = 86.59

PRICE_LIMIT_USD = PRICE_LIMIT_RUB / RUB_PER_USD


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

STATE_FILE = Path("flight_state.json")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):
    try:
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

        if not response.ok:
            print("Telegram error:", response.text)

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
# ПОИСК
# ============================================================

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
    destination_code,
    flight,
):

    price = get_price(flight)

    if price is None:
        return

    # Игнорируем всё дороже лимита
    if price > PRICE_LIMIT_RUB:
        return

    airlines = get_airlines(flight)

    results.append({

        "outbound": outbound,

        "return": return_date,

        "airport": airport,

        "destination": destination_code,

        "destination_name":
            DESTINATIONS[destination_code],

        "price": price,

        "airlines": airlines,

        "segments":
            get_segments(flight),
    })


# ============================================================
# ОБЩИЙ ПОИСК
# ============================================================

def search_all(results, errors):

    total_searches = 0
    successful_searches = 0

    print("================================")
    print("GENERAL GOOGLE FLIGHTS SEARCH")
    print("================================")

    for outbound in OUTBOUND_DATES:

        for return_date in RETURN_DATES:

            for airport in MOSCOW_AIRPORTS:

                for destination_code in DESTINATIONS:

                    total_searches += 1

                    print(
                        f"\nSEARCH {total_searches}: "
                        f"{airport}->{destination_code} "
                        f"{outbound}->{return_date}"
                    )

                    try:

                        flights = search_flights(
                            outbound,
                            return_date,
                            airport,
                            destination_code,
                        )

                        successful_searches += 1

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
                                destination_code,
                                flight,
                            )

                    except Exception as error:

                        error_text = (
                            f"{airport}->{destination_code} "
                            f"{outbound}->{return_date}: "
                            f"{type(error).__name__}: "
                            f"{error}"
                        )

                        print(
                            "SEARCH ERROR:",
                            error_text,
                        )

                        errors.append(
                            error_text
                        )

    return (
        total_searches,
        successful_searches,
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

        airline = segment["airline"]
        number = segment["number"]
        departure = segment["departure"]
        arrival = segment["arrival"]

        text += airline

        if number:
            text += f" {number}"

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

        f"💰 {format_rub(item['price'])} "
        f"({format_usd(item['price'])})\n"

        f"📅 {item['outbound']} → "
        f"{item['return']}\n"

        f"🛫 {item['airport']}\n"

        f"🛬 {item['destination_name']} "
        f"({item['destination']})\n"

        f"✈️ {item['airlines']}\n\n"
    )

    flight_text = build_flight_text(item)

    if flight_text:
        message += flight_text

    message += (
        "\n🎯 Лимит: "
        f"{format_rub(PRICE_LIMIT_RUB)} "
        f"(≈ {format_usd(PRICE_LIMIT_RUB)})\n\n"

        "Источник: Google Flights / fast-flights."
    )

    return message


# ============================================================
# ГЛАВНОЕ СООБЩЕНИЕ ЗА ЗАПУСК
# ============================================================

def build_run_summary(
    results,
    errors,
    total_searches,
    successful_searches,
    new_count,
    cheaper_count,
):

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

        f"🔍 Поисков: {total_searches}\n"
        f"✅ Успешно: {successful_searches}\n"
        f"❌ Ошибок: {len(errors)}\n\n"
    )

    if results:

        message += (
            f"💰 Найдено вариантов до "
            f"{format_rub(PRICE_LIMIT_RUB)}: "
            f"{len(results)}\n\n"
        )

        for index, item in enumerate(
            results[:10],
            start=1,
        ):

            message += (
                f"{index}. "
                f"{format_rub(item['price'])} "
                f"({format_usd(item['price'])})\n"

                f"   {item['outbound']} → "
                f"{item['return']}\n"

                f"   {item['airport']} → "
                f"{item['destination']}\n"

                f"   {item['airlines']}\n\n"
            )

        if len(results) > 10:

            message += (
                f"... ещё "
                f"{len(results) - 10} вариантов\n\n"
            )

    else:

        message += (
            f"❌ Билетов дешевле "
            f"{format_rub(PRICE_LIMIT_RUB)} "
            "не найдено.\n\n"
        )

    message += (
        f"🆕 Новых вариантов: {new_count}\n"
        f"📉 Снижения цены: {cheaper_count}\n"
    )

    if errors:

        message += (
            "\n⚠️ Были ошибки поиска.\n"
            "Первые ошибки:\n"
        )

        for error in errors[:3]:

            message += (
                f"• {error[:500]}\n"
            )

        if len(errors) > 3:

            message += (
                f"• ... ещё "
                f"{len(errors) - 3} ошибок\n"
            )

    return message


# ============================================================
# ОСНОВНАЯ ПРОГРАММА
# ============================================================

def main():

    print("================================")
    print("FLIGHT MONITOR START")
    print("================================")

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

    state = load_state()

    all_results = []
    errors = []

    try:

        total_searches, successful_searches = (
            search_all(
                all_results,
                errors,
            )
        )

    except Exception as error:

        error_text = (
            f"{type(error).__name__}: "
            f"{error}"
        )

        errors.append(error_text)

        print(
            "FATAL SEARCH ERROR:",
            error_text,
        )

        traceback.print_exc()

        total_searches = 0
        successful_searches = 0


    print(
        "Raw results:",
        len(all_results)
    )


    all_results = remove_duplicates(
        all_results
    )


    all_results.sort(
        key=lambda item:
            item["price"]
    )


    print(
        "Unique results:",
        len(all_results)
    )


    new_count = 0
    cheaper_count = 0


    # ========================================================
    # ОБНОВЛЕНИЕ СОСТОЯНИЯ
    # ========================================================

    for item in all_results:

        key = make_key(item)

        new_price = item["price"]

        old_price = state.get(key)


        if old_price is None:

            new_count += 1

            state[key] = new_price

            continue


        if new_price < old_price:

            cheaper_count += 1

            state[key] = new_price


        elif new_price > old_price:

            # Обновляем состояние и при росте цены.
            state[key] = new_price


    # ========================================================
    # СОХРАНЕНИЕ
    # ========================================================

    save_state(state)


    # ========================================================
    # ОТПРАВКА ОДНОГО ОТЧЁТА КАЖДЫЙ ЗАПУСК
    # ========================================================

    summary = build_run_summary(
        all_results,
        errors,
        total_searches,
        successful_searches,
        new_count,
        cheaper_count,
    )

    send_telegram(summary)


    print(
        "================================"
    )

    print(
        "FLIGHT MONITOR FINISHED"
    )

    print(
        f"Notifications: 1"
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
            f"{type(error).__name__}: {error}"
        )

        raise
