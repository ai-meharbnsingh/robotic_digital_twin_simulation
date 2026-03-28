#pragma once

// ──────────────────────────────────────────────────────────
// rdt/core/Timer.h — High-resolution cycle timer for the FMS main loop
// ──────────────────────────────────────────────────────────

#include <chrono>

namespace rdt {
namespace core {

/// @brief Deterministic cycle timer using std::chrono::steady_clock.
///
/// Designed for the 15Hz FMS main loop (67ms per cycle).
///
/// Usage:
/// @code
///     Timer timer;
///     while (running) {
///         timer.tick();
///         // ... do work ...
///         timer.sleep_until_next(67.0);  // 15Hz target
///     }
///     double hz = timer.get_frequency_hz();
/// @endcode
///
/// Thread-safety: Each thread should own its own Timer instance.
class Timer {
public:
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;
    using Duration = std::chrono::duration<double, std::milli>;

    Timer();

    /// Mark the start of a new cycle. Call at the top of every loop iteration.
    void tick();

    /// Milliseconds elapsed since the last tick() call.
    /// Returns 0.0 if tick() has never been called.
    double elapsed_ms() const;

    /// Sleep for the remaining time to hit the target cycle duration.
    /// If the cycle already exceeded target_ms, returns immediately (no sleep).
    /// @param target_ms  Target cycle time in milliseconds (e.g., 67.0 for 15Hz).
    void sleep_until_next(double target_ms) const;

    /// Measured frequency in Hz, computed from the interval between
    /// the two most recent tick() calls.
    /// Returns 0.0 if fewer than 2 ticks have occurred.
    double get_frequency_hz() const;

    /// Total number of tick() calls since construction.
    uint64_t tick_count() const;

private:
    TimePoint m_tick_time;       ///< Time of the most recent tick()
    TimePoint m_prev_tick_time;  ///< Time of the tick() before that
    uint64_t  m_tick_count;      ///< Running count of tick() calls
};

}  // namespace core
}  // namespace rdt
