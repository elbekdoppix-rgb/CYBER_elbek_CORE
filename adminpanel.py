"""
handlers/admin_panel.py
-----------------------
Faqat bot egasi (ADMIN_ID, ya'ni sizning akkauntingiz) uchun ishlaydigan
boshqaruv paneli. `.panel` buyrug'i orqali inline tugmali menyu ochiladi,
unda barcha funksiyalarni bir bosishda yoqish/o'chirish mumkin.
"""

import logging

from telethon import events, Button, TelegramClient
from telethon.tl.custom import Message

from config import ADMIN_ID, COMMAND_PREFIX
from database import db

logger = logging.getLogger("admin_panel")

# Panelda ko'rsatiladigan funksiyalar va ularning chiroyli nomlari
FEATURE_LABELS = {
    "ghost_mode": "👻 Ghost Mode",
    "anti_delete": "🗑 Anti-Delete",
    "keyword_alert": "🔔 Kalit so'z xabarnomasi",
    "call_logger": "📞 Qo'ng'iroqlar jurnali",
    "force_offline": "🚫 Doim offline ko'rinish",
}


def _is_owner(event) -> bool:
    """Buyruq faqat akkaunt egasidan (sizdan) kelganini tekshiradi."""
    return bool(event.out) or event.sender_id == ADMIN_ID


async def _build_panel_text_and_buttons():
    settings = await db.get_all_settings()
    lines = [
        "🛠 **UserBot Boshqaruv Paneli**",
        "",
        "Quyidagi tugmalar orqali funksiyalarni yoqishingiz yoki o'chirishingiz mumkin:",
    ]
    buttons = []
    for key, label in FEATURE_LABELS.items():
        state = settings.get(key, "0") == "1"
        status_icon = "✅" if state else "❌"
        buttons.append(
            [Button.inline(f"{label}  {status_icon}", data=f"toggle_{key}".encode())]
        )
    buttons.append(
        [
            Button.inline("🔄 Yangilash", data=b"refresh_panel"),
            Button.inline("📊 Statistika", data=b"show_stats"),
        ]
    )
    text = "\n".join(lines)
    return text, buttons


def register(client: TelegramClient) -> None:
    """Admin panel bilan bog'liq barcha handlerlarni clientga ulaydi."""

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}panel$"))
    async def panel_handler(event: Message):
        try:
            if not _is_owner(event):
                return
            text, buttons = await _build_panel_text_and_buttons()
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except Exception:
            logger.exception("Panelni ko'rsatishda xatolik")
            try:
                await event.reply("⚠️ Panelni ochishda xatolik yuz berdi. Loglarni tekshiring.")
            except Exception:
                logger.exception("Xatolik xabarini yuborishda ham muammo yuz berdi")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}addkey (.+)$"))
    async def add_keyword_handler(event: Message):
        try:
            if not _is_owner(event):
                return
            keyword = event.pattern_match.group(1).strip()
            if not keyword:
                await event.edit("⚠️ Kalit so'z bo'sh bo'lishi mumkin emas.")
                return
            success = await db.add_keyword(keyword)
            if success:
                await event.edit(f"✅ Kalit so'z qo'shildi: `{keyword}`", parse_mode="markdown")
            else:
                await event.edit("❌ Kalit so'z qo'shishda xatolik yuz berdi.")
        except Exception:
            logger.exception("Kalit so'z qo'shishda xatolik")
            try:
                await event.edit("⚠️ Kutilmagan xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolikni bildirishda ham muammo")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}delkey (.+)$"))
    async def del_keyword_handler(event: Message):
        try:
            if not _is_owner(event):
                return
            keyword = event.pattern_match.group(1).strip()
            await db.remove_keyword(keyword)
            await event.edit(f"🗑 Kalit so'z o'chirildi: `{keyword}`", parse_mode="markdown")
        except Exception:
            logger.exception("Kalit so'z o'chirishda xatolik")
            try:
                await event.edit("⚠️ Kutilmagan xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolikni bildirishda ham muammo")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}keys$"))
    async def list_keywords_handler(event: Message):
        try:
            if not _is_owner(event):
                return
            keywords = await db.get_keywords()
            if not keywords:
                await event.edit("📭 Kalit so'zlar ro'yxati hozircha bo'sh.")
                return
            text = "🔑 **Kalit so'zlar ro'yxati:**\n\n" + "\n".join(
                f"• `{k}`" for k in keywords
            )
            await event.edit(text, parse_mode="markdown")
        except Exception:
            logger.exception("Kalit so'zlar ro'yxatini ko'rsatishda xatolik")
            try:
                await event.edit("⚠️ Ro'yxatni olishda xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolikni bildirishda ham muammo")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}help$"))
    async def help_handler(event: Message):
        try:
            if not _is_owner(event):
                return
            prefix = COMMAND_PREFIX
            help_text = (
                "🤖 **UserBot buyruqlari ro'yxati**\n\n"
                f"`{prefix}panel` — Boshqaruv panelini ochish\n"
                f"`{prefix}addkey <so'z>` — Kalit so'z qo'shish\n"
                f"`{prefix}delkey <so'z>` — Kalit so'zni o'chirish\n"
                f"`{prefix}keys` — Kalit so'zlar ro'yxatini ko'rish\n"
                f"`{prefix}encrypt <parol> <matn>` — Matnni shifrlash\n"
                f"`{prefix}decrypt <parol> <shifr>` — Matnni ochish\n"
                f"`{prefix}hide <parol> <matn>` — (rasmga javoban) Matnni rasmga yashirish\n"
                f"`{prefix}reveal <parol>` — (stego-rasmga javoban) Yashirin matnni ochish\n"
                f"`{prefix}help` — Ushbu yordam matni"
            )
            await event.edit(help_text, parse_mode="markdown")
        except Exception:
            logger.exception("Help buyrug'ida xatolik")

    @client.on(events.CallbackQuery(pattern=b"toggle_(.+)"))
    async def toggle_callback_handler(event):
        try:
            if event.sender_id != ADMIN_ID:
                await event.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q.", alert=True)
                return
            key = event.pattern_match.group(1).decode()
            if key not in FEATURE_LABELS:
                await event.answer("⚠️ Noma'lum sozlama.", alert=True)
                return
            new_state = await db.toggle_setting(key)
            text, buttons = await _build_panel_text_and_buttons()
            await event.edit(text, buttons=buttons, parse_mode="markdown")
            state_text = "yoqildi ✅" if new_state else "o'chirildi ❌"
            await event.answer(f"{FEATURE_LABELS[key]} {state_text}")
        except Exception:
            logger.exception("Toggle callback'da xatolik")
            try:
                await event.answer("⚠️ Xatolik yuz berdi.", alert=True)
            except Exception:
                logger.exception("Callback javobida ham xatolik")

    @client.on(events.CallbackQuery(pattern=b"refresh_panel"))
    async def refresh_callback_handler(event):
        try:
            if event.sender_id != ADMIN_ID:
                await event.answer("⛔ Sizda ruxsat yo'q.", alert=True)
                return
            text, buttons = await _build_panel_text_and_buttons()
            await event.edit(text, buttons=buttons, parse_mode="markdown")
            await event.answer("🔄 Panel yangilandi")
        except Exception:
            logger.exception("Panelni yangilashda xatolik")

    @client.on(events.CallbackQuery(pattern=b"show_stats"))
    async def stats_callback_handler(event):
        try:
            if event.sender_id != ADMIN_ID:
                await event.answer("⛔ Sizda ruxsat yo'q.", alert=True)
                return
            deleted_logs = await db.get_recent_deleted_logs(limit=1000)
            calls = await db.get_recent_calls(limit=1000)
            keywords = await db.get_keywords()
            stats_text = (
                "📊 Statistika:\n"
                f"🗑 O'chirilgan xabarlar (arxivda): {len(deleted_logs)}\n"
                f"📞 Qo'ng'iroqlar (logda): {len(calls)}\n"
                f"🔑 Kalit so'zlar soni: {len(keywords)}"
            )
            await event.answer(stats_text, alert=True)
        except Exception:
            logger.exception("Statistikani ko'rsatishda xatolik")
            try:
                await event.answer("⚠️ Statistikani olishda xatolik.", alert=True)
            except Exception:
                logger.exception("Statistika callback javobida ham xatolik")

    logger.info("admin_panel moduli muvaffaqiyatli ro'yxatdan o'tkazildi.")
