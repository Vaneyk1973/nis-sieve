import struct
import sys

UNKNOWN_SIZE = 2**32 - 1
RECORD = struct.Struct("<IQIq")


def main(path):
    requests = 0
    unknown_size = 0
    zero_size = 0
    no_next = 0
    non_monotonic = 0
    first_time = None
    last_time = 0
    with open(path, "rb") as f:
        while chunk := f.read(RECORD.size * 65536):
            if len(chunk) % RECORD.size:
                raise SystemExit("file size is not a multiple of the record size")
            for time, _, size, next_access in RECORD.iter_unpack(chunk):
                requests += 1
                if first_time is None:
                    first_time = time
                if time < last_time:
                    non_monotonic += 1
                last_time = time
                unknown_size += size == UNKNOWN_SIZE
                zero_size += size == 0
                no_next += next_access < 0
    print(f"requests {requests}")
    print(f"time_span_seconds {last_time - first_time}")
    print(f"non_monotonic_time {non_monotonic}")
    print(f"size_is_2^32-1 {unknown_size} ({unknown_size / requests:.4%})")
    print(f"size_is_zero {zero_size} ({zero_size / requests:.4%})")
    print(f"next_access_negative {no_next} ({no_next / requests:.4%})")


if __name__ == "__main__":
    main(sys.argv[1])
