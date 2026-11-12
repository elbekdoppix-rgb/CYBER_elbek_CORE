"""
config.py
----------
Loyihaning barcha muhim konfiguratsiya o'zgaruvchilarini `.env` faylidan
o'qib, tekshirib (validatsiya qilib) beruvchi markaziy modul.

Diqqat: Bu fayl eng birinchi import qilinadigan fayl bo'lishi kerak, chunki
boshqa barcha modullar shu yerdagi qiymatlarga tayanadi.
"""

import os
import sys
import logging

from dotenv import load_dotenv

# .env faylini joriy ishchi papkadan yuklaymiz
load_dotenv()

# Bu bosqichda logging hali to'liq sozlanmagan bo'lishi mumkin,
# shuning uchun oddiy basicConfig bilan minimal logger yaratamiz.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("config")


def _get_env(name: str, required: bool = True, default=None):
    """.env dan matn qiymatini o'qiydi. Majburiy bo'lsa va topilmasa, dastur to'xtaydi."""
    value = os.getenv(name, default)
    if required and (value is None or str(value).strip() == ""):
        logger.critical(
            "'%s' muhit o'zgaruvchisi .env faylda topilmadi! "
            "Iltimos .env faylini tekshiring.",
            name,
        )
        sys.exit(1)
    return value


def _get_env_int(name: str, required: bool = True, default=None):
    """.env dan butun son (int) qiymatini xavfsiz o'qiydi."""
    raw = _get_env(name, required=required, default=default)
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        logger.critical(
            "'%s' qiymati butun son (int) bo'lishi kerak. Hozirgi qiymat: %r",
            name,
            raw,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Telegram API ma'lumotlari (https://my.telegram.org/apps dan olinadi)
# ---------------------------------------------------------------------------
API_ID: int = _get_env_int("API_ID")
API_HASH: str = _get_env("API_HASH")

# Session fayli nomi (Telethon shu nom bilan <nom>.session faylini yaratadi)
SESSION_NAME: str = _get_env("SESSION_NAME", required=False, default="userbot_session")

# Bot egasining (sizning) shaxsiy Telegram user_id raqamingiz.
# Faqat shu ID orqali yuborilgan buyruqlar (chiquvchi xabarlar) qabul qilinadi.
ADMIN_ID: int = _get_env_int("ADMIN_ID")

# Ixtiyoriy: Birinchi marta login qilishda ishlatiladigan telefon raqam.
# Agar session fayli allaqachon mavjud bo'lsa, bu qiymat ishlatilmaydi.
PHONE_NUMBER = _get_env("PHONE_NUMBER", required=False, default=None)

# Ma'lumotlar bazasi fayli joylashuvi
DATABASE_PATH: str = _get_env("DATABASE_PATH", required=False, default="userbot.db")

# Log fayli va log darajasi
LOG_FILE: str = _get_env("LOG_FILE", required=False, default="userbot.log")
LOG_LEVEL: str = _get_env("LOG_LEVEL", required=False, default="INFO")

# Buyruqlar prefiksi (masalan "." -> .panel, .ghost, .hide ...)
# Eslatma: joriy regex patternlar bitta belgili prefiks uchun optimallashtirilgan.
COMMAND_PREFIX: str = _get_env("COMMAND_PREFIX", required=False, default=".")

# Birinchi marta ishga tushganda bazaga yoziladigan standart sozlamalar.
# Qiymatlar matn ko'rinishida saqlanadi: "1" = yoqilgan, "0" = o'chirilgan.
DEFAULT_SETTINGS = {
    "ghost_mode": "0",
    "anti_delete": "1",
    "keyword_alert": "1",
    "call_logger": "1",
    "force_offline": "0",
}
