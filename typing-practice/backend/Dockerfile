FROM golang:1.21-alpine AS builder

RUN apk add --no-cache gcc musl-dev sqlite-dev

WORKDIR /src/backend

COPY backend/go.mod backend/go.sum ./
RUN go mod download

COPY backend/ ./
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o /out/typing-practice .

FROM alpine:3.20

RUN apk --no-cache add ca-certificates sqlite-libs \
    && addgroup -S app \
    && adduser -S app -G app

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
