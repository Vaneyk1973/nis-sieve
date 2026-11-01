#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "arc.hpp"

namespace {

constexpr std::size_t kRecordSize = 24;
constexpr std::size_t kObjectIdOffset = 4;

std::size_t ParseCapacity(const std::string& text, std::size_t unique) {
    const std::runtime_error invalid("invalid capacity: " + text);
    if (text.empty()) {
        throw invalid;
    }
    std::size_t capacity = 0;
    try {
        std::size_t parsed = 0;
        if (text.back() == '%') {
            const std::string number = text.substr(0, text.size() - 1);
            const double percent = std::stod(number, &parsed);
            if (parsed != number.size() || !(percent > 0.0 && percent <= 100.0)) {
                throw invalid;
            }
            capacity = static_cast<std::size_t>(static_cast<double>(unique) * percent / 100.0);
        } else {
            if (text.find_first_not_of("0123456789") != std::string::npos) {
                throw invalid;
            }
            capacity = std::stoull(text, &parsed);
        }
    } catch (const std::invalid_argument&) {
        throw invalid;
    } catch (const std::out_of_range&) {
        throw invalid;
    }
    if (capacity == 0) {
        throw invalid;
    }
    return capacity;
}

void Replay(std::FILE* file, const std::vector<std::string>& capacities) {
    std::fseek(file, 0, SEEK_END);
    const long bytes = std::ftell(file);
    if (bytes <= 0) {
        throw std::runtime_error("trace is empty");
    }
    if (bytes % static_cast<long>(kRecordSize) != 0) {
        throw std::runtime_error("file size is not a multiple of the record size");
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
    objects.clear();

    std::vector<std::size_t> parsed;
    for (const auto& text : capacities) {
        parsed.push_back(ParseCapacity(text, unique));
    }

    std::cout << "requests " << requests << " unique " << unique << '\n';
    for (const std::size_t capacity : parsed) {
        ArcCache cache(capacity);
        read_all([&](std::uint64_t id) { cache.Access(id); });
        const auto& stats = cache.GetStats();
        const double miss_ratio =
            static_cast<double>(stats.misses) / static_cast<double>(stats.requests);
        std::printf(
            "capacity %zu misses %llu miss_ratio %.4f evictions %llu ghost_hits %llu "
            "list_ops %llu\n",
            capacity, static_cast<unsigned long long>(stats.misses), miss_ratio,
            static_cast<unsigned long long>(stats.evictions),
            static_cast<unsigned long long>(stats.ghost_hits),
            static_cast<unsigned long long>(stats.list_ops));
        std::fflush(stdout);
    }
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
    int status = EXIT_SUCCESS;
    try {
        Replay(file, std::vector<std::string>(argv + 2, argv + argc));
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        status = EXIT_FAILURE;
    }
    std::fclose(file);
    return status;
}
