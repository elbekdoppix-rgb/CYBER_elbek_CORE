"""
handlers/keyword_alert.py
--------------------------
Barcha kiruvchi xabarlarni (shaxsiy va guruh chatlarida) bazadagi kalit
so'zlar ro'yxati bo'yicha skaner qiladi. Mos keluvchi so'z topilganda,
ADMIN_ID'ga darhol to'liq kontekst bilan bildirishnoma yuboriladi.
"""

import logging

from telethon import events, TelegramClient

from config import ADMIN_ID
from database import db

logger = logging.getLogger("keyword_alert")


def register(client: TelegramClient) -> None:
    """Kalit so'zlarni skaner qiluvchi handlerni clientga ulaydi."""

    @client.on(events.NewMessage(incoming=True))
    async def keyword_scan_handler(event):
        try:
            enabled = await db.get_bool_setting("keyword_alert", default=True)
            if not enabled:
                return

            raw_text = event.raw_text or ""
            text_lower = raw_text.lower()
            if not text_lower:
                return

            keywords = await db.get_keywords()
            if not keywords:
                return

            matched = [kw for kw in keywords if kw in text_lower]
            if not matched:
                return

            sender_name = "Noma'lum"
            try:
                sender = await event.get_sender()
                if sender:
                    sender_name = getattr(sender, "first_name", None) or getattr(
                        sender, "title", "Noma'lum"
                    )
                    username = getattr(sender, "username", None)
                    if username:
                        sender_name = f"{sender_name} (@{username})"
            except Exception:
                logger.debug("Yuboruvchi ma'lumotini olib bo'lmadi.")

            chat_title = "Shaxsiy chat"
            try:
                chat = await event.get_chat()
                chat_title = getattr(chat, "title", None) or "Shaxsiy chat"
            except Exception:
                logger.debug("Chat ma'lumotini olib bo'lmadi.")

            matched_str = ", ".join(f"`{m}`" for m in matched)
            alert_text = (
                "🔔 **Kalit so'z aniqlandi!**\n\n"
                f"🔑 Topilgan so'z(lar): {matched_str}\n"
                f"👤 Kimdan: {sender_name}\n"
                f"💬 Qayerda: {chat_title}\n"
                f"🆔 Chat ID: `{event.chat_id}`\n\n"
                f"📝 Xabar matni:\n{raw_text}"
            )

            try:
                await client.send_message(ADMIN_ID, alert_text, parse_mode="markdown")
            except Exception:
                logger.exception("Kalit so'z bildirishnomasini yuborishda xatolik")

        except Exception:
            logger.exception("Kalit so'zlarni skanerlashda xatolik")

    logger.info("keyword_alert moduli muvaffaqiyatli ro'yxatdan o'tkazildi.")
