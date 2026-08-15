import asyncio
import yaml
from wg_scraper import WGScraper
from gemini_agent import evaluate_and_draft_message
from telegram_bot import TelegramNotifier

def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def main():
    print("🚀 Starting WG-Gesucht Agent System...")
    config = load_config()
    search_url = config.get("search_url")
    check_interval = config.get("check_interval_seconds", 300)

    scraper = WGScraper(search_url=search_url)

    async def handle_send_message(url: str, message: str) -> bool:
        return await scraper.send_message_to_listing(url, message)

    notifier = TelegramNotifier(on_approve_callback=handle_send_message)
    await notifier.start()
    print("🤖 Telegram Bot initialized and listening for interactions...")

    try:
        while True:
            print("\n🔄 Checking for new listings...")
            new_listings = await scraper.fetch_new_listings()
            print(f"📊 Found {len(new_listings)} new uninspected listings.")

            for item in new_listings:
                print(f"🤖 Analyzing listing {item['id']} with Gemini...")
                evaluation = evaluate_and_draft_message(item["full_description"])

                if evaluation.get("is_match"):
                    print(f"✨ Match found! Sending proposal to Telegram: {item['id']}")
                    await notifier.send_listing_proposal(
                        listing_id=item["id"],
                        title=item["title"],
                        url=item["url"],
                        reason=evaluation.get("reason", ""),
                        german_message=evaluation.get("german_message", "")
                    )
                else:
                    print(f"⏭ Skipped listing {item['id']}: {evaluation.get('reason')}")

            print(f"⏳ Sleeping for {check_interval} seconds...")
            await asyncio.sleep(check_interval)

    except (KeyboardInterrupt, SystemExit):
        print("Shutting down...")
    finally:
        await notifier.stop()

if __name__ == "__main__":
    asyncio.run(main())
