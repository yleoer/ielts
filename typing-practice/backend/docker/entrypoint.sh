#!/bin/sh
set -eu

SOURCE_DIR="${ANKI_SYNC_SOURCE_DIR:-}"
TARGET="${ANKI_SYNC_TARGET:-/app/anki-cache/collection.anki2}"
INTERVAL="${ANKI_SYNC_INTERVAL_SECONDS:-300}"
INITIAL_WAIT="${ANKI_SYNC_INITIAL_WAIT_SECONDS:-60}"
STABLE_SECONDS="${ANKI_SYNC_STABLE_SECONDS:-2}"
APP_PID=""

log() {
	printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

latest_collection() {
	if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR" ]; then
		return 1
	fi

	find "$SOURCE_DIR" -type f -name collection.anki2 -size +0c -printf '%T@ %p\n' 2>/dev/null \
		| sort -nr \
		| awk 'NR == 1 { sub(/^[^ ]+ /, ""); print }'
}

copy_collection() {
	src="$(latest_collection || true)"
	if [ -z "$src" ] || [ ! -r "$src" ]; then
		return 1
	fi

	first_stat="$(stat -c '%s:%Y' "$src")"
	sleep "$STABLE_SECONDS"
	second_stat="$(stat -c '%s:%Y' "$src")"
	if [ "$first_stat" != "$second_stat" ]; then
		log "Anki collection is still changing; skipping this sync pass"
		return 1
	fi

	mkdir -p "$(dirname "$TARGET")"
	if [ -f "$TARGET" ] && cmp -s "$src" "$TARGET"; then
		return 1
	fi

	tmp="${TARGET}.tmp"
	cp "$src" "$tmp"
	mv "$tmp" "$TARGET"
	log "Copied Anki collection from $src to $TARGET"
	return 0
}

start_app() {
	"$@" &
	APP_PID="$!"
	log "Started typing-practice with pid $APP_PID"
}

stop_app() {
	if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
		log "Stopping typing-practice for Anki collection reload"
		kill "$APP_PID"
		wait "$APP_PID" 2>/dev/null || true
	fi
}

shutdown() {
	stop_app
	exit 0
}

trap shutdown TERM INT

if [ -z "$SOURCE_DIR" ]; then
	exec "$@"
fi

elapsed=0
while [ "$elapsed" -lt "$INITIAL_WAIT" ]; do
	if copy_collection || [ -f "$TARGET" ]; then
		break
	fi
	sleep "$STABLE_SECONDS"
	elapsed=$((elapsed + STABLE_SECONDS))
done

if [ ! -f "$TARGET" ]; then
	log "No synced Anki collection found yet; starting with Anki reader disabled"
fi

start_app "$@"

while true; do
	sleep "$INTERVAL" &
	wait "$!" || true

	if ! kill -0 "$APP_PID" 2>/dev/null; then
		wait "$APP_PID"
		exit "$?"
	fi

	if copy_collection; then
		stop_app
		start_app "$@"
	fi
done
