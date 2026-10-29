FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/app.py backend/anki.py backend/auth.py backend/config.py backend/memory.py backend/srs.py backend/stats.py backend/sync.py backend/optimizer_service.py backend/optimize_fsrs.py ./
RUN mkdir -p config
COPY backend/config/config.yaml ./config/config.yaml
COPY frontend ../frontend

RUN mkdir -p /app/data /app/stats /app/anki-cache \
    && chown -R app:app /app

USER app

EXPOSE 8080

ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8080
ENV TZ=Asia/Shanghai
ENV ANKI_DB_PATH=/app/anki-cache/collection.anki2
ENV STATS_DB_PATH=/app/stats/stats.db
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
