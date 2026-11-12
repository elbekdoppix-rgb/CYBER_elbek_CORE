"""
handlers/anti_delete.py
------------------------
Suhbatdosh (yoki guruh a'zosi) xabarni o'chirib yuborsa ham, uning matni va
media fayli oldindan keshlanganligi sababli yo'qolib ketmaydi. Xabar
o'chirilgani aniqlanishi bilan, uning to'liq nusxasi ADMIN_ID'ga (sizga)
maxfiy tarzda yuboriladi.

MUHIM TEXNIK ESLATMA:
Telegram protokoli (MTProto) xabar o'chirilganda, o'chirilgan xabarning qaysi
chatga tegishli ekanligini har doim ham aniq ko'rsatavermaydi (ayniqsa shaxsiy
suhbatlarda). Shuning uchun bu modul barcha kiruvchi xabarlarni oldindan
mahalliy keshga saqlab boradi va o'chirish yuz berganda shu keshdan qidiradi.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from telethon import events, TelegramClient

from config import ADMIN_ID
from database import db

logger = logging.getLogger("anti_delete")

MEDIA_CACHE_DIR = "media_cache"
MAX_MEDIA_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB dan katta mediani keshlamaymiz

os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)

# O'z akkaunt ID'imizni keshlab qo'yamiz, shunda o'zimiz o'chirgan xabarlar
# uchun keraksiz bildirishnoma yubormaymiz.
_self_id_cache = {"id": None}


async def _get_self_id(client: TelegramClient) -> Optional[int]:
    try:
        if _self_id_cache["id"] is None:
            me = await client.get_me()
            _self_id_cache["id"] = me.id
        return _self_id_cache["id"]
    except Exception:
        logger.exception("O'z ID'ni olishda xatolik")
        return None


async def _download_media_safe(client: TelegramClient, message) -> Optional[str]:
    try:
        if not message.media:
            return None
        file_size = getattr(message.file, "size", 0) or 0
        if file_size and file_size > MAX_MEDIA_SIZE_BYTES:
            logger.info("Media hajmi juda katta (%s bayt), keshlanmadi.", file_size)
            return None
        file_name = f"{message.chat_id}_{message.id}"
        path = await client.download_media(
            message, file=os.path.join(MEDIA_CACHE_DIR, file_name)
        )
        return path
    except Exception:
        logger.exception("Mediani yuklab olishda xatolik")
        return None


def register(client: TelegramClient) -> None:
    """Anti-delete bilan bog'liq barcha handlerlarni clientga ulaydi."""

    @client.on(events.NewMessage())
    async def cache_incoming_handler(event):
        """Har bir yangi xabarni (kiruvchi/chiquvchi) keshga saqlab boradi."""
        try:
            anti_delete_enabled = await db.get_bool_setting("anti_delete", default=True)
            if not anti_delete_enabled:
                return

            message = event.message
            sender_name = None
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
                logger.debug("Yuboruvchi ma'lumotini olib bo'lmadi, davom etilmoqda.")

            media_path = await _download_media_safe(client, message)

            await db.cache_message(
                message_id=message.id,
                chat_id=event.chat_id,
                sender_id=event.sender_id,
                sender_name=sender_name,
                text=message.raw_text or None,
                media_path=media_path,
                sent_date=message.date.isoformat() if message.date else None,
            )
        except Exception:
            logger.exception("Xabarni keshlashda xatolik")

    @client.on(events.MessageEdited())
    async def update_cache_on_edit(event):
        """Xabar tahrirlansa, keshdagi matnni ham yangilab boradi."""
        try:
            anti_delete_enabled = await db.get_bool_setting("anti_delete", default=True)
            if not anti_delete_enabled:
                return
            message = event.message
            await db.cache_message(
                message_id=message.id,
                chat_id=event.chat_id,
                sender_id=event.sender_id,
                sender_name=None,
                text=message.raw_text or None,
                media_path=None,
                sent_date=message.date.isoformat() if message.date else None,
            )
        except Exception:
            logger.exception("Tahrirlangan xabarni keshda yangilashda xatolik")

    @client.on(events.MessageDeleted())
    async def deleted_handler(event):
        """Xabar o'chirilgani aniqlanganda ishga tushadi."""
        try:
            anti_delete_enabled = await db.get_bool_setting("anti_delete", default=True)
            if not anti_delete_enabled:
                return

            self_id = await _get_self_id(client)

            for deleted_id in event.deleted_ids:
                cached_rows = await db.get_cached_message_by_id(deleted_id)
                if not cached_rows:
                    continue

                for row in cached_rows:
                    # O'zimiz yuborib, o'zimiz o'chirgan xabarlar uchun bildirishnoma
                    # yubormaymiz — bu faqat suhbatdosh harakatlari uchun mo'ljallangan.
                    if self_id is not None and row["sender_id"] == self_id:
                        await db.remove_cached_message(deleted_id, row["chat_id"])
                        continue

                    chat_display = (
                        row["chat_id"] if row["chat_id"] is not None else "Noma'lum chat"
                    )
                    sender_display = row["sender_name"] or "Noma'lum"
                    sent_date_display = row["sent_date"] or "Noma'lum"

                    notif_lines = [
                        "🗑 **O'chirilgan xabar aniqlandi!**",
                        "",
                        f"👤 Yuboruvchi: {sender_display}",
                        f"🆔 Yuboruvchi ID: `{row['sender_id']}`",
                        f"💬 Chat ID: `{chat_display}`",
                        f"🕐 Yuborilgan vaqt: {sent_date_display}",
                        f"🕑 O'chirilgan vaqt (UTC): {datetime.utcnow().isoformat()}",
                        "",
                    ]
                    if row["text"]:
                        notif_lines.append(f"📝 Matn:\n{row['text']}")
                    else:
                        notif_lines.append("📝 Matn: (matn yo'q yoki faqat media yuborilgan)")

                    notif_text = "\n".join(notif_lines)

                    try:
                        if row["media_path"] and os.path.exists(row["media_path"]):
                            await client.send_file(
                                ADMIN_ID,
                                row["media_path"],
                                caption=notif_text,
                                parse_mode="markdown",
                            )
                        else:
                            await client.send_message(
                                ADMIN_ID, notif_text, parse_mode="markdown"
                            )
                    except Exception:
                        logger.exception("Admin'ga bildirishnoma yuborishda xatolik")

                    await db.log_deleted_message(
                        message_id=deleted_id,
                        chat_id=row["chat_id"],
                        sender_id=row["sender_id"],
                        sender_name=row["sender_name"],
                        text=row["text"],
                        media_path=row["media_path"],
                        sent_date=row["sent_date"],
                    )
                    await db.remove_cached_message(deleted_id, row["chat_id"])
        except Exception:
            logger.exception("O'chirilgan xabarni qayta ishlashda xatolik")

    logger.info("anti_delete moduli muvaffaqiyatli ro'yxatdan o'tkazildi.")
