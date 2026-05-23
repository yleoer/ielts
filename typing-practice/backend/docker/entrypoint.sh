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

	find "$SOURCE_DIR" -type f -name 'collection.anki2' -size +0c -printf '%T@ %p\n' 2>/dev/null \
		| sort -nr \
		| awk 'NR == 1 { sub(/^[^ ]+ /, ""); print }'
}

collection_group_stat() {
	group_source="$1"
	for suffix in "" "-wal" "-shm"; do
		file="${group_source}${suffix}"
		if [ -f "$file" ]; then
			stat -c '%n:%s:%Y' "$file"
		fi
	done
}

copy_file_atomic() {
	copy_source="$1"
	copy_target="$2"
	copy_tmp="${copy_target}.tmp"
	cp "$copy_source" "$copy_tmp"
	mv "$copy_tmp" "$copy_target"
}

copy_collection() {
	source_path="$(latest_collection || true)"
	if [ -z "$source_path" ] || [ ! -r "$source_path" ]; then
		return 1
	fi

	first_stat="$(collection_group_stat "$source_path")"
	sleep "$STABLE_SECONDS"
	second_stat="$(collection_group_stat "$source_path")"
	if [ "$first_stat" != "$second_stat" ]; then
		log "Anki collection is still changing; skipping this sync pass"
		return 1
	fi

	mkdir -p "$(dirname "$TARGET")"

	changed=0
	if [ ! -f "$TARGET" ] || ! cmp -s "$source_path" "$TARGET"; then
		changed=1
	fi
	for suffix in "-wal" "-shm"; do
		if [ -f "${source_path}${suffix}" ]; then
			if [ ! -f "${TARGET}${suffix}" ] || ! cmp -s "${source_path}${suffix}" "${TARGET}${suffix}"; then
				changed=1
			fi
		elif [ -f "${TARGET}${suffix}" ]; then
			changed=1
		fi
	done
	if [ "$changed" -eq 0 ]; then
		return 1
	fi

	copied="collection.anki2"
	copy_file_atomic "$source_path" "$TARGET"
	for suffix in "-wal" "-shm"; do
		if [ -f "${source_path}${suffix}" ]; then
			copy_file_atomic "${source_path}${suffix}" "${TARGET}${suffix}"
			copied="${copied},collection.anki2${suffix}"
		else
			rm -f "${TARGET}${suffix}"
		fi
	done
	log "Copied Anki collection group from $source_path to $TARGET files=$copied"
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
