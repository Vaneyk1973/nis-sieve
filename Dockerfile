FROM gcc:16.2.0-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates cmake curl git libglib2.0-dev libgoogle-perftools-dev \
        libzstd-dev ninja-build pkg-config python3-venv zstd \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir meson==1.12.1

# The course pins this revision; the reference uses CMake, our project uses Meson.
RUN git init /opt/sieve-reference \
    && git -C /opt/sieve-reference fetch --depth 1 \
        https://github.com/cacheMon/NSDI24-SIEVE.git \
        0861f8261c37b8286a70449a1defb5a4749c72d2 \
    && git -C /opt/sieve-reference checkout --detach FETCH_HEAD \
    && cmake -S /opt/sieve-reference/libCacheSim \
        -B /opt/sieve-reference/libCacheSim/_build -G Ninja \
        -DCMAKE_C_STANDARD=11 -DENABLE_TESTS=OFF \
    && cmake --build /opt/sieve-reference/libCacheSim/_build \
        --target cachesim --parallel 2

ENV PATH="/opt/venv/bin:/opt/sieve-reference/libCacheSim/_build/bin:${PATH}"

WORKDIR /workspace
CMD ["bash"]
