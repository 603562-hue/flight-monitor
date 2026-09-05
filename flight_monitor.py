import os
import requests
from playwright.sync_api import sync_playwright

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

URL = "https://www.ozon.ru/travel/flight/moskva-mow/suvarnabhumi-bkk/"

def telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text[:3900]},
        timeout=30
    )

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="ru-RU")
    page = context.new_page()

    seen = []

    def capture(request):
        u = request.url
        low = u.lower()
        keys = ["api", "flight", "travel", "search", "graphql", "bff"]
        if any(k in low for k in keys):
            item = request.method + " " + u
            if item not in seen:
                seen.append(item)

    page.on("request", capture)

    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(15000)

    resources = page.evaluate(
        "performance.getEntriesByType('resource').map(x => x.name)"
    )

    for u in resources:
        low = u.lower()
        if any(k in low for k in ["api", "flight", "travel", "search", "graphql", "bff"]):
            item = "RESOURCE " + u
            if item not in seen:
                seen.append(item)

    text = page.locator("body").inner_text()

    print("PAGE:", page.url)
    print("TITLE:", page.title())
    print("NETWORK:")
    for x in seen:
        print(x)

    message = (
        "OZON NETWORK CAPTURE\n\n"
        "PAGE: " + page.url + "\n"
        "TITLE: " + page.title() + "\n\n"
        + "\n".join(seen[:60])
    )

    telegram(message)

    browser.close()
