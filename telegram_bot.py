import os
import json
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CACHE_FILE = "sessions/proposals.json"

def _load_proposals() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_proposals(data: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class TelegramNotifier:
    def __init__(self, on_approve_callback):
        # Increased read and connect timeouts to prevent ReadError exceptions
        request_config = HTTPXRequest(
            connection_pool_size=8,
            read_timeout=30.0,
            write_timeout=20.0,
            connect_timeout=20.0
        )
        self.app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).request(request_config).build()
        self.on_approve_callback = on_approve_callback
        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CallbackQueryHandler(self.handle_button_click))

    async def send_listing_proposal(self, listing_id: str, title: str, url: str, reason: str, german_message: str):
        proposals = _load_proposals()
        proposals[str(listing_id)] = {
            "url": url,
            "message": german_message,
            "title": title
        }
        _save_proposals(proposals)

        text = (
            f"🏠 *New Matching WG Found (Gemini 3.7)!*\n\n"
            f"📌 *Title:* {title}\n"
            f"🔗 *URL:* [View on WG-Gesucht]({url})\n\n"
            f"💡 *Match Reason:* {reason}\n\n"
            f"📝 *Drafted Message (German):*\n```\n{german_message}\n```"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Send Message", callback_data=f"send_{listing_id}"),
                InlineKeyboardButton("❌ Skip", callback_data=f"skip_{listing_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )

    async def handle_button_click(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        proposals = _load_proposals()

        if data.startswith("send_"):
            listing_id = data.replace("send_", "")
            proposal = proposals.get(str(listing_id))

            if proposal:
                await query.edit_message_text(f"⏳ Sending message for listing {listing_id}...")
                success = await self.on_approve_callback(proposal["url"], proposal["message"])
                if success:
                    await query.edit_message_text(f"✅ Message sent successfully!\n🔗 {proposal['url']}")
                    proposals.pop(str(listing_id), None)
                    _save_proposals(proposals)
                else:
                    await query.edit_message_text(f"❌ Failed to send message for listing:\n🔗 {proposal['url']}")
            else:
                await query.edit_message_text("⚠️ Proposal expired or not found in persistent cache.")

        elif data.startswith("skip_"):
            listing_id = data.replace("skip_", "")
            if str(listing_id) in proposals:
                proposals.pop(str(listing_id), None)
                _save_proposals(proposals)
            await query.edit_message_text(f"🗑 Listing {listing_id} skipped.")

    async def start(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(poll_interval=2.0)

    async def stop(self):
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
