# UserBot uchun yengil va barqaror production image
FROM python:3.11-slim

# Python buffer va cache sozlamalari (log'lar real vaqtda ko'rinishi uchun)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Avval faqat requirements.txt'ni ko'chiramiz — Docker layer keshidan
# samarali foydalanish uchun (kod o'zgarsa ham, kutubxonalar qayta o'rnatilmaydi)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Qolgan barcha loyiha fayllarini ko'chiramiz
COPY . .

# Session, baza va media-kesh fayllari saqlanadigan papka doimiy bo'lishi uchun
VOLUME ["/app/data"]

CMD ["python", "main.py"]
