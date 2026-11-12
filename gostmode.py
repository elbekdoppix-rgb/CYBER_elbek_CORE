"""
handlers/ghost_mode.py
----------------------
"Ghost Mode" — yoqilgan bo'lsa, kiruvchi xabarlar hech qachon "o'qildi" deb
belgilanmaydi (ya'ni suhbatdosh tomonida xabar doimo bitta ✔️ holatida qoladi).
O'chirilgan bo'lsa, xabarlar odatdagidek, kichik kechikish bilan o'qilgan deb
belgilanadi (tabiiy foydalanuvchi xatti-harakatini taqlid qilish uchun).

Qo'shimcha: `force_offline` sozlamasi yoqilganda, akkaunt statusi doimiy
ravishda "offline" qilib saqlab turiladi.
"""

import asyncio
import logging
from typing import Optional

from telethon import events, TelegramClient, functions

from database import db

logger = logging.getLogger("ghost_mode")

_READ_DELAY_SECONDS = 3           # Tabiiy ko'rinish uchun kichik kechikish
_STATUS_UPDATE_INTERVAL = 50      # Offline statusni necha soniyada bir yangilash


async def _mark_as_read_if_allowed(client: TelegramClient, chat_id: Optional[int]) -> None:
    try:
        if chat_id is None:
            return
        ghost_enabled = await db.get_bool_setting("ghost_mode", default=False)
        if ghost_enabled:
            # Ghost mode yoqilgan: o'qilgan deb belgilamaymiz.
            return
        await asyncio.sleep(_READ_DELAY_SECONDS)
        await client.send_read_acknowledge(chat_id)
    except Exception:
        logger.exception("Xabarni o'qilgan deb belgilashda xatolik")


async def _force_offline_loop(client: TelegramClient) -> None:
    """Fon vazifasi: force_offline sozlamasi yoqilgan bo'lsa, doimiy offline statusni saqlaydi."""
    while True:
        try:
            force_offline = await db.get_bool_setting("force_offline", default=False)
            if force_offline:
                await client(functions.account.UpdateStatusRequest(offline=True))
        except Exception:
            logger.exception("Offline statusni yangilashda xatolik")
        await asyncio.sleep(_STATUS_UPDATE_INTERVAL)


def register(client: TelegramClient) -> None:
    """Ghost mode bilan bog'liq handler va fon vazifalarini ishga tushiradi."""

    @client.on(events.NewMessage(incoming=True))
    async def incoming_message_handler(event):
        try:
            # Xabarni bloklamasdan fon vazifasi sifatida ishga tushiramiz,
            # shunda boshqa handlerlar kutib turmaydi.
            client.loop.create_task(_mark_as_read_if_allowed(client, event.chat_id))
        except Exception:
            logger.exception("Ghost mode handler'da xatolik")

    client.loop.create_task(_force_offline_loop(client))

    logger.info("ghost_mode moduli muvaffaqiyatli ro'yxatdan o'tkazildi.")
