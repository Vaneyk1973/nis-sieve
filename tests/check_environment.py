import csv
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


def run(*args):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"$ {shlex.join(args)}\n{result.stdout}", flush=True)
    result.check_returncode()
    return result.stdout


def assert_fails(*args):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"$ {shlex.join(args)}\nexit {result.returncode}\n{result.stdout}", flush=True)
    assert result.returncode not in (0, -6, -11), result.stdout
    assert "nan" not in result.stdout, result.stdout


def check_reference(trace, algorithm, capacity, requests, misses):
    output = run(
        "cachesim", str(trace), "txt", algorithm, str(capacity),
        "--ignore-obj-size", "1",
    )
    match = re.search(r"(\d+) req, miss ratio ([0-9.]+)", output)
    assert match and int(match[1]) == requests, output
    assert abs(float(match[2]) - misses / requests) < 0.0001, output
    print(f"PASS {algorithm}: capacity={capacity}, misses={misses}/{requests}", flush=True)


repository = Path(__file__).resolve().parent.parent
fixtures = repository / "tests/data"
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

    check_reference(fixtures / "order.txt", "arc", 3, 8, 4)
    for algorithm, misses in (("lru", 9), ("sieve", 7), ("arc", 7)):
        check_reference(fixtures / "example.txt", algorithm, 4, 11, misses)

    Path("unique.txt").write_text("".join(f"{i}\n" for i in range(1, 21)))
    Path("repeated.txt").write_text("1\n" * 20)
    check_reference("unique.txt", "arc", 10, 20, 20)
    check_reference("repeated.txt", "arc", 10, 20, 1)

    run(
        "g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic",
        "-fsanitize=address,undefined",
        str(repository / "prototypes/arc/test_arc.cpp"), "-o", "test_arc",
    )
    assert "all checks passed" in run("./test_arc")
    print("PASS ARC prototype: known-answer test with sanitizers", flush=True)

    run(
        "g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic",
        "-fsanitize=address,undefined",
        str(repository / "prototypes/arc/replay_arc.cpp"), "-o", "replay_arc",
    )
    Path("empty.bin").write_bytes(b"")
    record = (1).to_bytes(4, "little") + (7).to_bytes(8, "little") + bytes(12)
    Path("one.bin").write_bytes(record)
    Path("broken.bin").write_bytes(record + b"x")
    assert_fails("./replay_arc", "empty.bin", "10")
    assert_fails("./replay_arc", "broken.bin", "10")
    for capacity in ("-1", "0", "abc", "1x", "0%", "-1%", "101%", "1x%", "", "99999999999999999999999"):
        assert_fails("./replay_arc", "one.bin", capacity)
    assert "capacity 1 misses 1 miss_ratio 1.0000 " in run("./replay_arc", "one.bin", "1")
    print("PASS replay_arc rejects empty traces and invalid capacities", flush=True)

    compare = str(repository / "tests/compare_reference.py")
    Path("prototype.txt").write_text(
        "requests 10 unique 5\n"
        "capacity 4 misses 6 miss_ratio 0.6000 evictions 1 ghost_hits 0 list_ops 1\n"
    )
    Path("same.txt").write_text("arc 4 x ARC cache size 4, 10 req, miss ratio 0.6000\n")
    Path("other.txt").write_text("arc 4 x ARC cache size 4, 10 req, miss ratio 0.7000\n")
    Path("length.txt").write_text("arc 4 x ARC cache size 4, 11 req, miss ratio 0.6000\n")
    Path("capacity.txt").write_text("arc 8 x ARC cache size 8, 10 req, miss ratio 0.6000\n")
    Path("no_arc.txt").write_text("lru 4 x LRU cache size 4, 10 req, miss ratio 0.6000\n")
    Path("no_results.txt").write_text("")
    run("python3", "-I", compare, "prototype.txt", "same.txt")
    for reference_file in ("other.txt", "length.txt", "capacity.txt", "no_arc.txt"):
        assert_fails("python3", "-I", compare, "prototype.txt", reference_file)
    assert_fails("python3", "-I", compare, "no_results.txt", "same.txt")
    Path("exact_same.txt").write_text(
        "arc 4 EXACT requests=10 misses=6\n"
    )
    run("python3", "-I", compare, "prototype.txt", "exact_same.txt")
    Path("large_prototype.txt").write_text(
        "requests 100000 unique 100\n"
        "capacity 4 misses 60000 miss_ratio 0.6000 evictions 1 ghost_hits 0 list_ops 1\n"
    )
    Path("rounded_collision.txt").write_text(
        "arc 4 x ARC cache size 4, 100000 req, miss ratio 0.6000\n"
        "arc 4 EXACT requests=100000 misses=60001\n"
    )
    assert_fails("python3", "-I", compare, "large_prototype.txt", "rounded_collision.txt")
    invalid_prototypes = (
        "requests 0 unique 0\ncapacity 4 misses 0 miss_ratio 0.0000 evictions 0\n",
        "requests 10 unique 11\ncapacity 4 misses 6 miss_ratio 0.6000 evictions 0\n",
        "requests 10 unique 5\ncapacity 4 misses 20 miss_ratio 2.0000 evictions 0\n",
        "requests 10 unique 5\ncapacity 4 misses 6 miss_ratio 0.2000 evictions 0\n",
        "requests 10 unique 5\ncapacity 4 misses 6 miss_ratio nan evictions 0\n",
        "requests 10 unique 5\ncapacity 4 misses -1 miss_ratio 0.6000 evictions 0\n",
        Path("prototype.txt").read_text() * 2,
        Path("prototype.txt").read_text() + "capacity 4 misses 6 miss_ratio 0.6000 evictions 0\n",
    )
    for text in invalid_prototypes:
        Path("invalid-prototype.txt").write_text(text)
        assert_fails("python3", "-I", compare, "invalid-prototype.txt", "exact_same.txt")
    invalid_references = (
        "arc 4 EXACT requests=10 misses=20\n",
        "arc 4 EXACT requests=10 misses=-1\n",
        "arc 4 x ARC cache size 4, 10 req, miss ratio nan\n",
        "arc 4 x ARC cache size 4, 10 req, miss ratio 2.0000\n",
        "arc 4 x ARC cache size 4, 10 req, miss ratio 0.2000\narc 4 EXACT requests=10 misses=6\n",
        "arc 4 x ARC cache size 4, 11 req, miss ratio 0.6000\narc 4 EXACT requests=10 misses=6\n",
        Path("exact_same.txt").read_text() * 2,
        Path("same.txt").read_text() * 2,
    )
    for text in invalid_references:
        Path("invalid-reference.txt").write_text(text)
        assert_fails("python3", "-I", compare, "prototype.txt", "invalid-reference.txt")
    for requests, unique, misses, ratio in ((10, 5, 20, "2.0000"), (0, 0, 0, "0.0000")):
        Path("invalid-prototype.txt").write_text(
            f"requests {requests} unique {unique}\n"
            f"capacity 4 misses {misses} miss_ratio {ratio} evictions 0\n"
        )
        Path("invalid-reference.txt").write_text(f"arc 4 EXACT requests={requests} misses={misses}\n")
        assert_fails("python3", "-I", compare, "invalid-prototype.txt", "invalid-reference.txt")
    print("PASS comparison fails when prototype and reference differ", flush=True)

    Path("prefix-source.bin").write_bytes(record * 4)
    run("zstd", "-q", "prefix-source.bin", "-o", "prefix-source.zst")
    fetch = str(repository / "tests/fetch_trace_prefix.sh")
    url = Path("prefix-source.zst").resolve().as_uri()
    expected = hashlib.sha256(record * 2).hexdigest()
    run("bash", fetch, url, "prefix.bin", "2", expected)
    assert Path("prefix.bin").read_bytes() == record * 2
    assert_fails("bash", fetch, url, "bad-hash.bin", "2", "0" * 64)
    assert not Path("bad-hash.bin").exists()
    assert_fails("bash", fetch, url, "short.bin", "5", expected)
    assert not Path("short.bin").exists()
    print("PASS prefix download checks length/hash and does not publish invalid data", flush=True)

    sandbox = Path("cached-input-check").resolve()
    for relative in (
        "Dockerfile", "tests/check_large_traces.py", "tests/fetch_trace_prefix.sh",
        "tests/compare_reference.py", "prototypes/arc/arc.hpp", "prototypes/arc/replay_arc.cpp",
    ):
        target = sandbox / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, target)
    cached = sandbox / "data/meta_reag-10m.bin"
    cached.parent.mkdir()
    with cached.open("wb") as stream:
        stream.truncate(10_000_000 * 24)
    completion = sandbox / "nis/checkpoints/01-results/large-traces/manifest.json"
    completion.parent.mkdir(parents=True)
    completion.write_text('{"stale": true}')
    assert_fails("python3", str(sandbox / "tests/check_large_traces.py"))
    assert cached.stat().st_size == 10_000_000 * 24
    assert not completion.exists()
    print("PASS corrupted cache is rejected and stale completion manifest is removed", flush=True)

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
