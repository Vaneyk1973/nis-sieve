import math
import re
import sys


def validate_row(requests, row):
    if requests <= 0:
        raise ValueError("request count must be positive")
    if "misses" in row and not 0 <= row["misses"] <= requests:
        raise ValueError("miss count is outside the request count")
    if "ratio" in row:
        ratio = float(row["ratio"])
        if not math.isfinite(ratio) or not 0 <= ratio <= 1:
            raise ValueError("invalid miss ratio")
        # The CLI renders ratios to four decimal places.
        if "misses" in row and abs(ratio - row["misses"] / requests) > 0.000050000001:
            raise ValueError("miss ratio disagrees with integer counters")


def read_prototype(path):
    requests = None
    rows = {}
    with open(path) as stream:
        for line in stream:
            if match := re.fullmatch(r"requests (\d+) unique (\d+)\n?", line):
                if requests is not None:
                    raise ValueError("duplicate prototype header")
                requests = int(match[1])
                if not 0 < int(match[2]) <= requests:
                    raise ValueError("invalid unique object count")
            elif match := re.match(r"capacity (\d+) misses (\d+) miss_ratio (\S+)(?:\s|$)", line):
                capacity = int(match[1])
                if capacity <= 0 or capacity in rows:
                    raise ValueError("invalid or duplicate prototype capacity")
                rows[capacity] = {"misses": int(match[2]), "ratio": match[3]}
            elif line.startswith(("requests ", "capacity ")):
                raise ValueError("malformed prototype record")
    if requests is not None:
        for row in rows.values():
            validate_row(requests, row)
    return requests, rows


def read_reference(path, policy):
    rows = {}
    with open(path) as stream:
        for line in stream:
            summary = re.match(
                rf"{policy} (\d+) .*?(\d+) req, miss ratio ([^,\s]+)", line, re.IGNORECASE
            )
            exact = re.match(
                rf"{policy} (\d+) EXACT requests=(\d+) misses=(\d+)", line, re.IGNORECASE
            )
            match = exact or summary
            if match:
                capacity, requests = int(match[1]), int(match[2])
                row = rows.setdefault(capacity, {"requests": requests})
                if capacity <= 0 or row["requests"] != requests:
                    raise ValueError(f"inconsistent reference request counts at {capacity}")
                field = "misses" if exact else "ratio"
                if field in row:
                    raise ValueError(f"duplicate reference {field} at {capacity}")
                row[field] = int(match[3]) if exact else match[3]
            elif re.match(rf"{policy} \d+ .*?(?:EXACT| req, miss ratio)", line, re.IGNORECASE):
                raise ValueError("malformed reference record")
    for row in rows.values():
        validate_row(row["requests"], row)
    return rows


def main(prototype_path, reference_path):
    requests, prototype = read_prototype(prototype_path)
    reference = read_reference(reference_path, "arc")
    errors = []
    if requests is None or not prototype:
        errors.append("prototype output has no results")
    if not reference:
        errors.append("reference output has no ARC results")
    if prototype.keys() != reference.keys():
        errors.append(f"capacities differ: {sorted(prototype)} and {sorted(reference)}")
    for capacity in sorted(prototype.keys() & reference.keys()):
        row = reference[capacity]
        field = "misses" if "misses" in row else "ratio"
        got, expected = prototype[capacity][field], row[field]
        status = "ok" if got == expected else "MISMATCH"
        print(f"{status} capacity {capacity}: {field}, prototype {got}, reference {expected}")
        if status != "ok":
            errors.append(f"{field} differs at capacity {capacity}")
        if row["requests"] != requests:
            errors.append(f"requests differ at capacity {capacity}")
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        return 1
    print("PASS prototype matches reference")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
