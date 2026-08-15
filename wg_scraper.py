import os
import re
import json
import random
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import yaml

SEEN_FILE = "sessions/seen_listings.json"
SESSION_FILE = "sessions/user_session.json"

def _load_config() -> dict:
    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

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

def _build_page_url(base_url: str, page_idx: int) -> str:
    if page_idx == 0:
        return base_url
    pattern = r"\.1\.\d+\.html"
    if re.search(pattern, base_url):
        return re.sub(pattern, f".1.{page_idx}.html", base_url)
    return base_url.replace(".html", f".1.{page_idx}.html")

class WGScraper:
    def __init__(self, search_url: str):
        self.search_url = search_url
        self.seen_listings = _load_seen_listings()

    async def fetch_new_listings(self) -> list:
        config = _load_config()
        max_pages = config.get("max_pages_to_crawl", 3)
        max_per_cycle = config.get("max_listings_per_cycle", 6)
        scrape_delay_min = config.get("listing_scrape_delay_min", 7)
        scrape_delay_max = config.get("listing_scrape_delay_max", 13)

        self.seen_listings = _load_seen_listings()
        new_items = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1920,1080"
                ]
            )
            context = await browser.new_context(
                storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="de-DE",
                timezone_id="Europe/Berlin"
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()

            for page_idx in range(max_pages):
                target_url = _build_page_url(self.search_url, page_idx)
                print(f"🔍 [Page {page_idx + 1}/{max_pages}] Scanning: {target_url}", flush=True)

                try:
                    await page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(3.5, 6.0))
                except Exception as e:
                    print(f"⚠️ Failed to load page {page_idx + 1}: {e}", flush=True)
                    break

                content = await page.content()
                if "cf-browser-verification" in content or "Ray ID:" in content or "Just a moment..." in content:
                    print("🚨 Cloudflare Challenge detected! Stopping page crawl...", flush=True)
                    break

                soup = BeautifulSoup(content, "html.parser")
                listing_cards = soup.select(".wgg_card") or soup.select(".offer_list_item")

                for card in listing_cards:
                    if len(new_items) >= max_per_cycle:
                        print(f"🛑 Reached cycle limit ({max_per_cycle} listings). Moving to analysis.", flush=True)
                        break

                    card_id = card.get("data-id") or card.get("id")
                    if not card_id:
                        link_tag = card.select_one("a[href*='.html']")
                        if link_tag and link_tag.get("href"):
                            href = link_tag.get("href")
                            card_id = href.split(".")[-2] if len(href.split(".")) >= 3 else href

                    if not card_id or "shop" in str(card_id).lower() or not str(card_id).isdigit():
                        continue

                    if card_id not in self.seen_listings:
                        link_elem = card.select_one("a[href*='.html']")
                        if not link_elem:
                            continue
                        url = link_elem.get("href")
                        if not url.startswith("http"):
                            url = f"https://www.wg-gesucht.de/{url.lstrip('/')}"

                        title = card.get_text(separator=" ", strip=True)[:100]

                        # Pre-delay before opening individual listing
                        scrape_wait = random.uniform(scrape_delay_min, scrape_delay_max)
                        print(f"⏳ Waiting {scrape_wait:.1f}s before scraping listing {card_id}...", flush=True)
                        await asyncio.sleep(scrape_wait)

                        print(f"📄 Scraping details for listing ID: {card_id}", flush=True)
                        detail_page = await context.new_page()
                        try:
                            await detail_page.goto(url, timeout=45000, wait_until="domcontentloaded")

                            # Human-like micro-scroll
                            await detail_page.evaluate(f"window.scrollBy(0, {random.randint(250, 600)});")
                            await asyncio.sleep(random.uniform(2.5, 4.0))

                            detail_content = await detail_page.content()
                            detail_soup = BeautifulSoup(detail_content, "html.parser")
                            description_text = detail_soup.get_text(separator="\n", strip=True)
                        except Exception as e:
                            description_text = title
                            print(f"⚠️ Failed to fetch details for {card_id}: {e}", flush=True)
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

                if len(new_items) >= max_per_cycle:
                    break

                # Inter-page transition pause
                page_wait = random.uniform(5.0, 9.0)
                print(f"😴 Resting {page_wait:.1f}s before fetching next search page...", flush=True)
                await asyncio.sleep(page_wait)

            await browser.close()
        return new_items

    async def send_message_to_listing(self, url: str, message: str) -> bool:
        if not os.path.exists(SESSION_FILE):
            print("❌ Authentication session not found.", flush=True)
            return False

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                storage_state=SESSION_FILE,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()

            try:
                print(f"🌐 Navigating to listing: {url}", flush=True)
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(3.0, 5.0))

                message_btn = page.locator("a:has-text('Nachricht senden'), button:has-text('Nachricht senden')")
                if await message_btn.count() > 0:
                    await message_btn.first.click()
                    await asyncio.sleep(random.uniform(2.5, 4.0))

                textarea = page.locator("textarea#message_input, textarea[name='message'], textarea")
                if await textarea.count() > 0:
                    await textarea.first.click()
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    await textarea.first.fill(message)
                    await asyncio.sleep(random.uniform(2.5, 4.5))

                    submit_btn = page.locator("button[type='submit']:has-text('Nachricht senden'), input[type='submit']")
                    if await submit_btn.count() > 0:
                        await submit_btn.first.click()
                        await asyncio.sleep(random.uniform(3.0, 5.0))
                        print(f"✅ Successfully sent message to {url}", flush=True)
                        await browser.close()
                        return True

                print(f"⚠️ Message form elements not found on {url}", flush=True)
                await browser.close()
                return False

            except Exception as e:
                print(f"❌ Error sending message: {e}", flush=True)
                await browser.close()
                return False
