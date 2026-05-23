FROM golang:1.21-bookworm AS builder
WORKDIR /src/backend

COPY backend/go.mod backend/go.sum ./
RUN go mod download

COPY backend/ ./
RUN CGO_ENABLED=1 GOOS=linux go build -o /out/typing-practice .

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app/backend

COPY --from=builder /out/typing-practice ./typing-practice
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
ENV GIN_MODE=release

CMD ["./typing-practice"]
