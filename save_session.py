import asyncio
import os
from playwright.async_api import async_playwright

SESSION_PATH = "sessions/user_session.json"

async def manual_login():
    os.makedirs("sessions", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="de-DE",
            timezone_id="Europe/Berlin"
        )
        page = await context.new_page()

        print("🌐 Opening WG-Gesucht login page...")
        await page.goto("https://www.wg-gesucht.de")

        print("\n" + "=" * 50)
        print("1. Enter your email and password in the opened browser window.")
        print("2. Complete email verification/2FA if prompted.")
        print("3. Ensure you are fully logged in to your dashboard.")
        print("=" * 50 + "\n")

        input("Press ENTER in this terminal once you are logged in...")

        # Save cookies, tokens, and storage state
        await context.storage_state(path=SESSION_PATH)
        print(f"🎉 Session successfully saved to: {SESSION_PATH}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(manual_login())
