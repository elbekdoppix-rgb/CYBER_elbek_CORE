"""
main.py
-------
UserBot'ning asosiy ishga tushirish nuqtasi. Vazifalari:
  1. Logging tizimini sozlash (fayl + konsol).
  2. Ma'lumotlar bazasiga ulanish va jadvallarni tayyorlash.
  3. Telethon clientini ishga tushirish (session orqali avtomatik login).
  4. Barcha handler modullarini ro'yxatdan o'tkazish.
  5. Event loop'ni ishga tushirish va kutilmagan xatoliklardan himoyalash.
"""

import asyncio
import logging
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import (
    API_ID,
    API_HASH,
    SESSION_NAME,
    PHONE_NUMBER,
    LOG_FILE,
    LOG_LEVEL,
    ADMIN_ID,
)
from database import db

from handlers import admin_panel
from handlers import anti_delete
from handlers import ghost_mode
from handlers import call_logger
from handlers import keyword_alert
from handlers import steganography


def setup_logging() -> None:
    """Fayl va konsolga bir vaqtda log yozuvchi logging konfiguratsiyasi."""
    log_level = getattr(logging, str(LOG_LEVEL).upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Takroriy handler qo'shilib ketmasligi uchun avval tozalaymiz
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Telethon kutubxonasining haddan tashqari ko'p (DEBUG/INFO) log yozishining oldini olamiz
    logging.getLogger("telethon").setLevel(logging.WARNING)


logger = logging.getLogger("main")


async def start_userbot() -> None:
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    # ------------------------------------------------------------------
    # 1) Ma'lumotlar bazasini ishga tushirish
    # ------------------------------------------------------------------
    try:
        await db.connect()
        await db.init_db()
    except Exception:
        logger.critical("Ma'lumotlar bazasini ishga tushirib bo'lmadi. Dastur to'xtatilmoqda.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2) Telegram'ga ulanish
    # ------------------------------------------------------------------
    try:
        if PHONE_NUMBER:
            await client.start(phone=PHONE_NUMBER)
        else:
            await client.start()
    except SessionPasswordNeededError:
        logger.critical(
            "Ikki bosqichli autentifikatsiya (2FA) parolini kiritish talab qilinadi. "
            "Terminalda ishga tushirib, parolni kiritganingizdan so'ng session fayli saqlanadi."
        )
        sys.exit(1)
    except Exception:
        logger.exception("Telegram'ga ulanishda xatolik yuz berdi.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3) Akkaunt ma'lumotlarini tekshirish
    # ------------------------------------------------------------------
    try:
        me = await client.get_me()
        logger.info("UserBot muvaffaqiyatli ishga tushdi: %s (ID: %s)", me.first_name, me.id)
        if me.id != ADMIN_ID:
            logger.warning(
                "DIQQAT: .env faylidagi ADMIN_ID (%s) joriy akkaunt ID'siga (%s) mos kelmayapti. "
                "Buyruqlar to'g'ri ishlamasligi mumkin. ADMIN_ID qiymatini %s ga tenglashtiring.",
                ADMIN_ID,
                me.id,
                me.id,
            )
    except Exception:
        logger.exception("Akkaunt ma'lumotlarini olishda xatolik")

    # ------------------------------------------------------------------
    # 4) Barcha modullarni ro'yxatdan o'tkazish
    # ------------------------------------------------------------------
    try:
        admin_panel.register(client)
        anti_delete.register(client)
        ghost_mode.register(client)
        call_logger.register(client)
        keyword_alert.register(client)
        steganography.register(client)
        logger.info("Barcha modullar muvaffaqiyatli yuklandi. UserBot ishga tayyor.")
    except Exception:
        logger.exception("Modullarni ro'yxatdan o'tkazishda xatolik")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 5) Fon vazifasi: eski keshni davriy ravishda tozalash
    # ------------------------------------------------------------------
    async def _periodic_cache_cleanup():
        while True:
            try:
                removed = await db.cleanup_old_cache(older_than_hours=48)
                if removed:
                    logger.info("Eski keshdan %s ta yozuv tozalandi.", removed)
            except Exception:
                logger.exception("Davriy kesh tozalashda xatolik")
            await asyncio.sleep(3600)  # Har soatda bir marta

    client.loop.create_task(_periodic_cache_cleanup())

    # ------------------------------------------------------------------
    # 6) Asosiy event loop
    # ------------------------------------------------------------------
    try:
        await client.run_until_disconnected()
    except Exception:
        logger.exception("Asosiy event loop'da kutilmagan xatolik yuz berdi.")
    finally:
        await db.close()
        logger.info("UserBot to'xtatildi.")


def main() -> None:
    setup_logging()
    try:
        asyncio.run(start_userbot())
    except KeyboardInterrupt:
        logger.info("Dastur foydalanuvchi tomonidan to'xtatildi (Ctrl+C).")
    except Exception:
        logger.exception("Dasturda kutilmagan global xatolik yuz berdi.")
        sys.exit(1)


if __name__ == "__main__":
    main()
