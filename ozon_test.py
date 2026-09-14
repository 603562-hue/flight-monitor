import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright


ORIGIN = "DME"
DESTINATION = "BKK"

DEPARTURE_DATE = "2026-12-27"
RETURN_DATE = "2027-01-11"

OZON_ROUTE_URL = (
    "https://www.ozon.ru/travel/flight/"
    "moskva-mow/bangkok-bkk/"
)

SCREENSHOT_FILE = Path("ozon_test.png")


def clean_text(text):
    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def extract_prices(text):
    prices = []

    # ₽
    for match in re.findall(
        r"(\d[\d\s]{2,})\s*₽",
        text,
    ):
        value = match.replace(" ", "")

        try:
            prices.append(int(value))
        except ValueError:
            pass

    # Цены вида "от 123 456"
    for match in re.findall(
        r"(?:от|цена)\s+(\d[\d\s]{2,})",
        text,
        flags=re.IGNORECASE,
    ):
        value = match.replace(" ", "")

        try:
            prices.append(int(value))

        except ValueError:
            pass

    return sorted(set(prices))


async def dump_inputs(page):
    inputs = await page.locator("input").all()

    print("")
    print("========== INPUTS ==========")
    print(
        f"Количество input: {len(inputs)}"
    )

    for index, element in enumerate(inputs):
        try:
            info = {
                "index": index,
                "type": await element.get_attribute(
                    "type"
                ),
                "name": await element.get_attribute(
                    "name"
                ),
                "placeholder": await element.get_attribute(
                    "placeholder"
                ),
                "aria-label": await element.get_attribute(
                    "aria-label"
                ),
                "value": await element.input_value(),
            }

            print(
                json.dumps(
                    info,
                    ensure_ascii=False,
                )
            )

        except Exception as exc:
            print(
                f"input[{index}] error: {exc}"
            )


async def try_fill_route(page):
    inputs = page.locator("input")

    count = await inputs.count()

    # Сначала пытаемся найти поля по aria-label /
    # placeholder / name.
    field_candidates = {
        "origin": [
            "Откуда",
            "origin",
            "from",
        ],
        "destination": [
            "Куда",
            "destination",
            "to",
        ],
    }

    async def find_field(words):
        for index in range(count):
            element = inputs.nth(index)

            attrs = [
                await element.get_attribute(
                    "placeholder"
                ),
                await element.get_attribute(
                    "aria-label"
                ),
                await element.get_attribute(
                    "name"
                ),
            ]

            blob = " ".join(
                x or ""
                for x in attrs
            ).lower()

            for word in words:
                if word.lower() in blob:
                    return element

        return None

    origin_field = await find_field(
        field_candidates["origin"]
    )

    destination_field = await find_field(
        field_candidates["destination"]
    )

    if not origin_field or not destination_field:
        print(
            "Не удалось автоматически найти "
            "поля Откуда/Куда."
        )

        return False

    print(
        "Нашёл поля маршрута."
    )

    try:
        await origin_field.click()
        await origin_field.fill("")
        await origin_field.type(
            "Москва",
            delay=50,
        )

        await page.wait_for_timeout(1500)

        # Ищем выпадающие варианты.
        print(
            "Текст страницы после ввода Москвы:"
        )

        body_text = clean_text(
            await page.locator("body").inner_text()
        )

        print(
            body_text[-3000:]
        )

        # Обычно Ozon показывает вариант
        # "Москва" / "MOW".
        possible = page.get_by_text(
            re.compile(
                r"Москва.*(?:MOW|Россия)",
                re.IGNORECASE,
            )
        )

        if await possible.count():
            await possible.first.click()
        else:
            # Fallback: первая достаточно короткая
            # строка с Москвой.
            possible = page.get_by_text(
                re.compile(
                    r"Москва",
                    re.IGNORECASE,
                )
            )

            if await possible.count():
                await possible.last.click()

        await destination_field.click()
        await destination_field.fill("")
        await destination_field.type(
            "Бангкок",
            delay=50,
        )

        await page.wait_for_timeout(1500)

        body_text = clean_text(
            await page.locator("body").inner_text()
        )

        print(
            "Текст страницы после ввода Бангкока:"
        )

        print(
            body_text[-3000:]
        )

        possible = page.get_by_text(
            re.compile(
                r"Бангкок.*(?:BKK|Таиланд)",
                re.IGNORECASE,
            )
        )

        if await possible.count():
            await possible.first.click()
        else:
            possible = page.get_by_text(
                re.compile(
                    r"Бангкок",
                    re.IGNORECASE,
                )
            )

            if await possible.count():
                await possible.last.click()

        return True

    except Exception as exc:
        print(
            f"Ошибка заполнения маршрута: {exc}"
        )

        return False


async def click_search(page):
    patterns = [
        re.compile(
            r"Найти билеты",
            re.IGNORECASE,
        ),
        re.compile(
            r"Найти",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        locator = page.get_by_text(
            pattern
        )

        if await locator.count():
            try:
                await locator.last.click()

                print(
                    f"Нажата кнопка: {pattern.pattern}"
                )

                await page.wait_for_timeout(
                    7000
                )

                return True

            except Exception:
                pass

    buttons = page.locator("button")

    for index in range(
        await buttons.count()
    ):
        button = buttons.nth(index)

        try:
            text = clean_text(
                await button.inner_text()
            )

            if (
                "найти" in text.lower()
                or "билет" in text.lower()
            ):
                await button.click()

                print(
                    f"Нажата кнопка: {text}"
                )

                await page.wait_for_timeout(
                    7000
                )

                return True

        except Exception:
            continue

    return False


async def main():
    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = await context.new_page()

        print(
            "Открываем Ozon Travel:"
        )
        print(
            OZON_ROUTE_URL
        )

        try:
            response = await page.goto(
                OZON_ROUTE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print(
                f"HTTP status: "
                f"{response.status if response else 'unknown'}"
            )

        except Exception as exc:
            print(
                f"Ошибка открытия Ozon: {exc}"
            )

            await page.screenshot(
                path=str(SCREENSHOT_FILE),
                full_page=True,
            )

            await browser.close()
            raise

        await page.wait_for_timeout(
            5000
        )

        title = await page.title()

        print(
            f"Заголовок: {title}"
        )

        body_text = clean_text(
            await page.locator("body").inner_text()
        )

        print("")
        print(
            "========== НАЧАЛЬНЫЙ ТЕКСТ =========="
        )
        print(
            body_text[:8000]
        )

        # ----------------------------------------------------
        # Блокировка / CAPTCHA
        # ----------------------------------------------------

        block_markers = [
            "captcha",
            "капча",
            "робот",
            "проверка",
            "доступ ограничен",
            "докажите, что вы не робот",
        ]

        body_lower = body_text.lower()

        detected_block = any(
            marker in body_lower
            for marker in block_markers
        )

        if detected_block:
            print("")
            print(
                "❌ Ozon показывает CAPTCHA/блокировку."
            )

            await page.screenshot(
                path=str(SCREENSHOT_FILE),
                full_page=True,
            )

            await browser.close()
            return

        await dump_inputs(page)

        # ----------------------------------------------------
        # Пробуем заполнить маршрут
        # ----------------------------------------------------

        route_ok = await try_fill_route(
            page
        )

        if route_ok:
            print(
                "✅ Маршрут удалось заполнить."
            )

        else:
            print(
                "⚠️ Маршрут автоматически заполнить "
                "не удалось."
            )

        await dump_inputs(page)

        # ----------------------------------------------------
        # Пытаемся выполнить поиск
        # ----------------------------------------------------

        search_ok = await click_search(
            page
        )

        if search_ok:
            print(
                "✅ Поиск запущен."
            )

        else:
            print(
                "⚠️ Кнопку поиска автоматически "
                "найти не удалось."
            )

        await page.wait_for_timeout(
            5000
        )

        final_text = clean_text(
            await page.locator("body").inner_text()
        )

        print("")
        print(
            "========== ИТОГОВЫЙ ТЕКСТ =========="
        )
        print(
            final_text[:15000]
        )

        prices = extract_prices(
            final_text
        )

        print("")
        print(
            "========== НАЙДЕННЫЕ ЦЕНЫ =========="
        )

        if prices:
            for price in prices[:20]:
                print(
                    f"{price:,}".replace(",", " ")
                    + " ₽"
                )

        else:
            print(
                "Цены автоматически не найдены."
            )

        await page.screenshot(
            path=str(SCREENSHOT_FILE),
            full_page=True,
        )

        print("")
        print(
            f"Screenshot: {SCREENSHOT_FILE}"
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
