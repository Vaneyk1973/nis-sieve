import csv
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "nis/checkpoints/01-results/kv-survey"
BASE = "https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/cacheDatasets"
RECORD_BYTES = 24
WINDOW_REQUESTS = 5_000_000
PERCENTS = (0.1, 1, 10)
REFERENCE_POLICIES = ("fifo", "lru", "sieve", "arc")
MIN_EXCESS_POINTS = 2.0
MIN_SPREAD_POINTS = 0.5
CHECK_PERCENT = 1
SOURCES = (
    ("twitter_cluster10", "twitter/cluster10.oracleGeneral.zst", (0, 5, 10, 20)),
    ("twitter_cluster26", "twitter/cluster26.oracleGeneral.zst", (0,)),
    ("twitter_cluster50", "twitter/cluster50.oracleGeneral.zst", (0,)),
    ("twitter_cluster53", "twitter/cluster53.oracleGeneral.zst", (0,)),
    ("twitter_cluster45", "twitter/cluster45.oracleGeneral.zst", (0,)),
    ("twitter_cluster3", "twitter/cluster3.oracleGeneral.zst", (0,)),
    ("meta_kv_202401", "metaKV/202401_kv_traces_all_sort.csv.oracleGeneral.zst", (0,)),
)
FIELDS = (
    "source", "window_start_million", "requests", "unique", "sha256", "percent", "capacity",
    "first_access_share", "reference_requests", "fifo", "lru", "sieve", "arc", "prototype_arc",
    "excess_points", "spread_points", "suitable", "arc_exact_match",
)


def stream_windows(path, starts_million, directory):
    command = f"curl -sS -f -L --retry 2 '{BASE}/{path}' | zstd -dc"
    process = subprocess.Popen(["bash", "-c", command], stdout=subprocess.PIPE)
    window_bytes = WINDOW_REQUESTS * RECORD_BYTES
    position = 0
    files = {}
    try:
        for start in starts_million:
            begin = start * 1_000_000 * RECORD_BYTES
            while position < begin:
                chunk = process.stdout.read(min(1 << 20, begin - position))
                if not chunk:
                    return files
                position += len(chunk)
            target = Path(directory) / f"window_{start}.bin"
            written = 0
            with target.open("wb") as stream:
                while written < window_bytes:
                    chunk = process.stdout.read(min(1 << 20, window_bytes - written))
                    if not chunk:
                        break
                    stream.write(chunk)
                    written += len(chunk)
            position += written
            if written != window_bytes:
                target.unlink()
                return files
            files[start] = target
    finally:
        process.kill()
        process.wait()
    return files


def reference(path, policy, capacity):
    output = subprocess.run(
        ["cachesim", str(path), "oracleGeneral", policy, str(capacity), "--ignore-obj-size", "1"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, cwd=path.parent,
    ).stdout
    match = re.search(r"EXACT requests=(\d+) misses=(\d+)", output)
    if not match:
        raise RuntimeError(f"no exact counters for {policy} at {capacity}")
    return int(match[1]), int(match[2])


def replay(binary, path, capacities):
    output = subprocess.run(
        [str(binary), str(path), *capacities],
        text=True, stdout=subprocess.PIPE, check=True,
    ).stdout
    header = re.search(r"requests (\d+) unique (\d+)", output)
    misses = {int(c): int(m) for c, m in re.findall(r"capacity (\d+) misses (\d+)", output)}
    return int(header[1]), int(header[2]), misses


def analyze(binary, source, start, path):
    with path.open("rb") as trace:
        digest = hashlib.file_digest(trace, "sha256").hexdigest()
    requests, unique, prototype = replay(binary, path, [f"{percent}%" for percent in PERCENTS])
    capacities = dict(zip(PERCENTS, prototype))
    rows = []
    for percent, capacity in capacities.items():
        counted = {policy: reference(path, policy, capacity) for policy in REFERENCE_POLICIES}
        reference_requests = counted["arc"][0]
        ratios = {policy: misses / total for policy, (total, misses) in counted.items()}
        first_access = unique / requests
        compared = [ratios[policy] for policy in ("lru", "sieve", "arc")]
        worst, best = max(compared), min(compared)
        excess = (best - first_access) * 100
        spread = (worst - best) * 100
        rows.append({
            "source": source,
            "window_start_million": start,
            "requests": requests,
            "unique": unique,
            "sha256": digest,
            "percent": percent,
            "capacity": capacity,
            "first_access_share": f"{first_access:.5f}",
            "reference_requests": reference_requests,
            **{policy: f"{ratio:.5f}" for policy, ratio in ratios.items()},
            "prototype_arc": f"{prototype[capacity] / requests:.5f}",
            "excess_points": f"{excess:.3f}",
            "spread_points": f"{spread:.3f}",
            "suitable": excess >= MIN_EXCESS_POINTS and spread >= MIN_SPREAD_POINTS,
            "arc_exact_match": reference_requests == requests
            and counted["arc"][1] == prototype[capacity],
        })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = OUT / "results.csv"
    with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory, results.open("w", newline="") as stream:
        binary = Path(directory) / "replay_arc"
        subprocess.run(
            ["g++", "-std=c++17", "-O2", str(ROOT / "prototypes/arc/replay_arc.cpp"), "-o", str(binary)],
            check=True,
        )
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for source, path, starts in SOURCES:
            files = stream_windows(path, starts, directory)
            for start in starts:
                if start not in files:
                    print(f"{source} window {start}M: trace is too short", flush=True)
                    continue
                for row in analyze(binary, source, start, files[start]):
                    writer.writerow(row)
                    stream.flush()
                    if row["percent"] == CHECK_PERCENT:
                        print(
                            f"{source} {start}M U/N={row['first_access_share']} "
                            f"lru={row['lru']} sieve={row['sieve']} arc={row['arc']} "
                            f"excess={row['excess_points']} spread={row['spread_points']} "
                            f"suitable={row['suitable']} exact={row['arc_exact_match']}",
                            flush=True,
                        )
                files[start].unlink()


if __name__ == "__main__":
    main()
