import os
import json
import random
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

SEEN_FILE = "sessions/seen_listings.json"
SESSION_FILE = "sessions/user_session.json"

def _load_seen_listings() -> set:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def _save_seen_listings(seen: set):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)

class WGScraper:
    def __init__(self, search_url: str):
        self.search_url = search_url
        self.seen_listings = _load_seen_listings()

    async def fetch_new_listings(self) -> list:
        new_items = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            print(f"🔍 Fetching listings from: {self.search_url}")
            await page.goto(self.search_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2.5, 4.5))

            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            listing_cards = soup.select(".wgg_card") or soup.select(".offer_list_item")
            for card in listing_cards:
                card_id = card.get("data-id") or card.get("id")
                if not card_id:
                    link_tag = card.select_one("a[href*='.html']")
                    if link_tag and link_tag.get("href"):
                        href = link_tag.get("href")
                        card_id = href.split(".")[-2] if len(href.split(".")) >= 3 else href

                if card_id and card_id not in self.seen_listings:
                    link_elem = card.select_one("a[href*='.html']")
                    if not link_elem:
                        continue
                    url = link_elem.get("href")
                    if not url.startswith("http"):
                        url = f"https://www.wg-gesucht.de/{url.lstrip('/')}"

                    title = card.get_text(separator=" ", strip=True)[:100]

                    print(f"📄 Scraping details for listing ID: {card_id}")
                    detail_page = await context.new_page()
                    try:
                        await detail_page.goto(url, timeout=45000, wait_until="domcontentloaded")
                        await asyncio.sleep(random.uniform(1.8, 3.5))
                        detail_content = await detail_page.content()
                        detail_soup = BeautifulSoup(detail_content, "html.parser")
                        description_text = detail_soup.get_text(separator="\n", strip=True)
                    except Exception as e:
                        description_text = title
                        print(f"⚠️ Failed to fetch details for {card_id}: {e}")
                    finally:
                        await detail_page.close()

                    self.seen_listings.add(card_id)
                    _save_seen_listings(self.seen_listings)

                    new_items.append({
                        "id": str(card_id),
                        "title": title,
                        "url": url,
                        "full_description": description_text
                    })

                    # Short natural pause between opening listing pages
                    await asyncio.sleep(random.uniform(1.0, 2.5))

            await browser.close()
        return new_items

    async def send_message_to_listing(self, url: str, message: str) -> bool:
        if not os.path.exists(SESSION_FILE):
            print("❌ Authentication session not found.")
            return False

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=SESSION_FILE)
            page = await context.new_page()

            try:
                print(f"🌐 Navigating to listing: {url}")
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(2.0, 4.0))

                message_btn = page.locator("a:has-text('Nachricht senden'), button:has-text('Nachricht senden')")
                if await message_btn.count() > 0:
                    await message_btn.first.click()
                    await asyncio.sleep(random.uniform(2.0, 3.5))

                textarea = page.locator("textarea#message_input, textarea[name='message'], textarea")
                if await textarea.count() > 0:
                    await textarea.first.click()
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    # Simulating natural human typing speed
                    await textarea.first.fill(message)
                    await asyncio.sleep(random.uniform(2.5, 4.5))

                    submit_btn = page.locator("button[type='submit']:has-text('Nachricht senden'), input[type='submit']")
                    if await submit_btn.count() > 0:
                        await submit_btn.first.click()
                        await asyncio.sleep(random.uniform(3.0, 5.0))
                        print(f"✅ Successfully sent message to {url}")
                        await browser.close()
                        return True

                print(f"⚠️ Message form elements not found on {url}")
                await browser.close()
                return False

            except Exception as e:
                print(f"❌ Error sending message: {e}")
                await browser.close()
                return False
