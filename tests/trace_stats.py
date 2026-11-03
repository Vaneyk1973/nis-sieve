import csv
from pathlib import Path
import statistics
import subprocess

from trace_fields import RECORD, UNKNOWN_SIZE

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "nis/checkpoints/01-results/trace-stats"
BASE = "https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/cacheDatasets"
TRACES = (
    ("wiki_2019t", "wiki/wiki_2019t.oracleGeneral.zst"),
    ("meta_reag", "metaCDN/meta_reag.oracleGeneral.zst"),
    ("cluster50", "twitter/cluster50.oracleGeneral.zst"),
    ("cluster53", "twitter/cluster53.oracleGeneral.zst"),
)
READ_REQUESTS = 30_000_000
WINDOW_REQUESTS = 10_000_000
SIZE_SAMPLE_REQUESTS = 1_000_000
FRACTIONS = (0.001, 0.01, 0.1, 0.3)
FIELDS = (
    "trace", "records_read", "zero_size", "unknown_size", "median_request_size",
    "mean_request_size", "mean_object_size", "window_unique", "fraction", "cache_size",
    "requests_until_full",
)


def stream_records(path):
    command = f"curl -sS -f -L --retry 2 '{BASE}/{path}' | zstd -dc"
    process = subprocess.Popen(["bash", "-c", command], stdout=subprocess.PIPE)
    try:
        left = READ_REQUESTS
        while left:
            chunk = process.stdout.read(RECORD.size * min(left, 1 << 16))
            if len(chunk) < RECORD.size:
                return
            usable = len(chunk) - len(chunk) % RECORD.size
            if usable != len(chunk):
                chunk += process.stdout.read(RECORD.size - len(chunk) % RECORD.size)
            yield from RECORD.iter_unpack(chunk)
            left -= len(chunk) // RECORD.size
    finally:
        process.kill()
        process.wait()


def analyze(name, path):
    records = zero = unknown = 0
    sample_sizes = []
    object_sizes = {}
    seen = set()
    first_seen_at = []
    for _, object_id, size, _ in stream_records(path):
        records += 1
        zero += size == 0
        unknown += size == UNKNOWN_SIZE
        if records <= SIZE_SAMPLE_REQUESTS and 0 < size < UNKNOWN_SIZE:
            sample_sizes.append(size)
            object_sizes[object_id] = size
        if records <= WINDOW_REQUESTS and object_id not in seen:
            seen.add(object_id)
            first_seen_at.append(records)
    window_unique = len(seen)
    seen.clear()
    common = {
        "trace": name,
        "records_read": records,
        "zero_size": zero,
        "unknown_size": unknown,
        "median_request_size": statistics.median(sample_sizes),
        "mean_request_size": round(statistics.fmean(sample_sizes)),
        "mean_object_size": round(statistics.fmean(object_sizes.values())),
        "window_unique": window_unique,
    }
    for fraction in FRACTIONS:
        cache_size = max(100, int(window_unique * fraction))
        yield {
            **common,
            "fraction": fraction,
            "cache_size": cache_size,
            "requests_until_full": first_seen_at[cache_size - 1],
        }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for name, path in TRACES:
            for row in analyze(name, path):
                writer.writerow(row)
                stream.flush()
                print(row, flush=True)


if __name__ == "__main__":
    main()
