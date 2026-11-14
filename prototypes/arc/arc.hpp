#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <list>
#include <stdexcept>
#include <unordered_map>

class ArcCache {
public:
    enum class Where { T1, T2, B1, B2 };

    struct Stats {
        std::uint64_t requests = 0;
        std::uint64_t hits = 0;
        std::uint64_t misses = 0;
        std::uint64_t evictions = 0;
        std::uint64_t ghost_hits = 0;
        std::uint64_t list_ops = 0;
    };

    explicit ArcCache(std::size_t capacity) : capacity_(capacity) {
        if (capacity_ == 0) {
            throw std::invalid_argument("capacity must be positive");
        }
    }

    bool Access(std::uint64_t id) {
        ++stats_.requests;
        const auto it = index_.find(id);
        const bool hit = it != index_.end() &&
                         (it->second.where == Where::T1 || it->second.where == Where::T2);
        if (hit) {
            ++stats_.hits;
            MoveTo(it->second, Where::T2);
        } else {
            ++stats_.misses;
            if (it == index_.end()) {
                OnNew(id);
            } else {
                OnGhost(it->second);
            }
        }
        CheckInvariants();
        return hit;
    }

    std::size_t Size(Where where) const { return List(where).size(); }
    double Target() const { return target_; }
    const Stats& GetStats() const { return stats_; }

    const std::list<std::uint64_t>& Items(Where where) const { return List(where); }

private:
    struct Entry {
        Where where;
        std::list<std::uint64_t>::iterator pos;
    };

    std::list<std::uint64_t>& List(Where where) {
        switch (where) {
            case Where::T1: return t1_;
            case Where::T2: return t2_;
            case Where::B1: return b1_;
            default: return b2_;
        }
    }

    const std::list<std::uint64_t>& List(Where where) const {
        return const_cast<ArcCache*>(this)->List(where);
    }

    void MoveTo(Entry& entry, Where to) {
        auto& from_list = List(entry.where);
        auto& to_list = List(to);
        to_list.splice(to_list.end(), from_list, entry.pos);
        entry.where = to;
        ++stats_.list_ops;
    }

    void Forget(Where where) {
        auto& list = List(where);
        index_.erase(list.front());
        list.pop_front();
        ++stats_.list_ops;
    }

    void Insert(std::uint64_t id, Where where) {
        auto& list = List(where);
        list.push_back(id);
        index_[id] = Entry{where, std::prev(list.end())};
        ++stats_.list_ops;
    }

    void Replace(bool requested_in_b2) {
        const double t1_size = static_cast<double>(t1_.size());
        const bool from_t1 =
            !t1_.empty() && (t1_size > target_ || (requested_in_b2 && t1_size == target_));
        const Where from = from_t1 ? Where::T1 : Where::T2;
        const Where to = from_t1 ? Where::B1 : Where::B2;
        MoveTo(index_.at(List(from).front()), to);
        ++stats_.evictions;
    }

    void OnGhost(Entry& entry) {
        ++stats_.ghost_hits;
        const double b1 = static_cast<double>(b1_.size());
        const double b2 = static_cast<double>(b2_.size());
        const double cap = static_cast<double>(capacity_);
        const bool in_b2 = entry.where == Where::B2;
        if (in_b2) {
            target_ = std::max(0.0, target_ - std::max(b1 / b2, 1.0));
        } else {
            target_ = std::min(cap, target_ + std::max(b2 / b1, 1.0));
        }
        Replace(in_b2);
        MoveTo(entry, Where::T2);
    }

    void OnNew(std::uint64_t id) {
        const std::size_t l1 = t1_.size() + b1_.size();
        const std::size_t total = l1 + t2_.size() + b2_.size();
        if (l1 == capacity_) {
            if (t1_.size() < capacity_) {
                Forget(Where::B1);
                Replace(false);
            } else {
                Forget(Where::T1);
                ++stats_.evictions;
            }
        } else if (total >= capacity_) {
            if (total == 2 * capacity_) {
                Forget(Where::B2);
            }
            Replace(false);
        }
        Insert(id, Where::T1);
    }

    void CheckInvariants() const {
        const std::size_t resident = t1_.size() + t2_.size();
        const std::size_t l1 = t1_.size() + b1_.size();
        const std::size_t total = l1 + t2_.size() + b2_.size();
        const bool ok = resident <= capacity_ && l1 <= capacity_ && total <= 2 * capacity_ &&
                        index_.size() == total &&
                        stats_.hits + stats_.misses == stats_.requests &&
                        stats_.evictions <= stats_.misses && target_ >= 0.0 &&
                        target_ <= static_cast<double>(capacity_);
        if (!ok) {
            throw std::logic_error("ARC invariant violated");
        }
    }

    std::size_t capacity_;
    double target_ = 0.0;
    std::list<std::uint64_t> t1_, t2_, b1_, b2_;
    std::unordered_map<std::uint64_t, Entry> index_;
    Stats stats_;
};
