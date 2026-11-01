#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRACE=meta_reag.oracleGeneral.zst
TRACE_URL="https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/cacheDatasets/metaCDN/$TRACE"
TRACE_SHA=ff1d6b211ccf66a4115b3d532a82eb2710d6d94582da993a2ba24c7552f19039
PREFIX_REQUESTS=5000000
RECORD_BYTES=24
CAPACITIES=(1746 17469 174694)

DATA="$ROOT/data"
BUILD="$ROOT/build"
OUT="$ROOT/nis/checkpoints/01-results/real-trace"
PREFIX="$DATA/meta_reag_5m.bin"
mkdir -p "$DATA" "$BUILD" "$OUT"

[ -f "$DATA/$TRACE" ] || curl -sS -L --retry 3 -o "$DATA/$TRACE" "$TRACE_URL"
(cd "$DATA" && echo "$TRACE_SHA  $TRACE" | sha256sum -c -) | tee "$OUT/trace_sha256.txt"

set +o pipefail
zstd -dc "$DATA/$TRACE" | head -c $((PREFIX_REQUESTS * RECORD_BYTES)) > "$PREFIX"
set -o pipefail
[ "$(stat -c %s "$PREFIX")" -eq $((PREFIX_REQUESTS * RECORD_BYTES)) ]

python3 -I "$ROOT/tests/trace_fields.py" "$PREFIX" | tee "$OUT/trace_fields.txt"

g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic \
    "$ROOT/prototypes/arc/replay_arc.cpp" -o "$BUILD/replay_arc"
"$BUILD/replay_arc" "$PREFIX" "${CAPACITIES[@]}" | tee "$OUT/arc_prototype.txt"

cd "$(mktemp -d)"
for policy in fifo lru sieve arc; do
    for capacity in "${CAPACITIES[@]}"; do
        cachesim "$PREFIX" oracleGeneral "$policy" "$capacity" --ignore-obj-size 1 2>&1 |
            sed 's/\x1b\[[0-9;]*m//g' | grep 'miss ratio' | sed -E 's/, throughput.*//; s#^.*/##'
    done
done | tee "$OUT/reference.txt"
