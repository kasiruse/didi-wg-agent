import random
import asyncio
import yaml
from wg_scraper import WGScraper
from gemini_agent import evaluate_and_draft_message
from telegram_bot import TelegramNotifier

def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def scrape_loop(scraper: WGScraper, notifier: TelegramNotifier, config: dict):
    while True:
        crawl_min = config.get("crawl_interval_min", 240)
        crawl_max = config.get("crawl_interval_max", 420)
        analysis_min = config.get("analysis_delay_min", 16)
        analysis_max = config.get("analysis_delay_max", 24)

        print("\n🔄 Checking for new listings...", flush=True)
        new_listings = await scraper.fetch_new_listings()
        print(f"📊 Total new listings queued for this cycle: {len(new_listings)}", flush=True)

        for item in new_listings:
            print(f"🤖 Analyzing listing {item['id']} with Gemini 3.7...", flush=True)

            # Run blocking Gemini sync client inside worker thread
            evaluation = await asyncio.to_thread(evaluate_and_draft_message, item["full_description"])

            if evaluation.get("is_match"):
                print(f"✨ Match found! Sending proposal to Telegram: {item['id']}", flush=True)
                await notifier.send_listing_proposal(
                    listing_id=item["id"],
                    title=item["title"],
                    url=item["url"],
                    reason=evaluation.get("reason", ""),
                    german_message=evaluation.get("german_message", "")
                )
            else:
                print(f"⏭ Skipped listing {item['id']}: {evaluation.get('reason')}", flush=True)

            analysis_pause = random.uniform(analysis_min, analysis_max)
            print(f"⏳ Cooling down for {analysis_pause:.1f}s before next listing analysis...", flush=True)
            await asyncio.sleep(analysis_pause)

        idle_time = random.uniform(crawl_min, crawl_max)
        print(f"😴 Idle phase: waiting {idle_time:.1f}s before next search cycle...", flush=True)
        await asyncio.sleep(idle_time)

async def main():
    print("🚀 Starting WG-Gesucht Agent System (Powered by Gemini 3.7)...", flush=True)
    config = load_config()
    search_url = config.get("search_url")

    scraper = WGScraper(search_url=search_url)

    async def handle_send_message(url: str, message: str) -> bool:
        return await scraper.send_message_to_listing(url, message)

    notifier = TelegramNotifier(on_approve_callback=handle_send_message)
    await notifier.start()
    print("🤖 Telegram Bot initialized and listening for interactions...", flush=True)

    try:
        await scrape_loop(scraper, notifier, config)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down gracefully...", flush=True)
    finally:
        await notifier.stop()

if __name__ == "__main__":
    asyncio.run(main())
