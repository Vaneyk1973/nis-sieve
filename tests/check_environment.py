import csv
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def run(*args):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"$ {shlex.join(args)}\n{result.stdout}", flush=True)
    result.check_returncode()
    return result.stdout


def check_reference(trace, algorithm, capacity, requests, misses):
    output = run(
        "cachesim", str(trace), "txt", algorithm, str(capacity),
        "--ignore-obj-size", "1",
    )
    match = re.search(r"(\d+) req, miss ratio ([0-9.]+)", output)
    assert match and int(match[1]) == requests, output
    assert abs(float(match[2]) - misses / requests) < 0.0001, output
    print(f"PASS {algorithm}: capacity={capacity}, misses={misses}/{requests}", flush=True)


fixtures = Path(__file__).resolve().parent / "data"
reference = Path("/opt/sieve-reference")
assert run("g++", "-dumpfullversion").strip() == "16.2.0"
assert run("meson", "--version").strip() == "1.12.1"
assert (reference / ".git/HEAD").read_text().strip() == (
    "0861f8261c37b8286a70449a1defb5a4749c72d2"
)
run("ninja", "--version")
run("cmake", "--version")

with tempfile.TemporaryDirectory() as directory:
    os.chdir(directory)
    Path("meson.build").write_text(
        "project('smoke', 'cpp', default_options: ['cpp_std=c++17'])\n"
        "executable('smoke', 'main.cpp')\n"
    )
    Path("main.cpp").write_text("int main() { return 0; }\n")
    run("meson", "setup", "build")
    run("meson", "compile", "-C", "build")
    run("./build/smoke")
    print("PASS GCC / Meson: compile and run", flush=True)

    for algorithm in ("lru", "sieve"):
        for capacity, misses in ((1, 6), (2, 4), (3, 3)):
            check_reference(fixtures / "basic.txt", algorithm, capacity, 6, misses)
    for algorithm, misses in (("lru", 4), ("sieve", 5)):
        check_reference(fixtures / "order.txt", algorithm, 3, 8, misses)

    Path("unique.txt").write_text("".join(f"{i}\n" for i in range(1, 21)))
    Path("repeated.txt").write_text("1\n" * 20)
    check_reference("unique.txt", "s3fifo", 10, 20, 20)
    check_reference("repeated.txt", "s3fifo", 20, 20, 1)
    # This pinned reference rejects an object as large as its small FIFO.
    check_reference("repeated.txt", "s3fifo", 10, 20, 20)

    sample = reference / "libCacheSim/data/twitter_cluster52.csv"
    print(f"Bundled CSV SHA256: {hashlib.sha256(sample.read_bytes()).hexdigest()}", flush=True)
    output = run(
        "cachesim", str(sample), "csv", "sieve", "1024",
        "--ignore-obj-size", "1", "--num-req", "1000",
        "-t", "time-col=1,obj-id-col=2,obj-size-col=3,delimiter=,",
    )
    match = re.search(r"(\d+) req, miss ratio ([0-9.]+)", output)
    assert match and int(match[1]) == 1000 and 0 <= float(match[2]) <= 1, output
    print("PASS bundled CSV: 1000 requests parsed; this is a format check", flush=True)

with (fixtures / "basic-operations.csv").open() as stream:
    rows = list(csv.DictReader(stream))
assert [int(row["object"]) for row in rows] == [1, 2, 1, 3, 1, 2]
expected = {
    "lru_hit": 2, "lru_list_insert": 6, "lru_list_remove": 4,
    "sieve_hit": 2, "sieve_list_insert": 4, "sieve_list_remove": 2,
    "sieve_scan": 4, "sieve_bit_write": 8,
}
for field, total in expected.items():
    assert sum(int(row[field]) for row in rows) == total, field
print(f"PASS analytical operations ledger totals: {expected}", flush=True)
print("Operations ledger is an analytical expectation, not measured policy counters.")
print("ALL CHECKS PASSED", flush=True)
