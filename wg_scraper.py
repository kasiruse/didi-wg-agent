import asyncio
import json
import os
from typing import List, Dict, Optional
from playwright.async_api import async_playwright

SEEN_IDS_FILE = "sessions/seen_listings.json"
SESSION_PATH = "sessions/user_session.json"

def load_seen_ids() -> set:
    if os.path.exists(SEEN_IDS_FILE):
        try:
            with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_ids(seen_ids: set):
    os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f)

class WGScraper:
    def __init__(self, search_url: str):
        self.search_url = search_url
        self.seen_ids = load_seen_ids()

    async def _create_context(self, browser):
        context_kwargs = {
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "locale": "de-DE",
            "timezone_id": "Europe/Berlin"
        }
        if os.path.exists(SESSION_PATH):
            context_kwargs["storage_state"] = SESSION_PATH
        return await browser.new_context(**context_kwargs)

    async def fetch_new_listings(self) -> List[Dict]:
        new_listings = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await self._create_context(browser)
            page = await context.new_page()

            try:
                print(f"🔍 Fetching listings from: {self.search_url}")
                await page.goto(self.search_url, wait_until="domcontentloaded", timeout=45000)

                # Dismiss cookie banner if present
                try:
                    accept_btn = page.locator("#cmpwelcomebtnyes, button:has-text('Akzeptieren'), button:has-text('Alle akzeptieren')")
                    if await accept_btn.first.is_visible(timeout=3000):
                        await accept_btn.first.click()
                except Exception:
                    pass

                await page.wait_for_selector(".wgg_card", timeout=10000)
                cards = await page.locator(".wgg_card").all()

                for card in cards:
                    card_class = await card.get_attribute("class") or ""
                    if "sponsor" in card_class.lower():
                        continue

                    listing_id = await card.get_attribute("data-id")
                    if not listing_id or listing_id in self.seen_ids:
                        continue

                    title_elem = card.locator(".truncate_title a")
                    if await title_elem.count() == 0:
                        continue

                    title = (await title_elem.inner_text()).strip()
                    href = await title_elem.get_attribute("href")
                    detail_url = f"https://www.wg-gesucht.de/{href}" if href and not href.startswith("http") else href
                    summary_text = (await card.inner_text()).strip()

                    new_listings.append({
                        "id": listing_id,
                        "title": title,
                        "url": detail_url,
                        "summary_text": summary_text
                    })

                # Fetch full descriptions
                for item in new_listings:
                    print(f"📄 Scraping details for listing ID: {item['id']}")
                    await page.goto(item["url"], wait_until="domcontentloaded", timeout=30000)

                    try:
                        desc_elem = page.locator("#freitext, .section_freitexte")
                        if await desc_elem.first.is_visible(timeout=4000):
                            item["full_description"] = (await desc_elem.first.inner_text()).strip()
                        else:
                            item["full_description"] = item["summary_text"]
                    except Exception:
                        item["full_description"] = item["summary_text"]

                    self.seen_ids.add(item["id"])
                    await asyncio.sleep(2)

                save_seen_ids(self.seen_ids)

            except Exception as e:
                print(f"❌ Error during scraping: {e}")
            finally:
                await browser.close()

        return new_listings

    async def send_message_to_listing(self, listing_url: str, message_text: str) -> bool:
        """
        Sends an application message directly to the listing owner
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await self._create_context(browser)
            page = await context.new_page()

            try:
                print(f"📨 Navigating to listing: {listing_url}")
                await page.goto(listing_url, wait_until="domcontentloaded", timeout=45000)

                # Click contact button
                contact_btn = page.locator("a:has-text('Nachricht senden'), button:has-text('Nachricht senden')")
                if await contact_btn.first.is_visible(timeout=5000):
                    await contact_btn.first.click()
                    await page.wait_for_load_state("domcontentloaded")

                # Fill the message text area
                textarea = page.locator("#svalidated_message, textarea[name='message']")
                await textarea.wait_for(state="visible", timeout=10000)
                await textarea.fill(message_text)

                # Click send message button
                submit_btn = page.locator("#create_message, button[type='submit']:has-text('Senden')")
                await submit_btn.click()
                await page.wait_for_timeout(3000)

                print(f"✅ Message sent successfully to: {listing_url}")
                return True
            except Exception as e:
                print(f"❌ Failed to send message: {e}")
                return False
            finally:
                await browser.close()
