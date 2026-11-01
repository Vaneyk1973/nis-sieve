import re
import sys


def read_prototype(path):
    requests = None
    rows = {}
    with open(path) as stream:
        for line in stream:
            if match := re.fullmatch(r"requests (\d+) unique \d+\n?", line):
                requests = int(match[1])
            elif match := re.match(r"capacity (\d+) misses \d+ miss_ratio ([0-9.]+) ", line):
                rows[int(match[1])] = match[2]
    return requests, rows


def read_reference(path, policy):
    rows = {}
    with open(path) as stream:
        for line in stream:
            match = re.match(
                rf"{policy} (\d+) .*?(\d+) req, miss ratio ([0-9.]+)", line, re.IGNORECASE
            )
            if match:
                rows[int(match[1])] = (int(match[2]), match[3])
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
        reference_requests, reference_ratio = reference[capacity]
        status = "ok" if prototype[capacity] == reference_ratio else "MISMATCH"
        print(f"{status} capacity {capacity}: prototype {prototype[capacity]}, "
              f"reference {reference_ratio}")
        if status != "ok":
            errors.append(f"miss ratio differs at capacity {capacity}")
        if reference_requests != requests:
            errors.append(f"requests differ at capacity {capacity}")
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        return 1
    print("PASS prototype matches reference")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
