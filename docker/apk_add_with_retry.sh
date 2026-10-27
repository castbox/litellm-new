#!/bin/sh
set -eu

max_attempts="${APK_ADD_MAX_ATTEMPTS:-5}"
retry_delay_seconds="${APK_ADD_RETRY_DELAY_SECONDS:-10}"
case "$max_attempts" in
  ''|*[!0-9]*|0) echo "APK_ADD_MAX_ATTEMPTS must be a positive integer" >&2; exit 2 ;;
esac
case "$retry_delay_seconds" in
  ''|*[!0-9]*) echo "APK_ADD_RETRY_DELAY_SECONDS must be a nonnegative integer" >&2; exit 2 ;;
esac

attempt=1
while [ "$attempt" -le "$max_attempts" ]; do
  if apk add --no-cache "$@"; then
    exit 0
  fi
  if [ "$attempt" -eq "$max_attempts" ]; then
    echo "apk add failed after ${attempt} attempts" >&2
    exit 1
  fi
  echo "apk add attempt ${attempt}/${max_attempts} failed; retrying in ${retry_delay_seconds}s" >&2
  sleep "$retry_delay_seconds"
  attempt=$((attempt + 1))
done
