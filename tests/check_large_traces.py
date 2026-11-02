import csv
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import tempfile

from compare_reference import read_prototype, read_reference

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "nis/checkpoints/01-results/large-traces"
REQUESTS = 10_000_000
TRACES = (
    ("meta_reag", "metaCDN/meta_reag.oracleGeneral.zst",
     "8fe7c66cf5df50bc3dd638eb7e459f295ca2c88ef189b939d511bc0b1ffef4f5"),
    ("twitter10", "twitter/cluster10.oracleGeneral.zst",
     "65b767e8027236c99acae1180d5328714d6624f7c0ca6b4c3885adbbe600717b"),
    ("wiki2019t", "wiki/wiki_2019t.oracleGeneral.zst",
     "6906cf18f71a82b72ef116c200749ab9dc5780017042f023b9b0bd9c8926ff67"),
)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, log):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    if result.returncode:
        print(result.stdout, flush=True)
    result.check_returncode()
    return result.stdout


def main():
    DATA.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").unlink(missing_ok=True)
    source_hashes = {path: sha256(ROOT / path) for path in (
        "Dockerfile", "prototypes/arc/arc.hpp", "prototypes/arc/replay_arc.cpp",
        "tests/check_large_traces.py", "tests/fetch_trace_prefix.sh", "tests/compare_reference.py",
    )}
    rows, manifest = [], []
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic",
             str(ROOT / "prototypes/arc/replay_arc.cpp"), "-o", "./replay_arc"], OUT / "compile.log")
        for name, source, checksum in TRACES:
            result_dir = OUT / name
            result_dir.mkdir(exist_ok=True)
            trace = DATA / f"{name}-10m.bin"
            url = "https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/cacheDatasets/" + source
            if not trace.exists():
                print(f"Downloading {name}: first {REQUESTS} requests", flush=True)
                run(["bash", str(ROOT / "tests/fetch_trace_prefix.sh"), url, str(trace),
                     str(REQUESTS), checksum], result_dir / "download.log")
            if trace.stat().st_size != REQUESTS * 24 or sha256(trace) != checksum:
                raise ValueError(f"cached prefix has wrong length or SHA-256: {trace}")

            prototype_log = result_dir / "prototype.log"
            output = run(["./replay_arc", str(trace), "0.1%", "0.3%", "1%", "3%", "10%", "30%"],
                         prototype_log)
            requests, prototype = read_prototype(prototype_log)
            unique = int(re.search(r"requests \d+ unique (\d+)", output)[1])
            if requests != REQUESTS or len(prototype) != 6 or min(prototype) < 100:
                raise ValueError(f"unexpected prototype output: {prototype_log}")
            for capacity, row in prototype.items():
                rows.append(dict(trace=name, capacity=capacity, implementation="prototype_arc",
                                 requests=requests, misses=row["misses"],
                                 miss_ratio=row["misses"] / requests))

            reference_log = result_dir / "reference.txt"
            with reference_log.open("w") as stream:
                for policy in ("fifo", "lru", "sieve", "arc"):
                    for capacity in prototype:
                        output = run(["cachesim", str(trace), "oracleGeneral", policy, str(capacity),
                                      "--ignore-obj-size", "1", "--num-thread", "1"],
                                     result_dir / f"reference-{policy}-{capacity}.log")
                        clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
                        for line in clean.splitlines():
                            if " req, miss ratio " in line or line.startswith("EXACT "):
                                stream.write(f"{policy} {capacity} {line}\n")
                        stream.flush()
                        print(f"{name}: {policy}, capacity={capacity}", flush=True)

            for policy in ("fifo", "lru", "sieve", "arc"):
                reference = read_reference(reference_log, policy)
                if reference.keys() != prototype.keys():
                    raise ValueError(f"reference capacities differ: {reference_log}")
                for capacity, row in reference.items():
                    if (row["requests"] != REQUESTS or "misses" not in row
                            or not 0 <= row["misses"] <= REQUESTS):
                        raise ValueError(f"missing/invalid exact counters; rebuild Docker image: {reference_log}")
                    rows.append(dict(trace=name, capacity=capacity, implementation=f"reference_{policy}",
                                     requests=REQUESTS, misses=row["misses"],
                                     miss_ratio=row["misses"] / REQUESTS))
            run(["python3", "-I", str(ROOT / "tests/compare_reference.py"), str(prototype_log),
                 str(reference_log)], result_dir / "comparison.log")
            manifest.append(dict(trace=name, source_url=url, requests=REQUESTS, unique=unique,
                                 prefix_sha256=checksum, capacities=list(prototype),
                                 warmup_requests=0, object_size=1, exact_arc_matches=6,
                                 reference_revision="0861f8261c37b8286a70449a1defb5a4749c72d2"))
            with (OUT / "results.csv").open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            print(f"PASS {name}: all six exact ARC comparisons", flush=True)

    (OUT / "manifest.json").write_text(json.dumps(dict(
        traces=manifest, source_sha256=source_hashes,
        maximum_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        reference_instrumentation="Extra printf of existing request/miss counters; algorithms unchanged",
        download_scope="Only the first 10 million records; hashes refer to decompressed prefixes",
    ), indent=2) + "\n")
    print("ALL LARGE TRACE CHECKS PASSED: 18 exact ARC comparisons", flush=True)


if __name__ == "__main__":
    main()
