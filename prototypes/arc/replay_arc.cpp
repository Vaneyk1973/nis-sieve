#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <unordered_set>

#include "arc.hpp"

namespace {

constexpr std::size_t kRecordSize = 24;
constexpr std::size_t kObjectIdOffset = 4;

std::size_t ParseCapacity(const std::string& text, std::size_t unique) {
    if (!text.empty() && text.back() == '%') {
        const double percent = std::stod(text.substr(0, text.size() - 1));
        return static_cast<std::size_t>(static_cast<double>(unique) * percent / 100.0);
    }
    return std::stoull(text);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: replay_arc TRACE_BIN CAPACITY_OR_PERCENT...\n";
        return EXIT_FAILURE;
    }
    std::FILE* file = std::fopen(argv[1], "rb");
    if (file == nullptr) {
        std::cerr << "cannot open " << argv[1] << '\n';
        return EXIT_FAILURE;
    }
    std::fseek(file, 0, SEEK_END);
    const long bytes = std::ftell(file);
    if (bytes % static_cast<long>(kRecordSize) != 0) {
        std::cerr << "file size is not a multiple of the record size\n";
        return EXIT_FAILURE;
    }

    const auto read_all = [&](auto&& on_id) {
        std::rewind(file);
        unsigned char record[kRecordSize];
        while (std::fread(record, kRecordSize, 1, file) == 1) {
            std::uint64_t id = 0;
            std::memcpy(&id, record + kObjectIdOffset, sizeof(id));
            on_id(id);
        }
    };

    std::unordered_set<std::uint64_t> objects;
    std::uint64_t requests = 0;
    read_all([&](std::uint64_t id) {
        ++requests;
        objects.insert(id);
    });
    const std::size_t unique = objects.size();
    std::cout << "requests " << requests << " unique " << unique << '\n';
    objects.clear();

    for (int i = 2; i < argc; ++i) {
        const std::size_t capacity = ParseCapacity(argv[i], unique);
        ArcCache cache(capacity);
        read_all([&](std::uint64_t id) { cache.Access(id); });
        const auto& stats = cache.GetStats();
        const double miss_ratio =
            static_cast<double>(stats.misses) / static_cast<double>(stats.requests);
        std::printf("capacity %zu miss_ratio %.4f evictions %llu ghost_hits %llu list_ops %llu\n",
                    capacity, miss_ratio, static_cast<unsigned long long>(stats.evictions),
                    static_cast<unsigned long long>(stats.ghost_hits),
                    static_cast<unsigned long long>(stats.list_ops));
    }
    std::fclose(file);
    return EXIT_SUCCESS;
}
