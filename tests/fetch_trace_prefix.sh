#!/usr/bin/env bash
set -euo pipefail
url="$1"
prefix="$2"
requests="$3"
expected="$4"
[[ "$requests" =~ ^[1-9][0-9]*$ ]]
part=$(mktemp "${prefix}.part.XXXXXX")
trap 'rm -f "$part"' EXIT

set +o pipefail
curl --silent --show-error --fail --location --retry 2 --connect-timeout 20 \
    --max-time 1800 "$url" | zstd -dc | head -c "$((requests * 24))" > "$part"
statuses=("${PIPESTATUS[@]}")
set -o pipefail
test "${statuses[0]}" -eq 0 -o "${statuses[0]}" -eq 23
test "${statuses[1]}" -eq 0 -o "${statuses[1]}" -eq 141
test "${statuses[2]}" -eq 0
test "$(stat -c %s "$part")" -eq "$((requests * 24))"
printf '%s  %s\n' "$expected" "$part" | sha256sum -c -
mv "$part" "$prefix"
