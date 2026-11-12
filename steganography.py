"""
handlers/steganography.py
---------------------------
Ikki qatlamli maxfiylik vositasi:

  1. Matnni parol asosida (PBKDF2HMAC + Fernet/AES) shifrlash va ochish.
  2. Shifrlangan ma'lumotni rasm piksellarining eng kichik bitlariga (LSB —
     Least Significant Bit) yashirish va keyinchalik parol bilan qayta
     tiklab olish (klassik steganografiya usuli).

Natijada, hatto rasmni ko'rib turgan odam ham unda maxfiy ma'lumot
borligini bilmaydi, va parolsiz uni hech qanday usulda ochib bo'lmaydi.
"""

import os
import io
import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from PIL import Image

from telethon import events, TelegramClient
from telethon.tl.custom import Message

from config import COMMAND_PREFIX

logger = logging.getLogger("steganography")

_SALT_SIZE = 16
_PBKDF2_ITERATIONS = 390_000
_DELIMITER = "###STEGO_END###"


# ---------------------------------------------------------------------------
# SHIFRLASH / OCHISH (parol asosida)
# ---------------------------------------------------------------------------
def _derive_key(password: str, salt: bytes) -> bytes:
    """Parol va salt asosida Fernet uchun mos 32-baytli kalit hosil qiladi."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_text(plain_text: str, password: str) -> str:
    """Matnni parol yordamida shifrlaydi. Natija: base64 satr (ichida tasodifiy salt bor)."""
    salt = os.urandom(_SALT_SIZE)
    key = _derive_key(password, salt)
    fernet = Fernet(key)
    token = fernet.encrypt(plain_text.encode("utf-8"))
    payload = base64.urlsafe_b64encode(salt + token).decode("utf-8")
    return payload


def decrypt_text(payload: str, password: str) -> str:
    """encrypt_text() orqali shifrlangan satrni parol bilan ochadi."""
    raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
    salt, token = raw[:_SALT_SIZE], raw[_SALT_SIZE:]
    key = _derive_key(password, salt)
    fernet = Fernet(key)
    plain_bytes = fernet.decrypt(token)
    return plain_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# LSB STEGANOGRAFIYA (rasm ichiga matn yashirish)
# ---------------------------------------------------------------------------
def _text_to_bits(text: str) -> str:
    return "".join(format(byte, "08b") for byte in text.encode("utf-8"))


def _bits_to_text(bits: str) -> str:
    byte_chunks = [bits[i : i + 8] for i in range(0, len(bits), 8)]
    byte_values = bytes(int(chunk, 2) for chunk in byte_chunks if len(chunk) == 8)
    return byte_values.decode("utf-8", errors="ignore")


def hide_text_in_image(image_bytes: bytes, secret_payload: str) -> bytes:
    """Shifrlangan matnni rasm piksellarining LSB qismiga yashiradi. PNG bytes qaytaradi."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    pixels = list(image.getdata())

    full_payload = secret_payload + _DELIMITER
    bits = _text_to_bits(full_payload)

    capacity_bits = width * height * 3
    if len(bits) > capacity_bits:
        raise ValueError(
            "Rasm hajmi berilgan matnni yashirish uchun yetarli emas. "
            "Kattaroq o'lchamli rasm tanlang yoki matnni qisqartiring."
        )

    new_pixels = []
    bit_index = 0
    total_bits = len(bits)

    for pixel in pixels:
        channels = list(pixel[:3])
        for channel_index in range(3):
            if bit_index < total_bits:
                bit = int(bits[bit_index])
                channels[channel_index] = (channels[channel_index] & ~1) | bit
                bit_index += 1
        new_pixels.append(tuple(channels))

    stego_image = Image.new("RGB", image.size)
    stego_image.putdata(new_pixels)

    output_buffer = io.BytesIO()
    stego_image.save(output_buffer, format="PNG")
    return output_buffer.getvalue()


def extract_text_from_image(image_bytes: bytes) -> str:
    """Rasm ichiga LSB usulida yashirilgan shifrlangan matnni qayta tiklaydi."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pixels = list(image.getdata())

    bits = []
    for pixel in pixels:
        for channel_value in pixel[:3]:
            bits.append(str(channel_value & 1))

    bits_str = "".join(bits)
    extracted_text = _bits_to_text(bits_str)

    delimiter_index = extracted_text.find(_DELIMITER)
    if delimiter_index == -1:
        raise ValueError(
            "Ushbu rasmda yashirilgan ma'lumot topilmadi yoki rasm siqilgan/buzilgan."
        )

    return extracted_text[:delimiter_index]


# ---------------------------------------------------------------------------
# TELETHON HANDLERLARI
# ---------------------------------------------------------------------------
def register(client: TelegramClient) -> None:
    """Steganografiya va shifrlash buyruqlarini clientga ulaydi."""

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}encrypt (\S+) (.+)$"))
    async def encrypt_handler(event: Message):
        try:
            password = event.pattern_match.group(1)
            plain_text = event.pattern_match.group(2)
            cipher_payload = encrypt_text(plain_text, password)
            await event.edit(
                "🔒 **Matn shifrlandi:**\n\n`" + cipher_payload + "`",
                parse_mode="markdown",
            )
        except Exception:
            logger.exception("Matnni shifrlashda xatolik")
            try:
                await event.edit("⚠️ Matnni shifrlashda xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolik xabarini yuborishda ham muammo")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}decrypt (\S+) (.+)$"))
    async def decrypt_handler(event: Message):
        try:
            password = event.pattern_match.group(1)
            cipher_payload = event.pattern_match.group(2)
            plain_text = decrypt_text(cipher_payload, password)
            await event.edit("🔓 **Ochilgan matn:**\n\n" + plain_text)
        except InvalidToken:
            try:
                await event.edit("❌ Noto'g'ri parol yoki buzilgan ma'lumot.")
            except Exception:
                logger.exception("InvalidToken xabarini yuborishda muammo")
        except Exception:
            logger.exception("Matnni ochishda xatolik")
            try:
                await event.edit("⚠️ Matnni ochishda xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolik xabarini yuborishda ham muammo")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}hide (\S+) (.+)$"))
    async def hide_handler(event: Message):
        try:
            if not event.is_reply:
                await event.edit("⚠️ Bu buyruqni biror rasmga javob (reply) tarzida yuboring.")
                return

            replied = await event.get_reply_message()
            if not replied or not replied.photo:
                await event.edit("⚠️ Javob berilgan xabarda rasm topilmadi.")
                return

            password = event.pattern_match.group(1)
            secret_text = event.pattern_match.group(2)

            await event.edit("⏳ Ma'lumot shifrlanmoqda va rasmga yashirilmoqda...")

            cipher_payload = encrypt_text(secret_text, password)
            image_bytes = await replied.download_media(file=bytes)
            if image_bytes is None:
                await event.edit("⚠️ Rasmni yuklab olib bo'lmadi.")
                return

            stego_bytes = hide_text_in_image(image_bytes, cipher_payload)

            stego_file = io.BytesIO(stego_bytes)
            stego_file.name = "stego_image.png"

            await event.respond(
                "🖼 Maxfiy ma'lumot rasm ichiga muvaffaqiyatli yashirildi.\n"
                f"Ochish uchun: `{COMMAND_PREFIX}reveal <parol>` buyrug'ini shu rasmga "
                "javob qilib yuboring.",
                file=stego_file,
                parse_mode="markdown",
            )
            await event.delete()
        except ValueError as ve:
            try:
                await event.edit(f"⚠️ {ve}")
            except Exception:
                logger.exception("ValueError xabarini yuborishda muammo")
        except Exception:
            logger.exception("Rasmga ma'lumot yashirishda xatolik")
            try:
                await event.edit("⚠️ Rasmga ma'lumot yashirishda xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolik xabarini yuborishda ham muammo")

    @client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}reveal (\S+)$"))
    async def reveal_handler(event: Message):
        try:
            if not event.is_reply:
                await event.edit("⚠️ Bu buyruqni stego-rasmga javob (reply) tarzida yuboring.")
                return

            replied = await event.get_reply_message()
            if not replied or not replied.photo:
                await event.edit("⚠️ Javob berilgan xabarda rasm topilmadi.")
                return

            password = event.pattern_match.group(1)

            await event.edit("⏳ Rasm tahlil qilinmoqda...")

            image_bytes = await replied.download_media(file=bytes)
            if image_bytes is None:
                await event.edit("⚠️ Rasmni yuklab olib bo'lmadi.")
                return

            cipher_payload = extract_text_from_image(image_bytes)
            plain_text = decrypt_text(cipher_payload, password)

            await event.edit(
                f"🔓 **Topilgan maxfiy matn:**\n\n{plain_text}", parse_mode="markdown"
            )
        except InvalidToken:
            try:
                await event.edit("❌ Noto'g'ri parol yoki ma'lumot buzilgan.")
            except Exception:
                logger.exception("InvalidToken xabarini yuborishda muammo")
        except ValueError as ve:
            try:
                await event.edit(f"⚠️ {ve}")
            except Exception:
                logger.exception("ValueError xabarini yuborishda muammo")
        except Exception:
            logger.exception("Rasmdan ma'lumot chiqarishda xatolik")
            try:
                await event.edit("⚠️ Rasmdan ma'lumot chiqarishda xatolik yuz berdi.")
            except Exception:
                logger.exception("Xatolik xabarini yuborishda ham muammo")

    logger.info("steganography moduli muvaffaqiyatli ro'yxatdan o'tkazildi.")
