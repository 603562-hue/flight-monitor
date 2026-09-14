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
    get_return_flights,
    select_flight,
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

def get_value(obj, *names, default=None):
    if obj is None:
        return default

    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]

    for name in names:
        try:
            return getattr(obj, name)
        except Exception:
            continue

    return default


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
    number = to_float(value)

    if number is None:
        return "—"

    return (
        f"{number:,.0f}"
        .replace(",", " ")
        + " ₽"
    )


def normalize_stops(value):
    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    text = str(value).strip().lower()

    if text in {
        "direct",
        "nonstop",
        "0",
        "без пересадок",
    }:
        return 0

    digits = "".join(
        char for char in text
        if char.isdigit()
    )

    if digits:
        try:
            return int(digits)
        except Exception:
            pass

    return None


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
    Актуальный round-trip flow fast-flights 3.1.x:

    1. ищем outbound;
    2. берём несколько самых дешёвых вариантов;
    3. выбираем outbound;
    4. запрашиваем соответствующие return flights;
    5. сохраняем цену выбранного round-trip.
    """

    outbound_flight = FlightQuery(
        date=departure_date,
        from_airport=origin,
        to_airport=destination,
        max_stops=1,
    )

    return_flight = FlightQuery(
        date=return_date,
        from_airport=destination,
        to_airport=origin,
        max_stops=1,
    )

    query = create_query(
        flights=[
            outbound_flight,
            return_flight,
        ],
        trip="round-trip",
        seat="economy",
        passengers=PASSENGERS,
        language="en",
        currency="RUB",
    )

    outbound_results = get_flights(query)

    if not outbound_results:
        return []

    # Не перебираем десятки вариантов.
    # Достаточно нескольких самых дешёвых.
    candidates = list(outbound_results[:5])

    combined = []

    for outbound in candidates:
        try:
            return_query = select_flight(
                query,
                outbound,
            )

            return_results = get_return_flights(
                return_query
            )

            if not return_results:
                continue

            for returning in list(
                return_results[:5]
            ):
                outbound_price = to_float(
                    get_value(
                        outbound,
                        "price",
                    )
                )

                return_price = to_float(
                    get_value(
                        returning,
                        "price",
                    )
                )

                if (
                    outbound_price is None
                    or return_price is None
                ):
                    continue

                total_price = (
                    outbound_price
                    + return_price
                )

                outbound_stops = normalize_stops(
                    get_value(
                        outbound,
                        "stops",
                        "stop_count",
                    )
                )

                return_stops = normalize_stops(
                    get_value(
                        returning,
                        "stops",
                        "stop_count",
                    )
                )

                combined.append(
                    {
                        "source": "Google",
                        "origin": origin,
                        "destination": destination,
                        "departure_date": departure_date,
                        "return_date": return_date,
                        "price": total_price,
                        "outbound_price": outbound_price,
                        "return_price": return_price,
                        "outbound_airline": str(
                            get_value(
                                outbound,
                                "name",
                                "airline",
                                default="",
                            )
                            or ""
                        ),
                        "return_airline": str(
                            get_value(
                                returning,
                                "name",
                                "airline",
                                default="",
                            )
                            or ""
                        ),
                        "outbound_stops": outbound_stops,
                        "return_stops": return_stops,
                        "departure": str(
                            get_value(
                                outbound,
                                "departure",
                                "departure_time",
                                default="",
                            )
                            or ""
                        ),
                        "arrival": str(
                            get_value(
                                outbound,
                                "arrival",
                                "arrival_time",
                                default="",
                            )
                            or ""
                        ),
                        "return_departure": str(
                            get_value(
                                returning,
                                "departure",
                                "departure_time",
                                default="",
                            )
                            or ""
                        ),
                        "return_arrival": str(
                            get_value(
                                returning,
                                "arrival",
                                "arrival_time",
                                default="",
                            )
                            or ""
                        ),
                    }
                )

        except Exception:
            # Ошибка одного конкретного outbound
            # не должна ломать весь поиск.
            continue

    combined.sort(
        key=lambda item: item["price"]
    )

    return combined


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
        error = payload.get("error")

        raise RuntimeError(
            f"Aviasales API error: {error}"
        )

    return payload


def normalize_aviasales(
    payload,
    origin,
    destination,
    departure_date,
    return_date,
):
    raw = payload.get("data")

    if not raw:
        return []

    if isinstance(raw, list):
        records = raw

    elif isinstance(raw, dict):
        records = list(raw.values())

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

        results.append(
            {
                "source": "Aviasales",
                "origin": item.get(
                    "origin_airport"
                ) or origin,
                "destination": item.get(
                    "destination_airport"
                ) or destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "price": price,
                "airline": item.get(
                    "airline"
                ) or "",
                "flight_number": item.get(
                    "flight_number"
                ) or "",
                "outbound_stops": normalize_stops(
                    item.get("transfers")
                ),
                "return_stops": normalize_stops(
                    item.get("return_transfers")
                ),
                "departure": item.get(
                    "departure_at"
                ) or "",
                "return_departure": item.get(
                    "return_at"
                ) or "",
                "duration": item.get(
                    "duration"
                ),
                "link": item.get("link")
                or "",
            }
        )

    results.sort(
        key=lambda item: item["price"]
    )

    return results


# ============================================================
# ОДИН ПОИСК
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
            results = search_google(
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
# ФИЛЬТР ПЕРЕСАДОК
# ============================================================

def is_max_one_stop(result):
    outbound = result.get(
        "outbound_stops"
    )

    returning = result.get(
        "return_stops"
    )

    # Если источник не дал число пересадок,
    # не отбрасываем Google автоматически.
    # В Telegram это будет видно как неизвестно.
    if outbound is not None and outbound > 1:
        return False

    if returning is not None and returning > 1:
        return False

    return True


# ============================================================
# ИСТОРИЯ ЦЕН
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

    new_price = result.get("price")

    old = state.get(key)

    old_price = None

    if isinstance(old, dict):
        old_price = to_float(
            old.get("price")
        )

    state[key] = {
        "price": new_price,
        "updated_at": datetime.utcnow().isoformat(),
    }

    return old_price


# ============================================================
# ФОРМАТ РЕЗУЛЬТАТА
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
        stops_text = "🔄 пересадки: нет данных"

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
            f"🔄 пересадки: {out_text}/{back_text}"
        )

    lines = [
        f"🔎 {source}",
        f"💰 {format_price(price)}",
        f"🛫 {origin} → {destination}",
        f"📅 {departure_date}",
        f"↩️ {return_date}",
        stops_text,
    ]

    airline = result.get(
        "airline"
    )

    if airline:
        lines.append(
            f"✈️ {airline}"
        )

    outbound_airline = result.get(
        "outbound_airline"
    )

    return_airline = result.get(
        "return_airline"
    )

    if outbound_airline:
        lines.append(
            f"✈️ туда: {outbound_airline}"
        )

    if return_airline:
        lines.append(
            f"✈️ обратно: {return_airline}"
        )

    outbound_price = result.get(
        "outbound_price"
    )

    return_price = result.get(
        "return_price"
    )

    if (
        outbound_price is not None
        and return_price is not None
    ):
        lines.extend(
            [
                f"   туда: {format_price(outbound_price)}",
                f"   обратно: {format_price(return_price)}",
            ]
        )

    duration = result.get(
        "duration"
    )

    if duration:
        lines.append(
            f"⏱ {duration}"
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

                        continue

                    google_successes += 1

                    if not response["results"]:
                        google_empty += 1

                    else:
                        google_results.extend(
                            response["results"]
                        )

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

                        continue

                    aviasales_successes += 1

                    if not response["results"]:
                        aviasales_empty += 1

                    else:
                        aviasales_results.extend(
                            response["results"]
                        )

    # --------------------------------------------------------
    # МАКСИМУМ 1 ПЕРЕСАДКА
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
        key=lambda result: result["price"]
    )

    cheap_results = [
        result
        for result in all_results
        if result["price"] <= PRICE_LIMIT
    ]

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

    # --------------------------------------------------------
    # ЛУЧШИЕ ЦЕНЫ
    # --------------------------------------------------------

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
    # TELEGRAM SUMMARY
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
            "💵 Минимальная найденная цена: нет данных"
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
            "💵 Минимальная найденная цена: нет данных"
        )

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "📊 ИТОГ",
            "━━━━━━━━━━━━━━━━━━",
            f"Подходящих вариантов: {len(all_results)}",
            f"≤ {format_price(PRICE_LIMIT)}: "
            f"{len(cheap_results)}",
            f"🆕 Новых вариантов: {new_count}",
            f"📉 Снижений цены: {price_drop_count}",
        ]
    )

    if cheap_results:
        lines.append("")
        lines.append("🎯 Найдены билеты дешевле лимита.")

    elif all_results:
        lines.append("")
        lines.append(
            "ℹ️ Билетов дешевле лимита нет, "
            "но найдены реальные варианты выше "
            "100 000 ₽."
        )

    else:
        lines.append("")
        lines.append(
            "❌ Подходящих вариантов пока не найдено."
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
    # AVIASALES: ИНФО О КЕШЕ
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
                "тарифов в его Data API кеше.",
            ]
        )

    summary = "\n".join(lines)

    telegram_send(summary)

    # --------------------------------------------------------
    # ЛУЧШИЕ 5 ВАРИАНТОВ
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
# GLOBAL ERROR
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        critical_message = (
            "🚨 Maxim Flight Monitor\n\n"
            "КРИТИЧЕСКАЯ ОШИБКА\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"{traceback.format_exc()[-3000:]}"
        )

        telegram_send(
            critical_message
        )

        raise
