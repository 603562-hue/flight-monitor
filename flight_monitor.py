import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

from fast_flights import FlightData, Passengers, get_flights


# ============================================================
# CONFIG
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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AVIASALES_TOKEN = os.environ.get("AVIASALES_API_TOKEN", "")
AVIASALES_API_URL = (
    "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
)


# ============================================================
# HELPERS
# ============================================================

def safe_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        text = (
            text.replace("₽", "")
            .replace("RUB", "")
            .replace(",", ".")
            .replace(" ", "")
        )

        return float(text)
    except Exception:
        return None


def safe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def fmt_price(value):
    value = safe_float(value)

    if value is None:
        return "—"

    return f"{value:,.0f}".replace(",", " ") + " ₽"


def get_attr(obj, *names, default=None):
    """
    Универсальный доступ как к dataclass/object, так и к dict.
    """
    if obj is None:
        return default

    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]

    for name in names:
        try:
            value = getattr(obj, name)
            return value
        except Exception:
            continue

    return default


def normalize_stops(value):
    """
    Преобразует разные варианты представления пересадок в int.
    """
    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    text = str(value).strip().lower()

    if text in {"nonstop", "direct", "без пересадок"}:
        return 0

    if text in {"1 stop", "one stop", "1 пересадка"}:
        return 1

    if text in {"2 stops", "2 пересадки"}:
        return 2

    digits = "".join(ch for ch in text if ch.isdigit())

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
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return {}


def save_state(state):
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass


def make_key(source, origin, destination, departure, return_date):
    return (
        f"{source}|{origin}|{destination}|"
        f"{departure}|{return_date}"
    )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = (
        f"https://api.telegram.org/bot"
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
    Один round-trip поиск Google Flights.

    Мы намеренно НЕ ограничиваем цену на уровне запроса:
    сначала пытаемся получить самый дешёвый найденный тариф,
    а уже потом применяем PRICE_LIMIT.
    """

    flight_data = [
        FlightData(
            date=departure_date,
            from_airport=origin,
            to_airport=destination,
        ),
        FlightData(
            date=return_date,
            from_airport=destination,
            to_airport=origin,
        ),
    ]

    result = get_flights(
        flight_data=flight_data,
        trip="round-trip",
        seat="economy",
        passengers=PASSENGERS,
    )

    return result


def normalize_google_results(result, origin, destination):
    """
    Приводит Google/fast-flights результаты
    к простому списку словарей.
    """

    flights = get_attr(result, "flights", default=None)

    if flights is None:
        return []

    if not isinstance(flights, (list, tuple)):
        flights = [flights]

    normalized = []

    for flight in flights:
        try:
            price_raw = get_attr(
                flight,
                "price",
                "price_value",
                "amount",
            )

            price = safe_float(price_raw)

            if price is None:
                continue

            airline = get_attr(
                flight,
                "name",
                "airline",
                "airline_name",
                default="",
            )

            departure = get_attr(
                flight,
                "departure",
                "departure_time",
                default="",
            )

            arrival = get_attr(
                flight,
                "arrival",
                "arrival_time",
                default="",
            )

            duration = get_attr(
                flight,
                "duration",
                default="",
            )

            stops_raw = get_attr(
                flight,
                "stops",
                "stop_count",
                "number_of_stops",
            )

            stops = normalize_stops(stops_raw)

            normalized.append(
                {
                    "source": "Google",
                    "origin": origin,
                    "destination": destination,
                    "price": price,
                    "airline": str(airline or ""),
                    "departure": str(departure or ""),
                    "arrival": str(arrival or ""),
                    "duration": str(duration or ""),
                    "stops": stops,
                    "link": "",
                }
            )

        except Exception:
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

    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError(
            "Aviasales returned invalid JSON"
        )

    if data.get("success") is False:
        error_message = data.get("error")

        if isinstance(error_message, dict):
            error_message = json.dumps(
                error_message,
                ensure_ascii=False,
            )

        raise RuntimeError(
            f"Aviasales API error: {error_message or 'unknown error'}"
        )

    return data


def normalize_aviasales_results(
    data,
    origin,
    destination,
    departure_date,
    return_date,
):
    """
    Aviasales /v3/prices_for_dates historically may return:
      data as dict keyed by date
    or
      data as list.

    Поддерживаем оба варианта.
    """

    raw_data = data.get("data")

    if not raw_data:
        return []

    records = []

    if isinstance(raw_data, dict):
        records.extend(raw_data.values())

    elif isinstance(raw_data, list):
        records.extend(raw_data)

    else:
        return []

    normalized = []

    for item in records:
        if not isinstance(item, dict):
            continue

        price = safe_float(
            item.get("price")
        )

        if price is None:
            continue

        found_departure = item.get(
            "departure_at"
        )

        found_return = item.get(
            "return_at"
        )

        transfers = normalize_stops(
            item.get("transfers")
        )

        return_transfers = normalize_stops(
            item.get("return_transfers")
        )

        normalized.append(
            {
                "source": "Aviasales",
                "origin": item.get(
                    "origin_airport"
                )
                or origin,
                "destination": item.get(
                    "destination_airport"
                )
                or destination,
                "price": price,
                "airline": item.get(
                    "airline"
                )
                or "",
                "flight_number": item.get(
                    "flight_number"
                )
                or "",
                "departure": found_departure
                or departure_date,
                "return": found_return
                or return_date,
                "duration": item.get(
                    "duration"
                ),
                "duration_to": item.get(
                    "duration_to"
                ),
                "duration_back": item.get(
                    "duration_back"
                ),
                "stops": transfers,
                "return_stops": return_transfers,
                "link": item.get("link")
                or "",
            }
        )

    normalized.sort(
        key=lambda x: x["price"]
    )

    return normalized


# ============================================================
# URL
# ============================================================

def aviasales_link(relative_link):
    if not relative_link:
        return ""

    if relative_link.startswith("http"):
        return relative_link

    return (
        "https://www.aviasales.ru"
        + relative_link
    )


# ============================================================
# SEARCH ONE COMBINATION
# ============================================================

def run_one_search(
    source,
    origin,
    destination,
    departure_date,
    return_date,
):
    """
    Возвращает:
      {
        results: [...]
        error: None / string
        status: ...
      }
    """

    try:
        if source == "Google":
            raw = search_google(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
            )

            results = normalize_google_results(
                raw,
                origin,
                destination,
            )

        elif source == "Aviasales":
            raw = search_aviasales(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
            )

            results = normalize_aviasales_results(
                raw,
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
# RESULT PROCESSING
# ============================================================

def best_result(results):
    if not results:
        return None

    return min(
        results,
        key=lambda x: x.get("price", float("inf")),
    )


def filter_max_one_stop(results):
    """
    Оставляем варианты, где:
      туда <= 1 пересадки
      обратно <= 1 пересадки

    Если источник не сообщил число пересадок,
    результат НЕ считаем автоматически подходящим.
    """

    output = []

    for result in results:
        stops = result.get("stops")
        return_stops = result.get("return_stops")

        if stops is None:
            # Для Google иногда fast-flights не даёт поле.
            # В этом случае пытаемся принять результат,
            # если строка stops отсутствует только у Google.
            if result.get("source") == "Google":
                output.append(result)
            continue

        if stops > 1:
            continue

        if return_stops is not None and return_stops > 1:
            continue

        output.append(result)

    return output


def update_history(state, result):
    key = make_key(
        result["source"],
        result["origin"],
        result["destination"],
        result.get("departure"),
        result.get("return")
        or "",
    )

    old_price = state.get(key)

    state[key] = {
        "price": result["price"],
        "updated_at": datetime.utcnow().isoformat(),
    }

    return old_price


# ============================================================
# TELEGRAM FORMATTING
# ============================================================

def format_result(result):
    source = result.get("source", "")
    origin = result.get("origin", "")
    destination = result.get("destination", "")
    price = result.get("price")

    airline = result.get("airline") or ""

    flight_number = result.get(
        "flight_number"
    ) or ""

    departure = result.get(
        "departure"
    ) or ""

    return_date = result.get(
        "return"
    ) or ""

    stops = result.get("stops")
    return_stops = result.get("return_stops")

    parts = [
        f"💰 {fmt_price(price)}",
        f"🛫 {origin} → {destination}",
        f"📅 {departure}",
    ]

    if return_date:
        parts.append(
            f"↩️ {return_date}"
        )

    if airline:
        airline_text = airline

        if flight_number:
            airline_text += (
                f" {flight_number}"
            )

        parts.append(
            f"✈️ {airline_text}"
        )

    if stops is not None:
        if return_stops is not None:
            parts.append(
                f"🔄 {stops}/{return_stops} перес."
            )
        else:
            parts.append(
                f"🔄 {stops} перес."
            )

    duration = result.get(
        "duration"
    )

    if duration:
        parts.append(
            f"⏱ {duration}"
        )

    link = result.get("link") or ""

    if source == "Aviasales":
        link = aviasales_link(link)

    if link:
        parts.append(
            f"🔗 {link}"
        )

    return (
        f"🔎 {source}\n"
        + "\n".join(parts)
    )


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

                    result = run_one_search(
                        "Google",
                        origin,
                        destination,
                        departure_date,
                        return_date,
                    )

                    if result["error"]:
                        google_errors += 1

                        errors.append(
                            (
                                "Google",
                                origin,
                                destination,
                                departure_date,
                                return_date,
                                result["error"],
                            )
                        )

                        continue

                    google_successes += 1

                    if not result["results"]:
                        google_empty += 1
                    else:
                        google_results.extend(
                            result["results"]
                        )

    # --------------------------------------------------------
    # AVIASALES
    # --------------------------------------------------------

    for departure_date in DEPARTURE_DATES:
        for return_date in RETURN_DATES:
            for origin in ORIGIN_AIRPORTS:
                for destination in DESTINATIONS:

                    aviasales_searches += 1

                    result = run_one_search(
                        "Aviasales",
                        origin,
                        destination,
                        departure_date,
                        return_date,
                    )

                    if result["error"]:
                        aviasales_errors += 1

                        errors.append(
                            (
                                "Aviasales",
                                origin,
                                destination,
                                departure_date,
                                return_date,
                                result["error"],
                            )
                        )

                        continue

                    aviasales_successes += 1

                    if not result["results"]:
                        aviasales_empty += 1
                    else:
                        aviasales_results.extend(
                            result["results"]
                        )

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    google_filtered = filter_max_one_stop(
        google_results
    )

    aviasales_filtered = filter_max_one_stop(
        aviasales_results
    )

    all_results = (
        google_filtered
        + aviasales_filtered
    )

    all_results.sort(
        key=lambda x: x.get(
            "price",
            float("inf"),
        )
    )

    cheap_results = [
        result
        for result in all_results
        if result.get("price", float("inf"))
        <= PRICE_LIMIT
    ]

    google_best = best_result(
        google_filtered
    )

    aviasales_best = best_result(
        aviasales_filtered
    )

    # --------------------------------------------------------
    # HISTORY
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
    # SUMMARY
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
        f"Ответов без ошибки: {google_successes}",
        f"Технических ошибок: {google_errors}",
        f"Пустых результатов: {google_empty}",
        f"Результатов ≤ {PRICE_LIMIT:,.0f} ₽: "
        f"{sum(1 for x in google_filtered if x.get('price', 10**18) <= PRICE_LIMIT)}"
        .replace(",", " "),
    ]

    if google_best:
        lines.extend(
            [
                f"💵 Минимальная найденная цена: "
                f"{fmt_price(google_best['price'])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "💵 Минимальная найденная цена: нет данных",
                "",
            ]
        )

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━",
            "🔎 AVIASALES",
            "━━━━━━━━━━━━━━━━━━",
            f"Поисков: {aviasales_searches}",
            f"Ответов без ошибки: {aviasales_successes}",
            f"Технических ошибок: {aviasales_errors}",
            f"Пустых результатов: {aviasales_empty}",
            f"Результатов ≤ {PRICE_LIMIT:,.0f} ₽: "
            f"{sum(1 for x in aviasales_filtered if x.get('price', 10**18) <= PRICE_LIMIT)}"
            .replace(",", " "),
        ]
    )

    if aviasales_best:
        lines.extend(
            [
                f"💵 Минимальная найденная цена: "
                f"{fmt_price(aviasales_best['price'])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "💵 Минимальная найденная цена: нет данных",
                "",
            ]
        )

    # --------------------------------------------------------
    # GLOBAL STATUS
    # --------------------------------------------------------

    if cheap_results:
        lines.extend(
            [
                "🎯 Найдены варианты ≤ "
                f"{fmt_price(PRICE_LIMIT)}:",
                str(len(cheap_results)),
            ]
        )
    else:
        lines.extend(
            [
                f"❌ Вариантов ≤ {fmt_price(PRICE_LIMIT)} не найдено.",
            ]
        )

    if all_results:
        lines.extend(
            [
                "",
                f"📊 Всего найдено подходящих вариантов: "
                f"{len(all_results)}",
            ]
        )

    lines.extend(
        [
            "",
            f"🆕 Новых вариантов: {new_count}",
            f"📉 Снижений цены: {price_drop_count}",
        ]
    )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    if errors:
        lines.extend(
            [
                "",
                "⚠️ ТЕХНИЧЕСКИЕ ОШИБКИ",
            ]
        )

        max_error_lines = 15

        for index, error in enumerate(
            errors[:max_error_lines],
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
                f"{origin}->{destination} "
                f"{departure_date}->{return_date}: "
                f"{message}"
            )

        if len(errors) > max_error_lines:
            lines.append(
                f"... и ещё {len(errors) - max_error_lines}"
            )

    # --------------------------------------------------------
    # EXPLANATION WHEN AVIASALES EMPTY
    # --------------------------------------------------------

    if (
        aviasales_successes > 0
        and aviasales_empty > 0
    ):
        lines.extend(
            [
                "",
                "ℹ️ Aviasales отвечает корректно, "
                "но для части запросов сейчас нет "
                "цен в его кеше за последние 48 часов.",
            ]
        )

    summary = "\n".join(lines)

    telegram_send(summary)

    # --------------------------------------------------------
    # BEST RESULTS
    # --------------------------------------------------------

    sent = 0

    for result in all_results[:5]:
        text = format_result(result)

        telegram_send(text)

        sent += 1

    print(summary)

    for result in all_results[:5]:
        print(
            "\n" + format_result(result)
        )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        error_text = (
            "🚨 Maxim Flight Monitor — КРИТИЧЕСКАЯ ОШИБКА\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"{traceback.format_exc()[-3000:]}"
        )

        telegram_send(error_text)

        raise
