"""
handlers/call_logger.py
------------------------
Kiruvchi ovozli/video qo'ng'iroqlarni Telethon'ning "Raw" (xom) update
tizimi orqali ushlab, vaqt va foydalanuvchi ma'lumotlari bilan birga
ma'lumotlar bazasiga yozadi va ADMIN_ID'ga maxfiy bildirishnoma yuboradi.
"""

import logging

from telethon import events, TelegramClient
from telethon.tl.types import (
    UpdatePhoneCall,
    PhoneCallRequested,
    PhoneCallDiscarded,
)

from config import ADMIN_ID
from database import db

logger = logging.getLogger("call_logger")


def register(client: TelegramClient) -> None:
    """Qo'ng'iroqlarni kuzatuvchi handlerni clientga ulaydi."""

    @client.on(events.Raw(types=UpdatePhoneCall))
    async def raw_call_handler(event: UpdatePhoneCall):
        try:
            call_logger_enabled = await db.get_bool_setting("call_logger", default=True)
            if not call_logger_enabled:
                return

            phone_call = event.phone_call
            if phone_call is None:
                return

            if isinstance(phone_call, PhoneCallRequested):
                caller_id = phone_call.admin_id
                is_video = bool(getattr(phone_call, "video", False))

                caller_name = f"ID: {caller_id}"
                try:
                    caller_entity = await client.get_entity(caller_id)
                    name = getattr(caller_entity, "first_name", None) or "Noma'lum"
                    username = getattr(caller_entity, "username", None)
                    caller_name = f"{name} (@{username})" if username else name
                except Exception:
                    logger.debug("Qo'ng'iroq qiluvchi entity'sini olib bo'lmadi.")

                call_type = "🎥 Video qo'ng'iroq" if is_video else "📞 Ovozli qo'ng'iroq"

                await db.log_call(
                    caller_id=caller_id,
                    caller_name=caller_name,
                    call_type=call_type,
                    video=is_video,
                )

                try:
                    await client.send_message(
                        ADMIN_ID,
                        (
                            "📞 **Yangi qo'ng'iroq aniqlandi!**\n\n"
                            f"👤 Kimdan: {caller_name}\n"
                            f"🆔 ID: `{caller_id}`\n"
                            f"📡 Turi: {call_type}"
                        ),
                        parse_mode="markdown",
                    )
                except Exception:
                    logger.exception("Qo'ng'iroq haqida admin'ga xabar yuborishda xatolik")

            elif isinstance(phone_call, PhoneCallDiscarded):
                logger.info("Qo'ng'iroq tugadi yoki rad etildi.")

        except Exception:
            logger.exception("Qo'ng'iroq update'ini qayta ishlashda xatolik")

    logger.info("call_logger moduli muvaffaqiyatli ro'yxatdan o'tkazildi.")
