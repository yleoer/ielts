FROM golang:1.21-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src/backend

ENV GOPROXY=https://goproxy.cn,direct

COPY backend/go.mod backend/go.sum ./
RUN go mod download

COPY backend/ ./
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o /out/typing-practice .

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libsqlite3-0 wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app/backend

COPY --from=builder /out/typing-practice ./typing-practice
COPY frontend ../frontend

RUN mkdir -p /app/data /app/stats \
    && chown -R app:app /app

USER app

EXPOSE 8080

ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8080
ENV ANKI_DB_PATH=/app/data/collection.anki2
ENV STATS_DB_PATH=/app/stats/stats.db
ENV GIN_MODE=release

CMD ["./typing-practice"]
