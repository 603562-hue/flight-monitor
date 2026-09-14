import json
import os
import traceback
from datetime import datetime, timezone
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

def now_utc_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


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


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception:
        pass

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
    Round-trip поиск через текущий fast-flights.

    Используем именно ту схему, которая уже работает
    в текущем проекте:
    create_query(..., trip="round-trip")
    + get_flights(query).
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


def get_segment_airport_code(
    segment,
    attribute,
):
    try:
        airport = getattr(
            segment,
            attribute,
            None,
        )

        if airport is None:
            return ""

        code = getattr(
            airport,
            "code",
            None,
        )

        return str(code or "")

    except Exception:
        return ""


def get_flight_segments(flight):
    try:
        segments = getattr(
            flight,
            "flights",
            [],
        )

        if segments is None:
            return []

        return list(segments)

    except Exception:
        return []


def count_stops(segments):
    if not segments:
        return None

    return max(
        len(segments) - 1,
        0,
    )


def normalize_google_results(
    raw_results,
    origin,
    destination,
    departure_date,
    return_date,
):
    normalized = []

    for flight in raw_results:
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

            segments = get_flight_segments(
                flight
            )

            airlines = getattr(
                flight,
                "airlines",
                [],
            )

            if airlines is None:
                airlines = []

            airlines = [
                str(item)
                for item in airlines
            ]

            outbound_segments = []
            return_segments = []

            outbound_finished = False

            for segment in segments:
                to_code = get_segment_airport_code(
                    segment,
                    "to_airport",
                )

                if not outbound_finished:
                    outbound_segments.append(
                        segment
                    )

                    if to_code == destination:
                        outbound_finished = True

                else:
                    return_segments.append(
                        segment
                    )

            # Защита на случай, если parser Google
            # не позволил корректно разделить плечи.
            if (
                not outbound_segments
                or not return_segments
            ):
                if len(segments) >= 2:
                    midpoint = (
                        len(segments) // 2
                    )

                    outbound_segments = (
                        segments[:midpoint]
                    )

                    return_segments = (
                        segments[midpoint:]
                    )

            outbound_stops = count_stops(
                outbound_segments
            )

            return_stops = count_stops(
                return_segments
            )

            normalized.append(
                {
                    "source": "Google",
                    "origin": origin,
                    "destination": destination,
                    "departure_date": (
                        departure_date
                    ),
                    "return_date": (
                        return_date
                    ),
                    "price": price,
                    "airlines": airlines,
                    "outbound_stops": (
                        outbound_stops
                    ),
                    "return_stops": (
                        return_stops
                    ),
                }
            )

        except Exception:
            # Один кривой результат Google
            # не ломает весь запрос.
            continue

    normalized.sort(
        key=lambda item: item["price"]
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
            "Aviasales API error: "
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

    normalized = []

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
            outbound_stops = (
                int(outbound_stops)
                if outbound_stops is not None
                else None
            )
        except Exception:
            outbound_stops = None

        try:
            return_stops = (
                int(return_stops)
                if return_stops is not None
                else None
            )
        except Exception:
            return_stops = None

        normalized.append(
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
                "outbound_stops": (
                    outbound_stops
                ),
                "return_stops": (
                    return_stops
                ),
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

    normalized.sort(
        key=lambda item: item["price"]
    )

    return normalized


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
# ФИЛЬТР ПЕРЕСАДОК
# ============================================================

def is_max_one_stop(result):
    outbound = result.get(
        "outbound_stops"
    )

    returning = result.get(
        "return_stops"
    )

    if (
        outbound is not None
        and outbound > 1
    ):
        return False

    if (
        returning is not None
        and returning > 1
    ):
        return False

    return True


# ============================================================
# УДАЛЕНИЕ ДУБЛИКАТОВ
# ============================================================

def deduplicate_results(results):
    """
    Убирает повторяющиеся записи API.

    Одинаковым считается вариант с одинаковыми:
    источник
    маршрут
    датами
    авиакомпанией/рейсом
    количеством пересадок.
    """

    unique = {}

    for result in results:
        key = (
            result.get("source", ""),
            result.get("origin", ""),
            result.get("destination", ""),
            result.get("departure_date", ""),
            result.get("return_date", ""),
            result.get("airline", ""),
            result.get("flight_number", ""),
            tuple(
                result.get("airlines", [])
            ),
            result.get("outbound_stops"),
            result.get("return_stops"),
        )

        current = unique.get(key)

        if current is None:
            unique[key] = result
            continue

        current_price = to_float(
            current.get("price")
        )

        new_price = to_float(
            result.get("price")
        )

        if (
            new_price is not None
            and (
                current_price is None
                or new_price < current_price
            )
        ):
            unique[key] = result

    result_list = list(
        unique.values()
    )

    result_list.sort(
        key=lambda item: item["price"]
    )

    return result_list


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
            result.get("airline", ""),
            result.get("flight_number", ""),
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
        "updated_at": now_utc_iso(),
    }

    return old_price


# ============================================================
# ФОРМАТ ОБЫЧНОГО РЕЗУЛЬТАТА
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
# ФОРМАТ УВЕДОМЛЕНИЯ
# ============================================================

def format_alert(
    result,
    alert_type,
    old_price=None,
):
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
        outbound_stops is not None
        or return_stops is not None
    ):
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

    else:
        stops_text = (
            "🔄 Пересадки: нет данных"
        )

    if alert_type == "limit":
        title = "🔥 ЦЕНА НИЖЕ ЛИМИТА"

    elif alert_type == "new":
        title = (
            "🆕 НОВЫЙ ВАРИАНТ "
            "≤ 100 000 ₽"
        )

    elif alert_type == "drop":
        title = "📉 ЦЕНА СНИЗИЛАСЬ"

    else:
        title = "✈️ ИЗМЕНЕНИЕ ЦЕНЫ"

    lines = [
        title,
        "",
        f"💰 Сейчас: {format_price(price)}",
    ]

    if old_price is not None:
        difference = (
            old_price - price
        )

        if difference > 0:
            lines.append(
                "⬇️ Снижение: "
                f"{format_price(difference)}"
            )

        lines.append(
            "Предыдущая цена: "
            f"{format_price(old_price)}"
        )

    lines.extend(
        [
            "",
            f"🔎 {source}",
            f"🛫 {origin} → {destination}",
            f"📅 {departure_date}",
            f"↩️ {return_date}",
            stops_text,
        ]
    )

    airlines = result.get(
        "airlines"
    )

    if airlines:
        lines.append(
            "✈️ "
            + ", ".join(airlines)
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
        if not str(link).startswith(
            "http"
        ):
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

    # ========================================================
    # GOOGLE
    # ========================================================

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

    # ========================================================
    # AVIASALES
    # ========================================================

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

    # ========================================================
    # ФИЛЬТР ПЕРЕСАДОК
    # ========================================================

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

    # ========================================================
    # УДАЛЕНИЕ ДУБЛИКАТОВ
    # ========================================================

    google_filtered = deduplicate_results(
        google_filtered
    )

    aviasales_filtered = deduplicate_results(
        aviasales_filtered
    )

    # ========================================================
    # СОРТИРОВКА
    # ========================================================

    google_filtered.sort(
        key=lambda item: item["price"]
    )

    aviasales_filtered.sort(
        key=lambda item: item["price"]
    )

    all_results = (
        google_filtered
        + aviasales_filtered
    )

    all_results.sort(
        key=lambda item: item["price"]
    )

    # ========================================================
    # ЦЕНЫ
    # ========================================================

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

    global_best = (
        all_results[0]
        if all_results
        else None
    )

    # ========================================================
    # ИСТОРИЯ И СОБЫТИЯ
    # ========================================================

    new_count = 0
    price_drop_count = 0

    price_drops = []
    limit_hits = []
    new_cheap = []

    for result in all_results:
        old_price = update_history(
            state,
            result,
        )

        current_price = result.get(
            "price"
        )

        # ----------------------------------------------------
        # НОВЫЙ ВАРИАНТ
        # ----------------------------------------------------

        if old_price is None:
            new_count += 1

            if (
                current_price is not None
                and current_price <= PRICE_LIMIT
            ):
                new_cheap.append(
                    result
                )

            continue

        # ----------------------------------------------------
        # СНИЖЕНИЕ
        # ----------------------------------------------------

        if (
            current_price is not None
            and current_price < old_price
        ):
            price_drop_count += 1

            price_drops.append(
                (
                    result,
                    old_price,
                )
            )

            # ------------------------------------------------
            # ПЕРЕСЕЧЕНИЕ ЛИМИТА
            # ------------------------------------------------

            if (
                old_price > PRICE_LIMIT
                and current_price <= PRICE_LIMIT
            ):
                limit_hits.append(
                    (
                        result,
                        old_price,
                    )
                )

    save_state(state)

    # ========================================================
    # ВАЖНЫЕ УВЕДОМЛЕНИЯ
    # ========================================================

    # --------------------------------------------------------
    # 1. ПЕРЕСЕЧЕНИЕ ПОРОГА 100 000 ₽
    # --------------------------------------------------------

    for result, old_price in sorted(
        limit_hits,
        key=lambda item: (
            item[0]["price"]
        ),
    )[:5]:

        telegram_send(
            format_alert(
                result,
                "limit",
                old_price,
            )
        )

    # --------------------------------------------------------
    # 2. НОВЫЕ ВАРИАНТЫ ≤100 000 ₽
    # --------------------------------------------------------

    already_sent_keys = {
        history_key(result)
        for result, _ in limit_hits
    }

    for result in sorted(
        new_cheap,
        key=lambda item: item["price"],
    )[:5]:

        key = history_key(result)

        if key in already_sent_keys:
            continue

        telegram_send(
            format_alert(
                result,
                "new",
            )
        )

    # --------------------------------------------------------
    # 3. ДРУГИЕ СНИЖЕНИЯ
    # --------------------------------------------------------

    important_drops = sorted(
        price_drops,
        key=lambda item: (
            item[1]
            - item[0]["price"]
        ),
        reverse=True,
    )

    for result, old_price in (
        important_drops[:5]
    ):

        # Для перехода через 100k уже было
        # отправлено специальное сообщение.
        if (
            old_price > PRICE_LIMIT
            and result["price"] <= PRICE_LIMIT
        ):
            continue

        telegram_send(
            format_alert(
                result,
                "drop",
                old_price,
            )
        )

    # ========================================================
    # КОРОТКИЙ TELEGRAM SUMMARY
    # ========================================================

    lines = [
        "✈️ Maxim Flight Monitor",
        "",
        "26/27.12.2026 → "
        "09/10/11.01.2027",
        "Москва: SVO / DME / VKO",
        "BKK / UTP · Economy · ≤1 пересадка",
        "",
        "━━━━━━━━━━━━━━━━━━",
    ]

    if aviasales_best:
        lines.append(
            "🔎 Aviasales: "
            f"{format_price(aviasales_best['price'])}"
        )
    else:
        lines.append(
            "🔎 Aviasales: нет данных"
        )

    if google_best:
        lines.append(
            "🔎 Google: "
            f"{format_price(google_best['price'])}"
        )
    else:
        lines.append(
            "🔎 Google: нет данных"
        )

    if global_best:
        lines.append(
            "🏆 Минимум: "
            f"{format_price(global_best['price'])}"
        )
    else:
        lines.append(
            "🏆 Минимум: нет данных"
        )

    lines.extend(
        [
            "",
            "🎯 ≤100 000 ₽: "
            f"{len(cheap_results)}",
            "📉 Снижений: "
            f"{price_drop_count}",
            "🆕 Новых: "
            f"{new_count}",
            "",
            "Google: "
            f"{google_successes}/"
            f"{google_searches} успешно",
            "Aviasales: "
            f"{aviasales_successes}/"
            f"{aviasales_searches} успешно",
        ]
    )

    if google_errors:
        lines.append(
            "⚠️ Google ошибок: "
            f"{google_errors}"
        )

    if aviasales_empty:
        lines.append(
            "ℹ️ Aviasales без тарифа: "
            f"{aviasales_empty}"
        )

    if limit_hits:
        lines.extend(
            [
                "",
                "🔥 Есть варианты, "
                "перешедшие ниже лимита!",
            ]
        )

    summary = "\n".join(lines)

    telegram_send(summary)

    # ========================================================
    # LOG
    # ========================================================

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
