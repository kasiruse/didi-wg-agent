import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# In-memory storage for pending proposals
PENDING_PROPOSALS = {}

class TelegramNotifier:
    def __init__(self, on_approve_callback):
        self.app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        self.on_approve_callback = on_approve_callback
        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CallbackQueryHandler(self.handle_button_click))

    async def send_listing_proposal(self, listing_id: str, title: str, url: str, reason: str, german_message: str):
        PENDING_PROPOSALS[listing_id] = {
            "url": url,
            "message": german_message
        }

        text = (
            f"🏠 *New Matching WG Found!*\n\n"
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
        if data.startswith("send_"):
            listing_id = data.replace("send_", "")
            proposal = PENDING_PROPOSALS.get(listing_id)

            if proposal:
                await query.edit_message_text(f"⏳ Sending message for listing {listing_id}...")
                success = await self.on_approve_callback(proposal["url"], proposal["message"])
                if success:
                    await query.edit_message_text(f"✅ Message sent successfully!\n🔗 {proposal['url']}")
                else:
                    await query.edit_message_text(f"❌ Failed to send message for listing:\n🔗 {proposal['url']}")
            else:
                await query.edit_message_text("⚠️ Proposal expired or not found.")

        elif data.startswith("skip_"):
            listing_id = data.replace("skip_", "")
            PENDING_PROPOSALS.pop(listing_id, None)
            await query.edit_message_text(f"🗑 Listing {listing_id} skipped.")

    async def start(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
