FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Fingerprint and compress static assets during build
ENV STATIC_ROOT=/app/staticfiles \
    DJANGO_SETTINGS_MODULE=agridep.config.settings.production \
    SECRET_KEY=build-phase-secret-key-12345
RUN python manage.py collectstatic --noinput

EXPOSE 5000

CMD ["sh", "-c", "gunicorn agridep.config.wsgi:application --bind 0.0.0.0:${PORT:-5000} --workers 3 --timeout 120"]
