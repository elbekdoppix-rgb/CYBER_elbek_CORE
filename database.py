"""
database.py
------------
SQLite (aiosqlite orqali to'liq asinxron) ma'lumotlar bazasi qatlami.

Jadvallar:
  - settings               -> bot sozlamalari (key-value)
  - deleted_messages_cache -> hali o'chirilmagan xabarlarning vaqtinchalik keshi
  - deleted_messages_log   -> aniqlangan va tasdiqlangan o'chirilgan xabarlar arxivi
  - keywords               -> kalit so'zlar ro'yxati
  - contacts                -> botga murojaat qilgan foydalanuvchilar ro'yxati
  - calls_log               -> kiruvchi qo'ng'iroqlar jurnali
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict

import aiosqlite

from config import DATABASE_PATH, DEFAULT_SETTINGS

logger = logging.getLogger("database")


class Database:
    """Butun loyiha davomida yagona instance sifatida ishlatiladigan DB klassi."""

    def __init__(self, path: str = DATABASE_PATH):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------
    # ULANISH VA INITSIALIZATSIYA
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        try:
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
            await self._conn.commit()
            logger.info("Ma'lumotlar bazasiga muvaffaqiyatli ulanildi: %s", self.path)
        except Exception:
            logger.exception("Ma'lumotlar bazasiga ulanishda xatolik yuz berdi")
            raise

    async def close(self) -> None:
        try:
            if self._conn is not None:
                await self._conn.close()
                logger.info("Ma'lumotlar bazasi ulanishi yopildi.")
        except Exception:
            logger.exception("Ma'lumotlar bazasini yopishda xatolik")

    async def init_db(self) -> None:
        if self._conn is None:
            raise RuntimeError("init_db() chaqirilishidan oldin connect() chaqirilishi kerak.")
        try:
            await self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS deleted_messages_cache (
                    message_id INTEGER NOT NULL,
                    chat_id    INTEGER,
                    sender_id  INTEGER,
                    sender_name TEXT,
                    text        TEXT,
                    media_path  TEXT,
                    sent_date   TEXT,
                    cached_at   TEXT,
                    PRIMARY KEY (message_id, chat_id)
                );

                CREATE TABLE IF NOT EXISTS deleted_messages_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id  INTEGER,
                    chat_id     INTEGER,
                    sender_id   INTEGER,
                    sender_name TEXT,
                    text        TEXT,
                    media_path  TEXT,
                    sent_date   TEXT,
                    deleted_at  TEXT
                );

                CREATE TABLE IF NOT EXISTS keywords (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS contacts (
                    user_id   INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username  TEXT,
                    added_at  TEXT
                );

                CREATE TABLE IF NOT EXISTS calls_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    caller_id   INTEGER,
                    caller_name TEXT,
                    call_type   TEXT,
                    video       BOOLEAN,
                    received_at TEXT
                );
                """
            )
            await self._conn.commit()

            # Standart sozlamalarni faqat mavjud bo'lmagan hollarda yozamiz
            for key, value in DEFAULT_SETTINGS.items():
                existing = await self.get_setting(key)
                if existing is None:
                    await self.set_setting(key, value)

            logger.info("Barcha jadvallar muvaffaqiyatli tekshirildi/yaratildi.")
        except Exception:
            logger.exception("Jadvallarni yaratishda xatolik yuz berdi")
            raise

    # ------------------------------------------------------------------
    # SETTINGS (CRUD)
    # ------------------------------------------------------------------
    async def get_setting(self, key: str) -> Optional[str]:
        try:
            cursor = await self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            return row["value"] if row else None
        except Exception:
            logger.exception("'%s' sozlamasini o'qishda xatolik", key)
            return None

    async def get_bool_setting(self, key: str, default: bool = False) -> bool:
        value = await self.get_setting(key)
        if value is None:
            return default
        return value == "1"

    async def set_setting(self, key: str, value: str) -> bool:
        try:
            await self._conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )
            await self._conn.commit()
            return True
        except Exception:
            logger.exception("'%s' sozlamasini yozishda xatolik", key)
            return False

    async def toggle_setting(self, key: str) -> bool:
        """Sozlamani teskarisiga o'zgartiradi va YANGI holatni qaytaradi."""
        current = await self.get_bool_setting(key, default=False)
        new_value = "0" if current else "1"
        await self.set_setting(key, new_value)
        return new_value == "1"

    async def get_all_settings(self) -> Dict[str, str]:
        try:
            cursor = await self._conn.execute("SELECT key, value FROM settings")
            rows = await cursor.fetchall()
            await cursor.close()
            return {row["key"]: row["value"] for row in rows}
        except Exception:
            logger.exception("Barcha sozlamalarni o'qishda xatolik")
            return {}

    # ------------------------------------------------------------------
    # DELETED MESSAGES CACHE (anti-delete uchun vaqtinchalik keshlash)
    # ------------------------------------------------------------------
    async def cache_message(
        self,
        message_id: int,
        chat_id: Optional[int],
        sender_id: Optional[int],
        sender_name: Optional[str],
        text: Optional[str],
        media_path: Optional[str],
        sent_date: Optional[str],
    ) -> None:
        try:
            await self._conn.execute(
                """
                INSERT INTO deleted_messages_cache
                    (message_id, chat_id, sender_id, sender_name, text, media_path, sent_date, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id, chat_id) DO UPDATE SET
                    sender_id   = excluded.sender_id,
                    sender_name = excluded.sender_name,
                    text        = excluded.text,
                    media_path  = COALESCE(excluded.media_path, deleted_messages_cache.media_path),
                    sent_date   = excluded.sent_date,
                    cached_at   = excluded.cached_at
                """,
                (
                    message_id,
                    chat_id,
                    sender_id,
                    sender_name,
                    text,
                    media_path,
                    sent_date,
                    datetime.utcnow().isoformat(),
                ),
            )
            await self._conn.commit()
        except Exception:
            logger.exception("Xabarni keshga saqlashda xatolik")

    async def get_cached_message_by_id(self, message_id: int) -> List[aiosqlite.Row]:
        try:
            cursor = await self._conn.execute(
                "SELECT * FROM deleted_messages_cache WHERE message_id = ?",
                (message_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        except Exception:
            logger.exception("Keshdan xabarni o'qishda xatolik")
            return []

    async def remove_cached_message(self, message_id: int, chat_id: Optional[int]) -> None:
        try:
            await self._conn.execute(
                "DELETE FROM deleted_messages_cache WHERE message_id = ? AND chat_id IS ?",
                (message_id, chat_id),
            )
            await self._conn.commit()
        except Exception:
            logger.exception("Keshdan xabarni o'chirishda xatolik")

    async def cleanup_old_cache(self, older_than_hours: int = 48) -> int:
        """Berilgan soatdan eski keshlangan yozuvlarni o'chiradi (xotira tejash uchun)."""
        try:
            cursor = await self._conn.execute(
                "DELETE FROM deleted_messages_cache WHERE cached_at < datetime('now', ?)",
                (f"-{older_than_hours} hours",),
            )
            await self._conn.commit()
            return cursor.rowcount if cursor.rowcount is not None else 0
        except Exception:
            logger.exception("Eski keshni tozalashda xatolik")
            return 0

    async def log_deleted_message(
        self,
        message_id: int,
        chat_id: Optional[int],
        sender_id: Optional[int],
        sender_name: Optional[str],
        text: Optional[str],
        media_path: Optional[str],
        sent_date: Optional[str],
    ) -> None:
        try:
            await self._conn.execute(
                """
                INSERT INTO deleted_messages_log
                    (message_id, chat_id, sender_id, sender_name, text, media_path, sent_date, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    chat_id,
                    sender_id,
                    sender_name,
                    text,
                    media_path,
                    sent_date,
                    datetime.utcnow().isoformat(),
                ),
            )
            await self._conn.commit()
        except Exception:
            logger.exception("O'chirilgan xabarni arxiv logiga yozishda xatolik")

    async def get_recent_deleted_logs(self, limit: int = 20) -> List[aiosqlite.Row]:
        try:
            cursor = await self._conn.execute(
                "SELECT * FROM deleted_messages_log ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        except Exception:
            logger.exception("O'chirilgan xabarlar arxivini o'qishda xatolik")
            return []

    # ------------------------------------------------------------------
    # KEYWORDS (CRUD)
    # ------------------------------------------------------------------
    async def add_keyword(self, keyword: str) -> bool:
        try:
            await self._conn.execute(
                "INSERT OR IGNORE INTO keywords (keyword) VALUES (?)",
                (keyword.lower().strip(),),
            )
            await self._conn.commit()
            return True
        except Exception:
            logger.exception("Kalit so'z qo'shishda xatolik")
            return False

    async def remove_keyword(self, keyword: str) -> bool:
        try:
            await self._conn.execute(
                "DELETE FROM keywords WHERE keyword = ?", (keyword.lower().strip(),)
            )
            await self._conn.commit()
            return True
        except Exception:
            logger.exception("Kalit so'zni o'chirishda xatolik")
            return False

    async def get_keywords(self) -> List[str]:
        try:
            cursor = await self._conn.execute("SELECT keyword FROM keywords")
            rows = await cursor.fetchall()
            await cursor.close()
            return [row["keyword"] for row in rows]
        except Exception:
            logger.exception("Kalit so'zlar ro'yxatini o'qishda xatolik")
            return []

    # ------------------------------------------------------------------
    # CONTACTS (CRUD)
    # ------------------------------------------------------------------
    async def add_contact(self, user_id: int, full_name: str, username: Optional[str]) -> None:
        try:
            await self._conn.execute(
                """
                INSERT INTO contacts (user_id, full_name, username, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username  = excluded.username
                """,
                (user_id, full_name, username, datetime.utcnow().isoformat()),
            )
            await self._conn.commit()
        except Exception:
            logger.exception("Kontakt qo'shishda xatolik")

    async def get_contacts(self) -> List[aiosqlite.Row]:
        try:
            cursor = await self._conn.execute(
                "SELECT * FROM contacts ORDER BY added_at DESC"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        except Exception:
            logger.exception("Kontaktlar ro'yxatini o'qishda xatolik")
            return []

    # ------------------------------------------------------------------
    # CALLS LOG (CRUD)
    # ------------------------------------------------------------------
    async def log_call(self, caller_id: int, caller_name: str, call_type: str, video: bool) -> None:
        try:
            await self._conn.execute(
                """
                INSERT INTO calls_log (caller_id, caller_name, call_type, video, received_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (caller_id, caller_name, call_type, video, datetime.utcnow().isoformat()),
            )
            await self._conn.commit()
        except Exception:
            logger.exception("Qo'ng'iroqni logga yozishda xatolik")

    async def get_recent_calls(self, limit: int = 20) -> List[aiosqlite.Row]:
        try:
            cursor = await self._conn.execute(
                "SELECT * FROM calls_log ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        except Exception:
            logger.exception("Qo'ng'iroqlar logini o'qishda xatolik")
            return []


# Butun loyiha bo'ylab import qilib ishlatiladigan yagona (singleton) instance
db = Database()
