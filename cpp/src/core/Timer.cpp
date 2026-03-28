// ──────────────────────────────────────────────────────────
// core/Timer.cpp — High-resolution cycle timer implementation
// ──────────────────────────────────────────────────────────

#include "rdt/core/Timer.h"

#include <thread>

namespace rdt {
namespace core {

Timer::Timer()
    : m_tick_time(Clock::now())
    , m_prev_tick_time(m_tick_time)
    , m_tick_count(0)
{
}

void Timer::tick() {
    m_prev_tick_time = m_tick_time;
    m_tick_time = Clock::now();
    ++m_tick_count;
}

double Timer::elapsed_ms() const {
    if (m_tick_count == 0) {
        return 0.0;
    }
    Duration elapsed = Clock::now() - m_tick_time;
    return elapsed.count();
}

void Timer::sleep_until_next(double target_ms) const {
    if (m_tick_count == 0) {
        return;
    }

    Duration elapsed = Clock::now() - m_tick_time;
    double remaining_ms = target_ms - elapsed.count();

    if (remaining_ms > 0.0) {
        // Use microsecond-level sleep for sub-ms precision
        auto sleep_duration = std::chrono::microseconds(
            static_cast<int64_t>(remaining_ms * 1000.0));
        std::this_thread::sleep_for(sleep_duration);
    }
    // If remaining_ms <= 0, the cycle already exceeded the budget — return immediately.
}

double Timer::get_frequency_hz() const {
    if (m_tick_count < 2) {
        return 0.0;
    }
    Duration interval = m_tick_time - m_prev_tick_time;
    double interval_ms = interval.count();
    if (interval_ms <= 0.0) {
        return 0.0;
    }
    return 1000.0 / interval_ms;
}

uint64_t Timer::tick_count() const {
    return m_tick_count;
}

}  // namespace core
}  // namespace rdt
