import csv
import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile

from check_large_traces import ROOT, run, sha256
from compare_reference import read_prototype, read_reference
from trace_fields import RECORD

SEED = 20261103
CAPACITIES = (1, 2, 3, 7, 8, 9, 16, 64, 129)
OUT = ROOT / "nis/checkpoints/01-results/scenarios"


def main():
    rng = random.Random(SEED)
    uniform = [rng.randrange(128) for _ in range(8192)]
    profiles = {
        "one_object": [7] * 4096,
        "unique_scan": list(range(4096)),
        "loop_8": list(range(8)) * 512,
        "loop_9": list(range(9)) * 512,
        "scan_pollution": (list(range(8)) * 32 + list(range(1000, 2024)) + list(range(8)) * 64) * 4,
        "rotating_hotsets": [phase * 16 + rng.randrange(16) for phase in range(8) for _ in range(1024)],
        "uniform": uniform,
        "skewed": rng.choices(range(128), weights=[1 / (i + 1) for i in range(128)], k=8192),
        "hot_and_cold": [i // 2 % 8 if i % 2 == 0 else 10000 + i for i in range(8192)],
        "high_ids": [0, 2**64 - 1, 2**63, 2**32, 1] * 1024,
        "renamed_uniform": [(i * 11400714819323198485 + 17) % 2**64 for i in uniform],
        "metadata_uniform": uniform,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").unlink(missing_ok=True)
    records, descriptions, observed = [], [], {}
    known_answers = 0
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic",
             "-fsanitize=address,undefined", str(ROOT / "prototypes/arc/replay_arc.cpp"),
             "-o", "./replay_arc"], OUT / "compile.log")
        for name, ids in profiles.items():
            trace = Path(directory) / f"{name}.bin"
            with trace.open("wb") as stream:
                for i, object_id in enumerate(ids):
                    timestamp = i // 2 if name == "metadata_uniform" else i + 1
                    size = (1, 17, 2**32 - 1, 16_777_216)[i % 4] if name == "metadata_uniform" else 1
                    stream.write(RECORD.pack(timestamp, object_id, size, -1))
            result = OUT / name
            result.mkdir(exist_ok=True)
            prototype_log = result / "prototype.log"
            first = run(["./replay_arc", str(trace), *map(str, CAPACITIES)], prototype_log)
            requests, own = read_prototype(prototype_log)
            assert requests == len(ids) and set(own) == set(CAPACITIES), name
            unique = len(set(ids))
            if name == "uniform":
                repeated = run(["./replay_arc", str(trace), *map(str, CAPACITIES)], result / "repeat.log")
                assert first == repeated, "ARC replay must be deterministic"
            reference_log = result / "reference.txt"
            with reference_log.open("w") as stream:
                for capacity in CAPACITIES:
                    output = run(["cachesim", str(trace), "oracleGeneral", "arc", str(capacity),
                                  "--ignore-obj-size", "1", "--num-thread", "1"],
                                 Path(directory) / "reference.log")
                    for line in re.sub(r"\x1b\[[0-9;]*m", "", output).splitlines():
                        if " req, miss ratio " in line or line.startswith("EXACT "):
                            stream.write(f"arc {capacity} {line}\n")
            expected = read_reference(reference_log, "arc")
            assert expected.keys() == own.keys(), name
            for capacity in CAPACITIES:
                assert expected[capacity]["requests"] == requests, (name, capacity)
                assert expected[capacity]["misses"] == own[capacity]["misses"], (name, capacity)
                if unique == requests or capacity >= unique:
                    want = requests if unique == requests else unique
                    assert own[capacity]["misses"] == want, (name, capacity, want)
                    known_answers += 1
                records.append(dict(profile=name, capacity=capacity, requests=requests,
                                    unique=unique, misses=own[capacity]["misses"]))
            run(["python3", "-I", str(ROOT / "tests/compare_reference.py"),
                 str(prototype_log), str(reference_log)], result / "comparison.log")
            observed[name] = {capacity: row["misses"] for capacity, row in own.items()}
            descriptions.append(dict(profile=name, requests=requests, unique=unique,
                                     input_sha256=sha256(trace)))
            print(f"PASS {name}: {requests} requests, {len(CAPACITIES)} exact ARC comparisons", flush=True)

        result = OUT / "zero_size_records"
        result.mkdir(exist_ok=True)
        raw, normalized = Path(directory) / "zero_sizes.bin", Path(directory) / "normalized.bin"
        with raw.open("wb") as original, normalized.open("wb") as fixed:
            for i, object_id in enumerate(uniform):
                size = (0, 1, 2**32 - 1, 16_777_216)[i % 4]
                original.write(RECORD.pack(i // 2, object_id, size, -1))
                fixed.write(RECORD.pack(i // 2, object_id, 1, -1))
        for trace in (raw, normalized):
            prototype_log = result / f"{trace.stem}-prototype.log"
            run(["./replay_arc", str(trace), "8"], prototype_log)
            requests, own = read_prototype(prototype_log)
            output = run(["cachesim", str(trace), "oracleGeneral", "arc", "8",
                          "--ignore-obj-size", "1", "--num-thread", "1"],
                         result / f"{trace.stem}-raw-reference.log")
            reference_log = result / f"{trace.stem}-reference.txt"
            reference_log.write_text("".join(f"arc 8 {line}\n" for line in
                re.sub(r"\x1b\[[0-9;]*m", "", output).splitlines()))
            reference = read_reference(reference_log, "arc")[8]
            assert requests == len(uniform)
            if trace == raw:
                assert reference["requests"] == len(uniform) * 3 // 4
                comparison = subprocess.run(
                    ["python3", "-I", str(ROOT / "tests/compare_reference.py"),
                     str(prototype_log), str(reference_log)],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                (result / "expected-mismatch.log").write_text(comparison.stdout)
                assert comparison.returncode == 1 and "requests differ" in comparison.stdout
            else:
                assert reference["requests"] == len(uniform)
                assert reference["misses"] == own[8]["misses"] == observed["uniform"][8]
                run(["python3", "-I", str(ROOT / "tests/compare_reference.py"),
                     str(prototype_log), str(reference_log)], result / "normalized-comparison.log")
        print("PASS zero-size records: mismatch detected; explicit size normalization restores equality", flush=True)

    assert observed["renamed_uniform"] == observed["uniform"], "renaming IDs must preserve outcomes"
    assert observed["metadata_uniform"] == observed["uniform"], "ignored sizes/timestamps must preserve outcomes"
    with (OUT / "results.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (OUT / "manifest.json").write_text(json.dumps(dict(
        seed=SEED, profiles=descriptions, capacities=CAPACITIES,
        exact_arc_matches=len(records), known_answer_checks=known_answers,
        metamorphic_checks=2 * len(CAPACITIES), repeatability_checks=1,
        zero_size_mismatch_rejections=1, normalized_zero_size_exact_matches=1,
        sanitizers=["address", "undefined"], warmup_requests=0,
        source_sha256={path: sha256(ROOT / path) for path in (
            "tests/check_scenarios.py", "tests/check_large_traces.py", "tests/compare_reference.py",
            "prototypes/arc/arc.hpp", "prototypes/arc/replay_arc.cpp", "tests/trace_fields.py", "Dockerfile",
        )},
    ), indent=2) + "\n")
    print(f"ALL SCENARIO CHECKS PASSED: {len(records)} exact comparisons, "
          f"{known_answers} known answers, 18 metamorphic checks, 1 repeatability check", flush=True)


if __name__ == "__main__":
    main()
