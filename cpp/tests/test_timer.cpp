// ──────────────────────────────────────────────────────────
// test_timer.cpp — Tests for rdt::core::Timer
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include <thread>
#include <cmath>

#include "rdt/core/Timer.h"

class TimerTest : public ::testing::Test {
protected:
    rdt::core::Timer timer;
};

// ── TEST: tick() + elapsed_ms() returns > 0 ────────────────

TEST_F(TimerTest, ElapsedIsZeroBeforeTick) {
    // Before any tick(), elapsed should be 0
    // (constructor sets internal time, but tick_count is 0)
    EXPECT_DOUBLE_EQ(timer.elapsed_ms(), 0.0)
        << "elapsed_ms() should return 0.0 before any tick()";
}

TEST_F(TimerTest, ElapsedIsPositiveAfterTick) {
    timer.tick();
    // Sleep a small amount so elapsed is measurably > 0
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
    double elapsed = timer.elapsed_ms();

    EXPECT_GT(elapsed, 0.0)
        << "elapsed_ms() should be positive after tick() + sleep";
    EXPECT_GE(elapsed, 4.0)
        << "After 5ms sleep, elapsed should be at least 4ms (accounting for OS jitter)";
    EXPECT_LT(elapsed, 50.0)
        << "After 5ms sleep, elapsed should be well under 50ms";
}

TEST_F(TimerTest, TickCountIncrements) {
    EXPECT_EQ(timer.tick_count(), 0u);
    timer.tick();
    EXPECT_EQ(timer.tick_count(), 1u);
    timer.tick();
    EXPECT_EQ(timer.tick_count(), 2u);
    timer.tick();
    EXPECT_EQ(timer.tick_count(), 3u);
}

TEST_F(TimerTest, ElapsedResetsOnTick) {
    timer.tick();
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    double elapsed_before = timer.elapsed_ms();
    EXPECT_GE(elapsed_before, 15.0) << "Should have ~20ms elapsed";

    // New tick resets the reference point
    timer.tick();
    double elapsed_after = timer.elapsed_ms();
    EXPECT_LT(elapsed_after, 5.0)
        << "Immediately after tick(), elapsed should be near 0";
}

// ── TEST: sleep_until_next(100) sleeps ~100ms ──────────────

TEST_F(TimerTest, SleepUntilNextSleepsCorrectDuration) {
    timer.tick();

    // Start measuring total wall-clock time
    auto wall_start = std::chrono::steady_clock::now();

    // Target: 100ms cycle. We've done almost no work, so it should sleep ~100ms.
    timer.sleep_until_next(100.0);

    auto wall_end = std::chrono::steady_clock::now();
    double wall_ms = std::chrono::duration<double, std::milli>(wall_end - wall_start).count();

    // Should be ~100ms, within 10ms tolerance
    EXPECT_GE(wall_ms, 90.0)
        << "sleep_until_next(100) should sleep at least 90ms, got " << wall_ms << "ms";
    EXPECT_LE(wall_ms, 120.0)
        << "sleep_until_next(100) should sleep at most 120ms, got " << wall_ms << "ms";
}

TEST_F(TimerTest, SleepUntilNextReturnsImmediatelyWhenOverBudget) {
    timer.tick();
    // Simulate work that exceeds the budget
    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    auto wall_start = std::chrono::steady_clock::now();
    timer.sleep_until_next(10.0);  // 10ms budget, but 50ms already elapsed
    auto wall_end = std::chrono::steady_clock::now();

    double wall_ms = std::chrono::duration<double, std::milli>(wall_end - wall_start).count();
    EXPECT_LT(wall_ms, 5.0)
        << "When over budget, sleep_until_next should return immediately, got " << wall_ms << "ms";
}

TEST_F(TimerTest, SleepUntilNextWithPartialWork) {
    timer.tick();
    // Do 30ms of "work"
    std::this_thread::sleep_for(std::chrono::milliseconds(30));

    auto wall_start = std::chrono::steady_clock::now();
    timer.sleep_until_next(67.0);  // 15Hz target = 67ms
    auto wall_end = std::chrono::steady_clock::now();

    double wall_ms = std::chrono::duration<double, std::milli>(wall_end - wall_start).count();
    // Should sleep ~37ms (67 - 30), within tolerance
    EXPECT_GE(wall_ms, 25.0)
        << "Should sleep remaining budget (~37ms), got " << wall_ms << "ms";
    EXPECT_LE(wall_ms, 50.0)
        << "Should not overshoot remaining budget, got " << wall_ms << "ms";
}

// ── TEST: get_frequency_hz() returns ~10 at 100ms intervals ──

TEST_F(TimerTest, FrequencyIsZeroBeforeTwoTicks) {
    EXPECT_DOUBLE_EQ(timer.get_frequency_hz(), 0.0)
        << "Frequency should be 0.0 with no ticks";

    timer.tick();
    EXPECT_DOUBLE_EQ(timer.get_frequency_hz(), 0.0)
        << "Frequency should be 0.0 with only 1 tick";
}

TEST_F(TimerTest, FrequencyMeasures10HzAt100msIntervals) {
    // Tick at ~100ms intervals → expect ~10Hz
    timer.tick();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    timer.tick();

    double hz = timer.get_frequency_hz();
    EXPECT_GE(hz, 8.0)
        << "At 100ms intervals, frequency should be ~10Hz, got " << hz << "Hz";
    EXPECT_LE(hz, 12.0)
        << "At 100ms intervals, frequency should be ~10Hz, got " << hz << "Hz";
}

TEST_F(TimerTest, FrequencyMeasures15HzAt67msIntervals) {
    // Tick at ~67ms intervals → expect ~15Hz (the FMS target)
    timer.tick();
    std::this_thread::sleep_for(std::chrono::milliseconds(67));
    timer.tick();

    double hz = timer.get_frequency_hz();
    EXPECT_GE(hz, 12.0)
        << "At 67ms intervals, frequency should be ~15Hz, got " << hz << "Hz";
    EXPECT_LE(hz, 18.0)
        << "At 67ms intervals, frequency should be ~15Hz, got " << hz << "Hz";
}

TEST_F(TimerTest, FrequencyUpdatesWithLatestInterval) {
    // First interval: 100ms (~10Hz)
    timer.tick();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    timer.tick();
    double hz1 = timer.get_frequency_hz();
    EXPECT_GE(hz1, 8.0);
    EXPECT_LE(hz1, 12.0);

    // Second interval: 50ms (~20Hz) — frequency should update
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    timer.tick();
    double hz2 = timer.get_frequency_hz();
    EXPECT_GE(hz2, 16.0)
        << "After 50ms interval, frequency should be ~20Hz, got " << hz2 << "Hz";
    EXPECT_LE(hz2, 24.0)
        << "After 50ms interval, frequency should be ~20Hz, got " << hz2 << "Hz";
}

// ── TEST: Full loop simulation ─────────────────────────────

TEST_F(TimerTest, SimulatedLoopMaintainsTargetFrequency) {
    const double target_ms = 100.0;  // 10Hz for predictable testing
    const int iterations = 5;

    for (int i = 0; i < iterations; ++i) {
        timer.tick();
        // Simulate varying workloads (10-30ms)
        std::this_thread::sleep_for(std::chrono::milliseconds(10 + (i * 5)));
        timer.sleep_until_next(target_ms);
    }

    // After the loop, frequency should be near 10Hz
    double hz = timer.get_frequency_hz();
    EXPECT_GE(hz, 8.0)
        << "Simulated 10Hz loop should measure ~10Hz, got " << hz << "Hz";
    EXPECT_LE(hz, 12.0)
        << "Simulated 10Hz loop should measure ~10Hz, got " << hz << "Hz";

    EXPECT_EQ(timer.tick_count(), static_cast<uint64_t>(iterations))
        << "Tick count should match iterations";
}
