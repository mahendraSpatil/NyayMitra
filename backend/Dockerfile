# NyayMitra backend: FastAPI + OCR (Tesseract eng/hin/mar + poppler).
# Built and run by deploy/docker-compose.prod.yml; see deploy/README.md.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Native OCR tools. pytesseract/pdf2image are only wrappers around these.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-mar \
      poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

# Unprivileged runtime user.
RUN useradd --create-home --uid 10001 nyaymitra && chown -R nyaymitra /app
USER nyaymitra

EXPOSE 8000
# Migrate, then serve. --proxy-headers: Caddy terminates HTTPS in front.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
