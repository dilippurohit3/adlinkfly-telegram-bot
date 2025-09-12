from __future__ import annotations

import asyncio
import logging
import re
import time
from io import BytesIO
from typing import Optional, List

import qrcode
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, InlineQueryHandler

from .config import Settings
from .adlinkfly_client import AdLinkFlyClient
from .storage import Storage

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _user_allowed(user_id: int, allowed: Optional[list[int]]) -> bool:
	return allowed is None or user_id in allowed


def _domain_from_url(url: str) -> Optional[str]:
	m = re.match(r"https?://([^/]+)", url, re.IGNORECASE)
	return m.group(1).lower() if m else None


class RateLimiter:
	def __init__(self, per_minute: int) -> None:
		self.per_minute = per_minute
		self.user_to_events: dict[int, List[float]] = {}

	def allow(self, user_id: int) -> bool:
		now = time.time()
		window_start = now - 60
		events = [t for t in self.user_to_events.get(user_id, []) if t >= window_start]
		if len(events) >= self.per_minute:
			self.user_to_events[user_id] = events
			return False
		events.append(now)
		self.user_to_events[user_id] = events
		return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	storage: Storage = context.application.bot_data["storage"]

	payload = context.args[0] if context.args else None
	if payload:
		# Treat start payload as API key
		if update.effective_user:
			await storage.set_user_api_key(update.effective_user.id, payload)
			await update.message.reply_text("Your API key was saved from the start link. ✅")

	await update.message.reply_text(
		"Send me one or more URLs and I'll shorten them using AdLinkFly.\n"
		"Use /short <url> [alias] or simply paste URLs. Inline mode is supported.\n"
		"You can set your own AdLinkFly API key via deep link or /setapi."
	)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await cmd_start(update, context)


async def cmd_setapi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	storage: Storage = context.application.bot_data["storage"]
	if not update.effective_user:
		return
	if not context.args:
		await update.message.reply_text("Usage: /setapi <your_adlinkfly_api_key>")
		return
	await storage.set_user_api_key(update.effective_user.id, context.args[0])
	await update.message.reply_text("Saved your API key. ✅")


async def cmd_myapi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	storage: Storage = context.application.bot_data["storage"]
	if not update.effective_user:
		return
	key = await storage.get_user_api_key(update.effective_user.id)
	if key:
		masked = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"
		await update.message.reply_text(f"Your API key: {masked}")
	else:
		await update.message.reply_text("No API key set. Use /setapi <key> or a start link.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	storage: Storage = context.application.bot_data["storage"]
	uid = update.effective_user.id if update.effective_user else 0
	count, last = await storage.user_stats(uid)
	msg = f"Your stats:\nShortened: {count}\nLast time: {last or '-'}"
	if settings.admin_user_ids and uid in settings.admin_user_ids:
		g_count, g_users = await storage.global_stats()
		msg += f"\n\nGlobal: {g_count} links by {g_users} users"
	await update.message.reply_text(msg)


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	storage: Storage = context.application.bot_data["storage"]
	uid = update.effective_user.id if update.effective_user else 0
	if not settings.admin_user_ids or uid not in settings.admin_user_ids:
		return
	if not context.args:
		await update.message.reply_text("Usage: /ban <user_id>")
		return
	target = int(context.args[0])
	await storage.set_banned(target, True)
	await update.message.reply_text(f"Banned {target}")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	storage: Storage = context.application.bot_data["storage"]
	uid = update.effective_user.id if update.effective_user else 0
	if not settings.admin_user_ids or uid not in settings.admin_user_ids:
		return
	if not context.args:
		await update.message.reply_text("Usage: /unban <user_id>")
		return
	target = int(context.args[0])
	await storage.set_banned(target, False)
	await update.message.reply_text(f"Unbanned {target}")


async def cmd_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if not context.args:
		await update.message.reply_text("Usage: /qr <url>")
		return
	await send_qr(update, context, context.args[0])


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()
	data = query.data or ""
	if data.startswith("qr|"):
		url = data.split("|", 1)[1]
		await send_qr(update, context, url)


async def send_qr(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
	img = qrcode.make(url)
	bio = BytesIO()
	img.save(bio, format="PNG")
	bio.seek(0)
	await update.effective_chat.send_photo(photo=bio, caption=url)


async def cmd_short(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	if not update.effective_user:
		return
	if not _user_allowed(update.effective_user.id, settings.allowed_user_ids):
		await update.message.reply_text("You are not allowed to use this bot.")
		return
	args = context.args or []
	if not args:
		await update.message.reply_text("Usage: /short <url> [alias]")
		return
	await process_urls(update, context, [args[0]], alias=args[1] if len(args) > 1 else None)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	if not update.effective_user or not update.message or not update.message.text:
		return
	if not _user_allowed(update.effective_user.id, settings.allowed_user_ids):
		return
	urls = URL_REGEX.findall(update.message.text)
	if not urls:
		return
	await process_urls(update, context, urls)


async def process_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: List[str], alias: Optional[str] = None) -> None:
	settings: Settings = context.application.bot_data["settings"]
	storage: Storage = context.application.bot_data["storage"]
	ratelimiter: RateLimiter = context.application.bot_data["ratelimiter"]
	uid = update.effective_user.id if update.effective_user else 0
	await storage.upsert_user(uid)
	if await storage.is_banned(uid):
		await update.message.reply_text("You are banned. Contact admin.")
		return
	if not ratelimiter.allow(uid):
		await update.message.reply_text("Rate limit exceeded. Try again in a minute.")
		return

	user_api_key = await storage.get_user_api_key(uid)

	# Filter domains
	filtered: List[str] = []
	for u in urls:
		d = _domain_from_url(u)
		if settings.whitelist_domains and d not in settings.whitelist_domains:
			continue
		if settings.blacklist_domains and d in settings.blacklist_domains:
			continue
		filtered.append(u)
	if not filtered:
		await update.message.reply_text("No allowed URLs found.")
		return

	batch = filtered[: settings.max_batch]
	await update.message.reply_text(f"Processing {len(batch)} URL(s)... ⏳")

	results: List[str] = []
	async with AdLinkFlyClient(settings.adlinkfly_base_url, settings.adlinkfly_api_key, settings.adlinkfly_api_path) as client:
		for u in batch:
			try:
				short_url = await client.shorten(u, alias, api_key_override=user_api_key)
				results.append(short_url)
				await storage.record_link(uid, u, short_url, alias)
			except Exception as e:  # noqa: BLE001
				results.append(f"Failed for {u}: {e}")

	# Build reply with buttons
	lines: List[str] = []
	keyboard_rows: List[List[InlineKeyboardButton]] = []
	for s in results:
		if s.startswith("http"):
			lines.append(s)
			keyboard_rows.append([
				InlineKeyboardButton(text="Open", url=s),
				InlineKeyboardButton(text="QR", callback_data=f"qr|{s}"),
			])
		else:
			lines.append(s)

	text = "\n".join(lines)
	reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None
	await update.message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	settings: Settings = context.application.bot_data["settings"]
	if not settings.inline_mode:
		return
	query = update.inline_query.query
	match = URL_REGEX.search(query or "")
	if not match:
		return
	url = match.group(0)
	try:
		async with AdLinkFlyClient(settings.adlinkfly_base_url, settings.adlinkfly_api_key, settings.adlinkfly_api_path) as client:
			short_url = await client.shorten(url)
	except Exception:
		return

	result = InlineQueryResultArticle(
		id="1",
		title="Shorten URL",
		description=short_url,
		input_message_content=InputTextMessageContent(short_url, disable_web_page_preview=True),
	)
	await update.inline_query.answer([result], cache_time=0, is_personal=True)


async def main_async() -> None:
	settings = Settings.load()
	logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

	storage = Storage()
	await storage.init()

	ratelimiter = RateLimiter(settings.rate_limit_per_min)

	application: Application = ApplicationBuilder().token(settings.telegram_bot_token).build()
	application.bot_data["settings"] = settings
	application.bot_data["storage"] = storage
	application.bot_data["ratelimiter"] = ratelimiter

	application.add_handler(CommandHandler("start", cmd_start))
	application.add_handler(CommandHandler("help", cmd_help))
	application.add_handler(CommandHandler("setapi", cmd_setapi))
	application.add_handler(CommandHandler("myapi", cmd_myapi))
	application.add_handler(CommandHandler("short", cmd_short))
	application.add_handler(CommandHandler("stats", cmd_stats))
	application.add_handler(CommandHandler("ban", cmd_ban))
	application.add_handler(CommandHandler("unban", cmd_unban))
	application.add_handler(CommandHandler("qr", cmd_qr))
	application.add_handler(CallbackQueryHandler(callback_handler))
	if settings.inline_mode:
		application.add_handler(InlineQueryHandler(inline_query))
	application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

	await application.initialize()
	await application.start()
	try:
		await application.updater.start_polling(drop_pending_updates=True)
		await application.updater.idle()
	finally:
		await application.stop()
		await application.shutdown()


def main() -> None:
	asyncio.run(main_async())


if __name__ == "__main__":
	main()
