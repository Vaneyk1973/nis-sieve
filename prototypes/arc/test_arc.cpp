#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <list>
#include <string>
#include <vector>

#include "arc.hpp"

namespace {

int failures = 0;

void Expect(bool condition, const std::string& name) {
    std::cout << (condition ? "ok   " : "FAIL ") << name << '\n';
    if (!condition) {
        ++failures;
    }
}

bool Same(const std::list<std::uint64_t>& got, const std::vector<std::uint64_t>& want) {
    return std::vector<std::uint64_t>(got.begin(), got.end()) == want;
}

void TestKnownExample() {
    constexpr std::uint64_t A = 1, B = 2, C = 3, D = 4, E = 5, F = 6, G = 7;
    ArcCache cache(4);
    const std::vector<std::uint64_t> trace = {A, B, C, D, A, B, E, F, G, A, B};
    const std::vector<bool> expected = {false, false, false, false, true, true,
                                        false, false, false, true,  true};
    bool all_match = true;
    for (std::size_t i = 0; i < trace.size(); ++i) {
        all_match = all_match && cache.Access(trace[i]) == expected[i];
    }
    using W = ArcCache::Where;
    Expect(all_match, "hit and miss sequence on the 11-request example");
    Expect(cache.GetStats().hits == 4 && cache.GetStats().misses == 7, "4 hits and 7 misses");
    Expect(cache.GetStats().evictions == 3, "3 evictions");
    Expect(Same(cache.Items(W::T1), {F, G}), "T1 holds F, G");
    Expect(Same(cache.Items(W::T2), {A, B}), "T2 holds A, B");
    Expect(Same(cache.Items(W::B1), {D, E}), "B1 remembers D, E");
    Expect(cache.Size(W::B2) == 0, "B2 is empty");
    Expect(cache.Target() == 0.0, "target of T1 is 0 before the ghost hit");

    Expect(!cache.Access(E), "request to a ghost is a miss");
    Expect(cache.GetStats().ghost_hits == 1, "ghost hit is counted");
    Expect(cache.Target() == 1.0, "ghost hit in B1 raises the target to 1");
    Expect(Same(cache.Items(W::T1), {G}), "F is evicted from T1");
    Expect(Same(cache.Items(W::T2), {A, B, E}), "E goes straight to T2");
    Expect(Same(cache.Items(W::B1), {D, F}), "B1 forgets E and remembers F");
}

void TestLoopFitsInCache() {
    ArcCache cache(3);
    for (int round = 0; round < 5; ++round) {
        for (std::uint64_t id = 1; id <= 3; ++id) {
            cache.Access(id);
        }
    }
    Expect(cache.GetStats().misses == 3, "a loop that fits misses only on first access");
    Expect(cache.GetStats().evictions == 0, "a loop that fits evicts nothing");
}

void TestCapacityOne() {
    ArcCache cache(1);
    cache.Access(1);
    Expect(cache.Access(1), "capacity 1 keeps the last object");
    Expect(!cache.Access(2), "capacity 1 misses on another object");
    Expect(cache.Size(ArcCache::Where::T1) + cache.Size(ArcCache::Where::T2) == 1,
           "capacity 1 holds one object");
}

}  // namespace

int main() {
    TestKnownExample();
    TestLoopFitsInCache();
    TestCapacityOne();
    std::cout << (failures == 0 ? "all checks passed" : "checks failed") << '\n';
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
