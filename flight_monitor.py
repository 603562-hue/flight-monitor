import json
import os
import traceback
from datetime import datetime
from pathlib import Path

import requests

from fast_flights import (
    FlightQuery,
    Passengers,
    create_query,
    get_flights,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

PRICE_LIMIT = 100000

DEPARTURE_DATES = [
    "2026-12-26",
    "2026-12-27",
]

RETURN_DATES = [
    "2027-01-09",
    "2027-01-10",
    "2027-01-11",
]

ORIGIN_AIRPORTS = [
    "SVO",
    "DME",
    "VKO",
]

DESTINATIONS = [
    "BKK",
    "UTP",
]

PASSENGERS = Passengers(adults=1)

STATE_FILE = Path("flight_state.json")

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "",
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    "",
)

AVIASALES_TOKEN = os.environ.get(
    "AVIASALES_API_TOKEN",
    "",
)

AVIASALES_API_URL = (
    "https://api.travelpayouts.com/"
    "aviasales/v3/prices_for_dates"
)


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def to_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        text = (
            text.replace("₽", "")
            .replace("RUB", "")
            .replace(" ", "")
            .replace(",", ".")
        )

        return float(text)

    except Exception:
        return None


def format_price(value):
    value = to_float(value)

    if value is None:
        return "—"

    return (
        f"{value:,.0f}"
        .replace(",", " ")
        + " ₽"
    )


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception:
        return {}


def save_state(state):
    with STATE_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )


def telegram_send(text):
    if not TELEGRAM_BOT_TOKEN:
        return False

    if not TELEGRAM_CHAT_ID:
        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()
        return True

    except Exception:
        return False


# ============================================================
# GOOGLE FLIGHTS
# ============================================================

def search_google(
    origin,
    destination,
    departure_date,
    return_date,
):
    """
    Поиск round-trip через fast-flights 3.1.0.

    ВАЖНО:
    fast-flights 3.1.0 умеет создавать round-trip query
    напрямую через create_query(..., trip="round-trip"),
    поэтому никакие get_return_flights здесь не используются.
    """

    query = create_query(
        flights=[
            FlightQuery(
                date=departure_date,
                from_airport=origin,
                to_airport=destination,
                max_stops=1,
            ),
            FlightQuery(
                date=return_date,
                from_airport=destination,
                to_airport=origin,
                max_stops=1,
            ),
        ],
        trip="round-trip",
        seat="economy",
        passengers=PASSENGERS,
        language="en",
        currency="RUB",
    )

    results = get_flights(query)

    return list(results)


def normalize_google_results(
    results,
    origin,
    destination,
    departure_date,
    return_date,
):
    normalized = []

    for flight in results:
        try:
            price = to_float(
                getattr(
                    flight,
                    "price",
                    None,
                )
            )

            if price is None:
                continue

            segments = list(
                getattr(
                    flight,
                    "flights",
                    [],
                )
            )

            if not segments:
                continue

            # Для round-trip Google обычно возвращает
            # все сегменты обоих плеч в одном результате.
            #
            # Поэтому всего сегментов - 2 = пересадки
            # для двух прямых плеч.
            #
            # Если 4 сегмента:
            # 2 туда + 2 обратно = по одной пересадке.
            #
            # Чтобы не считать маршрут ошибочно,
            # определяем пересадки отдельно по направлению.

            outbound_segments = []
            return_segments = []

            outbound_done = False

            for segment in segments:
                from_code = getattr(
                    getattr(
                        segment,
                        "from_airport",
                        None,
                    ),
                    "code",
                    "",
                )

                to_code = getattr(
                    getattr(
                        segment,
                        "to_airport",
                        None,
                    ),
                    "code",
                    "",
                )

                if not outbound_done:
                    outbound_segments.append(
                        segment
                    )

                    if to_code == destination:
                        outbound_done = True

                else:
                    return_segments.append(
                        segment
                    )

            # Защита от странного результата parser'а.
            if not return_segments and len(segments) >= 2:
                half = len(segments) // 2
                outbound_segments = segments[:half]
                return_segments = segments[half:]

            outbound_stops = max(
                len(outbound_segments) - 1,
                0,
            )

            return_stops = max(
                len(return_segments) - 1,
                0,
            )

            airlines = getattr(
                flight,
                "airlines",
                [],
            )

            if airlines is None:
                airlines = []

            airlines = [
                str(x)
                for x in airlines
            ]

            first_segment = segments[0]
            last_segment = segments[-1]

            departure_time = getattr(
                getattr(
                    first_segment,
                    "departure",
                    None,
                ),
                "time",
                None,
            )

            arrival_time = getattr(
                getattr(
                    outbound_segments[-1],
                    "arrival",
                    None,
                ),
                "time",
                None,
            )

            return_departure_time = getattr(
                getattr(
                    return_segments[0],
                    "departure",
                    None,
                ),
                "time",
                None,
            ) if return_segments else None

            return_arrival_time = getattr(
                getattr(
                    last_segment,
                    "arrival",
                    None,
                ),
                "time",
                None,
            )

            normalized.append(
                {
                    "source": "Google",
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date,
                    "return_date": return_date,
                    "price": price,
                    "airlines": airlines,
                    "outbound_stops": outbound_stops,
                    "return_stops": return_stops,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "return_departure_time": return_departure_time,
                    "return_arrival_time": return_arrival_time,
                    "duration_minutes": sum(
                        getattr(
                            segment,
                            "duration",
                            0,
                        )
                        or 0
                        for segment in segments
                    ),
                }
            )

        except Exception:
            # Не ломаем весь поиск из-за одного кривого результата.
            continue

    normalized.sort(
        key=lambda x: x["price"]
    )

    return normalized


# ============================================================
# AVIASALES
# ============================================================

def search_aviasales(
    origin,
    destination,
    departure_date,
    return_date,
):
    if not AVIASALES_TOKEN:
        raise RuntimeError(
            "AVIASALES_API_TOKEN is not configured"
        )

    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": departure_date,
        "return_at": return_date,
        "unique": "false",
        "sorting": "price",
        "direct": "false",
        "currency": "rub",
        "limit": 30,
        "page": 1,
        "one_way": "false",
        "token": AVIASALES_TOKEN,
    }

    response = requests.get(
        AVIASALES_API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, dict):
        raise RuntimeError(
            "Aviasales returned invalid JSON"
        )

    if payload.get("success") is False:
        raise RuntimeError(
            f"Aviasales API error: "
            f"{payload.get('error')}"
        )

    return payload


def normalize_aviasales(
    payload,
    origin,
    destination,
    departure_date,
    return_date,
):
    raw_data = payload.get("data")

    if not raw_data:
        return []

    if isinstance(raw_data, list):
        records = raw_data

    elif isinstance(raw_data, dict):
        records = list(
            raw_data.values()
        )

    else:
        return []

    results = []

    for item in records:
        if not isinstance(item, dict):
            continue

        price = to_float(
            item.get("price")
        )

        if price is None:
            continue

        outbound_stops = item.get(
            "transfers"
        )

        return_stops = item.get(
            "return_transfers"
        )

        try:
            outbound_stops = int(
                outbound_stops
            ) if outbound_stops is not None else None
        except Exception:
            outbound_stops = None

        try:
            return_stops = int(
                return_stops
            ) if return_stops is not None else None
        except Exception:
            return_stops = None

        results.append(
            {
                "source": "Aviasales",
                "origin": (
                    item.get("origin_airport")
                    or origin
                ),
                "destination": (
                    item.get("destination_airport")
                    or destination
                ),
                "departure_date": (
                    departure_date
                ),
                "return_date": (
                    return_date
                ),
                "price": price,
                "airline": (
                    item.get("airline")
                    or ""
                ),
                "flight_number": (
                    item.get("flight_number")
                    or ""
                ),
                "outbound_stops": outbound_stops,
                "return_stops": return_stops,
                "departure": (
                    item.get("departure_at")
                    or ""
                ),
                "return_departure": (
                    item.get("return_at")
                    or ""
                ),
                "duration": (
                    item.get("duration")
                ),
                "link": (
                    item.get("link")
                    or ""
                ),
            }
        )

    results.sort(
        key=lambda x: x["price"]
    )

    return results


# ============================================================
# ОДИН ЗАПРОС
# ============================================================

def run_search(
    source,
    origin,
    destination,
    departure_date,
    return_date,
):
    try:
        if source == "Google":
            raw_results = search_google(
                origin,
                destination,
                departure_date,
                return_date,
            )

            results = normalize_google_results(
                raw_results,
                origin,
                destination,
                departure_date,
                return_date,
            )

        elif source == "Aviasales":
            payload = search_aviasales(
                origin,
                destination,
                departure_date,
                return_date,
            )

            results = normalize_aviasales(
                payload,
                origin,
                destination,
                departure_date,
                return_date,
            )

        else:
            raise RuntimeError(
                f"Unknown source: {source}"
            )

        return {
            "results": results,
            "error": None,
        }

    except Exception as exc:
        return {
            "results": [],
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }


# ============================================================
# МАКСИМУМ 1 ПЕРЕСАДКА
# ============================================================

def is_max_one_stop(result):
    outbound = result.get(
        "outbound_stops"
    )

    returning = result.get(
        "return_stops"
    )

    if outbound is not None:
        if outbound > 1:
            return False

    if returning is not None:
        if returning > 1:
            return False

    return True


# ============================================================
# ИСТОРИЯ
# ============================================================

def history_key(result):
    return "|".join(
        [
            result.get("source", ""),
            result.get("origin", ""),
            result.get("destination", ""),
            result.get("departure_date", ""),
            result.get("return_date", ""),
        ]
    )


def update_history(
    state,
    result,
):
    key = history_key(result)

    old_data = state.get(key)

    old_price = None

    if isinstance(old_data, dict):
        old_price = to_float(
            old_data.get("price")
        )

    state[key] = {
        "price": result.get("price"),
        "updated_at": datetime.utcnow().isoformat(),
    }

    return old_price


# ============================================================
# ФОРМАТ TELEGRAM
# ============================================================

def format_result(result):
    source = result.get(
        "source",
        "",
    )

    price = result.get(
        "price"
    )

    origin = result.get(
        "origin",
        "",
    )

    destination = result.get(
        "destination",
        "",
    )

    departure_date = result.get(
        "departure_date",
        "",
    )

    return_date = result.get(
        "return_date",
        "",
    )

    outbound_stops = result.get(
        "outbound_stops"
    )

    return_stops = result.get(
        "return_stops"
    )

    if (
        outbound_stops is None
        and return_stops is None
    ):
        stops_text = (
            "🔄 Пересадки: нет данных"
        )
    else:
        out_text = (
            str(outbound_stops)
            if outbound_stops is not None
            else "?"
        )

        back_text = (
            str(return_stops)
            if return_stops is not None
            else "?"
        )

        stops_text = (
            f"🔄 Пересадки: "
            f"{out_text} / {back_text}"
        )

    lines = [
        f"🔎 {source}",
        f"💰 {format_price(price)}",
        f"🛫 {origin} → {destination}",
        f"📅 {departure_date}",
        f"↩️ {return_date}",
        stops_text,
    ]

    airlines = result.get(
        "airlines"
    )

    if airlines:
        lines.append(
            "✈️ " + ", ".join(airlines)
        )

    airline = result.get(
        "airline"
    )

    flight_number = result.get(
        "flight_number"
    )

    if airline:
        airline_text = airline

        if flight_number:
            airline_text += (
                f" {flight_number}"
            )

        lines.append(
            f"✈️ {airline_text}"
        )

    link = result.get(
        "link"
    )

    if link:
        if not str(link).startswith("http"):
            link = (
                "https://www.aviasales.ru"
                + str(link)
            )

        lines.append(
            f"🔗 {link}"
        )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():
    state = load_state()

    google_searches = 0
    google_successes = 0
    google_errors = 0
    google_empty = 0

    aviasales_searches = 0
    aviasales_successes = 0
    aviasales_errors = 0
    aviasales_empty = 0

    google_results = []
    aviasales_results = []

    errors = []

    # --------------------------------------------------------
    # GOOGLE
    # --------------------------------------------------------

    for departure_date in DEPARTURE_DATES:
        for return_date in RETURN_DATES:
            for origin in ORIGIN_AIRPORTS:
                for destination in DESTINATIONS:

                    google_searches += 1

                    response = run_search(
                        "Google",
                        origin,
                        destination,
                        departure_date,
                        return_date,
                    )

                    if response["error"]:
                        google_errors += 1

                        errors.append(
                            (
                                "Google",
                                origin,
                                destination,
                                departure_date,
                                return_date,
                                response["error"],
                            )
                        )

                    else:
                        google_successes += 1

                        if response["results"]:
                            google_results.extend(
                                response["results"]
                            )
                        else:
                            google_empty += 1

    # --------------------------------------------------------
    # AVIASALES
    # --------------------------------------------------------

    for departure_date in DEPARTURE_DATES:
        for return_date in RETURN_DATES:
            for origin in ORIGIN_AIRPORTS:
                for destination in DESTINATIONS:

                    aviasales_searches += 1

                    response = run_search(
                        "Aviasales",
                        origin,
                        destination,
                        departure_date,
                        return_date,
                    )

                    if response["error"]:
                        aviasales_errors += 1

                        errors.append(
                            (
                                "Aviasales",
                                origin,
                                destination,
                                departure_date,
                                return_date,
                                response["error"],
                            )
                        )

                    else:
                        aviasales_successes += 1

                        if response["results"]:
                            aviasales_results.extend(
                                response["results"]
                            )
                        else:
                            aviasales_empty += 1

    # --------------------------------------------------------
    # ФИЛЬТР
    # --------------------------------------------------------

    google_filtered = [
        result
        for result in google_results
        if is_max_one_stop(result)
    ]

    aviasales_filtered = [
        result
        for result in aviasales_results
        if is_max_one_stop(result)
    ]

    all_results = (
        google_filtered
        + aviasales_filtered
    )

    all_results.sort(
        key=lambda item: item["price"]
    )

    google_cheap = [
        result
        for result in google_filtered
        if result["price"] <= PRICE_LIMIT
    ]

    aviasales_cheap = [
        result
        for result in aviasales_filtered
        if result["price"] <= PRICE_LIMIT
    ]

    cheap_results = [
        result
        for result in all_results
        if result["price"] <= PRICE_LIMIT
    ]

    google_best = (
        google_filtered[0]
        if google_filtered
        else None
    )

    aviasales_best = (
        aviasales_filtered[0]
        if aviasales_filtered
        else None
    )

    # --------------------------------------------------------
    # ИСТОРИЯ
    # --------------------------------------------------------

    new_count = 0
    price_drop_count = 0

    for result in all_results:
        old_price = update_history(
            state,
            result,
        )

        if old_price is None:
            new_count += 1

        elif result["price"] < old_price:
            price_drop_count += 1

    save_state(state)

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    lines = [
        "Maxim Flight Monitor",
        "",
        "Запуск завершён.",
        "",
        "📅 Вылет:",
        "26 или 27 декабря 2026",
        "",
        "📅 Возврат:",
        "9, 10 или 11 января 2027",
        "",
        "🛫 Москва: SVO / DME / VKO",
        "🛬 BKK / UTP",
        "👤 1 взрослый",
        "💺 Economy",
        "🔄 Максимум 1 пересадка",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🔎 GOOGLE FLIGHTS",
        "━━━━━━━━━━━━━━━━━━",
        f"Поисков: {google_searches}",
        f"Успешно: {google_successes}",
        f"Ошибок: {google_errors}",
        f"Пустых результатов: {google_empty}",
        f"Вариантов ≤ {format_price(PRICE_LIMIT)}: "
        f"{len(google_cheap)}",
    ]

    if google_best:
        lines.append(
            "💵 Минимальная найденная цена: "
            f"{format_price(google_best['price'])}"
        )
    else:
        lines.append(
            "💵 Минимальная найденная цена: "
            "нет данных"
        )

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🔎 AVIASALES",
            "━━━━━━━━━━━━━━━━━━",
            f"Поисков: {aviasales_searches}",
            f"Успешно: {aviasales_successes}",
            f"Ошибок: {aviasales_errors}",
            f"Пустых результатов: {aviasales_empty}",
            f"Вариантов ≤ {format_price(PRICE_LIMIT)}: "
            f"{len(aviasales_cheap)}",
        ]
    )

    if aviasales_best:
        lines.append(
            "💵 Минимальная найденная цена: "
            f"{format_price(aviasales_best['price'])}"
        )
    else:
        lines.append(
            "💵 Минимальная найденная цена: "
            "нет данных"
        )

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "📊 ИТОГ",
            "━━━━━━━━━━━━━━━━━━",
            f"Подходящих вариантов: "
            f"{len(all_results)}",
            f"≤ {format_price(PRICE_LIMIT)}: "
            f"{len(cheap_results)}",
            f"🆕 Новых вариантов: "
            f"{new_count}",
            f"📉 Снижений цены: "
            f"{price_drop_count}",
        ]
    )

    if cheap_results:
        lines.extend(
            [
                "",
                "🎯 Найдены билеты дешевле "
                "100 000 ₽.",
            ]
        )

    elif all_results:
        lines.extend(
            [
                "",
                "ℹ️ Билетов дешевле 100 000 ₽ "
                "пока нет, но найдены варианты "
                "выше лимита.",
            ]
        )

    else:
        lines.extend(
            [
                "",
                "❌ Подходящих вариантов пока "
                "не найдено.",
            ]
        )

    # --------------------------------------------------------
    # ОШИБКИ
    # --------------------------------------------------------

    if errors:
        lines.extend(
            [
                "",
                "⚠️ ТЕХНИЧЕСКИЕ ОШИБКИ",
            ]
        )

        for index, error in enumerate(
            errors[:15],
            start=1,
        ):
            (
                source,
                origin,
                destination,
                departure_date,
                return_date,
                message,
            ) = error

            lines.append(
                f"{index}. {source} | "
                f"{origin}->{destination} | "
                f"{departure_date}->{return_date} | "
                f"{message}"
            )

        if len(errors) > 15:
            lines.append(
                f"... ещё {len(errors) - 15}"
            )

    # --------------------------------------------------------
    # AVIASALES CACHE INFO
    # --------------------------------------------------------

    if (
        aviasales_successes > 0
        and aviasales_empty > 0
    ):
        lines.extend(
            [
                "",
                "ℹ️ Aviasales отвечает без ошибок, "
                "но по части запросов сейчас нет "
                "тарифов в Data API кеше.",
            ]
        )

    summary = "\n".join(lines)

    telegram_send(summary)

    # --------------------------------------------------------
    # ЛУЧШИЕ 5
    # --------------------------------------------------------

    for result in all_results[:5]:
        telegram_send(
            format_result(result)
        )

    print(summary)

    for result in all_results[:5]:
        print()
        print(
            format_result(result)
        )


# ============================================================
# КРИТИЧЕСКАЯ ОШИБКА
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        message = (
            "🚨 Maxim Flight Monitor\n\n"
            "КРИТИЧЕСКАЯ ОШИБКА\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"{traceback.format_exc()[-3000:]}"
        )

        telegram_send(message)

        raise
