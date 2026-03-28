// ──────────────────────────────────────────────────────────
// test_bt.cpp — Unit tests for the Lightweight BT Engine
//
// Tests: XML loading, node ticking, action/condition dispatch,
//        full AGV lifecycle, charge sequence, error recovery.
// ──────────────────────────────────────────────────────────

#include <gtest/gtest.h>
#include "rdt/behavior/BTEngine.h"
#include "rdt/behavior/ActionNodes.h"
#include "rdt/behavior/ConditionNodes.h"
#include "rdt/core/Config.h"

using namespace rdt;

#ifndef RDT_PROJECT_ROOT
#error "RDT_PROJECT_ROOT must be defined by CMake"
#endif

static std::string projectRoot() { return RDT_PROJECT_ROOT; }

static RobotConfig loadTestConfig() {
    return Config::loadRobotConfig(
        projectRoot() + "/configs/robots/unidirectional.yaml");
}

// ═══════════════════════════════════════════════════════
// 1. XML Loading Tests
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, LoadDefaultAGVXml) {
    BTEngine engine;
    bool result = engine.loadFromXML(
        projectRoot() + "/configs/behavior_trees/default_agv.xml");
    EXPECT_TRUE(result);
    EXPECT_TRUE(engine.isLoaded());
    EXPECT_EQ(engine.getMainTreeName(), "AGV_Main");
}

TEST(BTEngineTest, LoadFromStringSucceeds) {
    BTEngine engine;
    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="TestTree">
            <BehaviorTree ID="TestTree">
                <Sequence>
                    <Action ID="DoSomething"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    EXPECT_TRUE(engine.loadFromString(xml));
    EXPECT_TRUE(engine.isLoaded());
    EXPECT_EQ(engine.getMainTreeName(), "TestTree");
}

TEST(BTEngineTest, LoadInvalidXmlReturnsFalse) {
    BTEngine engine;
    EXPECT_FALSE(engine.loadFromString("not xml at all"));
    EXPECT_FALSE(engine.isLoaded());
}

TEST(BTEngineTest, LoadMissingFileReturnsFalse) {
    BTEngine engine;
    EXPECT_FALSE(engine.loadFromXML("/nonexistent/path.xml"));
    EXPECT_FALSE(engine.isLoaded());
}

TEST(BTEngineTest, LoadXmlMissingRootReturnsFalse) {
    BTEngine engine;
    std::string xml = R"(<?xml version="1.0"?><notroot/>)";
    EXPECT_FALSE(engine.loadFromString(xml));
}

TEST(BTEngineTest, LoadMultipleSubtrees) {
    BTEngine engine;
    bool result = engine.loadFromXML(
        projectRoot() + "/configs/behavior_trees/default_agv.xml");
    EXPECT_TRUE(result);
    // default_agv.xml has: AGV_Main, WaitForTask, ExecuteTask, BatteryManagement, ErrorRecovery
    EXPECT_GE(engine.getSubtreeCount(), 5u);
}

// ═══════════════════════════════════════════════════════
// 2. Sequence Node Tests
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, SequenceAllSucceed) {
    BTEngine engine;
    int call_count = 0;

    engine.registerAction("A", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });
    engine.registerAction("B", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });
    engine.registerAction("C", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Sequence>
                    <Action ID="A"/>
                    <Action ID="B"/>
                    <Action ID="C"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    BTStatus status = engine.tick();
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(call_count, 3);
}

TEST(BTEngineTest, SequenceFailsOnFirstFailure) {
    BTEngine engine;
    int call_count = 0;

    engine.registerAction("A", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });
    engine.registerAction("B", [&](const BTParams&) { call_count++; return BTStatus::FAILURE; });
    engine.registerAction("C", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Sequence>
                    <Action ID="A"/>
                    <Action ID="B"/>
                    <Action ID="C"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    BTStatus status = engine.tick();
    EXPECT_EQ(status, BTStatus::FAILURE);
    EXPECT_EQ(call_count, 2);  // C never called
}

TEST(BTEngineTest, SequenceReturnsRunning) {
    BTEngine engine;
    int tick_num = 0;

    engine.registerAction("A", [&](const BTParams&) { return BTStatus::SUCCESS; });
    engine.registerAction("B", [&](const BTParams&) {
        tick_num++;
        return (tick_num >= 3) ? BTStatus::SUCCESS : BTStatus::RUNNING;
    });
    engine.registerAction("C", [&](const BTParams&) { return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Sequence>
                    <Action ID="A"/>
                    <Action ID="B"/>
                    <Action ID="C"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::RUNNING);   // tick 1: B returns RUNNING
    EXPECT_EQ(engine.tick(), BTStatus::RUNNING);   // tick 2: B returns RUNNING
    EXPECT_EQ(engine.tick(), BTStatus::SUCCESS);   // tick 3: B succeeds, C succeeds
}

// ═══════════════════════════════════════════════════════
// 3. Fallback Node Tests
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, FallbackSucceedsOnFirstSuccess) {
    BTEngine engine;
    int call_count = 0;

    engine.registerAction("A", [&](const BTParams&) { call_count++; return BTStatus::FAILURE; });
    engine.registerAction("B", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });
    engine.registerAction("C", [&](const BTParams&) { call_count++; return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Fallback>
                    <Action ID="A"/>
                    <Action ID="B"/>
                    <Action ID="C"/>
                </Fallback>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::SUCCESS);
    EXPECT_EQ(call_count, 2);  // C never called
}

TEST(BTEngineTest, FallbackAllFail) {
    BTEngine engine;

    engine.registerAction("A", [](const BTParams&) { return BTStatus::FAILURE; });
    engine.registerAction("B", [](const BTParams&) { return BTStatus::FAILURE; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Fallback>
                    <Action ID="A"/>
                    <Action ID="B"/>
                </Fallback>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::FAILURE);
}

// ═══════════════════════════════════════════════════════
// 4. Condition Node Tests
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, ConditionTrueReturnsSuccess) {
    BTEngine engine;

    engine.registerCondition("IsReady", [](const BTParams&) { return true; });
    engine.registerAction("Go", [](const BTParams&) { return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Sequence>
                    <Condition ID="IsReady"/>
                    <Action ID="Go"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::SUCCESS);
}

TEST(BTEngineTest, ConditionFalseBlocksSequence) {
    BTEngine engine;
    bool go_called = false;

    engine.registerCondition("IsReady", [](const BTParams&) { return false; });
    engine.registerAction("Go", [&](const BTParams&) { go_called = true; return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Sequence>
                    <Condition ID="IsReady"/>
                    <Action ID="Go"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::FAILURE);
    EXPECT_FALSE(go_called);
}

// ═══════════════════════════════════════════════════════
// 5. Inverter Node Test
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, InverterFlipsResult) {
    BTEngine engine;

    engine.registerCondition("IsBad", [](const BTParams&) { return true; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Inverter>
                    <Condition ID="IsBad"/>
                </Inverter>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    // IsBad returns true (SUCCESS), inverter flips to FAILURE
    EXPECT_EQ(engine.tick(), BTStatus::FAILURE);
}

// ═══════════════════════════════════════════════════════
// 6. BatteryLow Condition with Real RobotState
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, BatteryLowConditionTriggers) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BatteryModel battery(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.battery = &battery;

    BTEngine engine;
    registerStandardConditions(engine, ctx);

    // Battery starts at 100% — not low
    BTParams empty_params;
    EXPECT_FALSE(conditionBatteryLow(ctx, empty_params));

    // Drain battery below critical threshold (20%)
    // discharge_duration_s is 54000s for 100%, so we need to drain ~81%
    for (int i = 0; i < 50000; ++i) {
        battery.update(1.0, true, false);
    }
    EXPECT_TRUE(battery.getPercentage() < 20.0);
    EXPECT_TRUE(conditionBatteryLow(ctx, empty_params));
}

TEST(BTEngineTest, BatteryAboveThresholdWithXMLParam) {
    RobotConfig config = loadTestConfig();
    BatteryModel battery(config);
    BTRobotContext ctx;
    ctx.battery = &battery;

    // Battery at 100%, threshold 20% — above
    BTParams params;
    params["threshold_pct"] = "20";
    EXPECT_TRUE(conditionBatteryAboveThreshold(ctx, params));

    // Drain to ~15%
    for (int i = 0; i < 48000; ++i) {
        battery.update(1.0, true, false);
    }

    double pct = battery.getPercentage();
    EXPECT_LT(pct, 20.0);
    EXPECT_FALSE(conditionBatteryAboveThreshold(ctx, params));
}

// ═══════════════════════════════════════════════════════
// 7. Action Node: Move Sequence
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, MoveActionTransitionsAndCompletes) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.move_complete = false;

    BTParams params;
    params["target_node"] = "k3";

    // First call: IDLE → MOVING, returns RUNNING
    BTStatus status = actionNavigateToNode(ctx, params);
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::MOVING);

    // Sim signals: not arrived yet
    status = actionNavigateToNode(ctx, params);
    EXPECT_EQ(status, BTStatus::RUNNING);

    // Sim signals: arrived
    ctx.move_complete = true;
    status = actionNavigateToNode(ctx, params);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::IDLE);
}

// ═══════════════════════════════════════════════════════
// 8. Charge Sequence: Dock → StartCharging → Undock
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, ChargeSequenceDockChargeUndock) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BatteryModel battery(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.battery = &battery;

    BTParams empty;

    // Step 1: Dock — IDLE → DOCKING
    BTStatus status = actionDockAtCharger(ctx, empty);
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::DOCKING);

    // Sim: dock complete
    ctx.dock_complete = true;
    status = actionDockAtCharger(ctx, empty);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::DOCKING);  // still docking until StartCharging

    // Step 2: Start charging — DOCKING → CHARGING
    status = actionStartCharging(ctx, empty);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::CHARGING);
    EXPECT_TRUE(battery.isCharging());

    // Step 3: Undock — CHARGING → IDLE
    status = actionUndockFromCharger(ctx, empty);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::IDLE);
    EXPECT_FALSE(battery.isCharging());
}

// ═══════════════════════════════════════════════════════
// 9. Load/Unload Attachment
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, LoadingAttachmentActionCode14) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;

    BTParams params;
    params["action_code"] = "14";  // loading

    // IDLE → LOADING
    BTStatus status = actionExecuteAttachment(ctx, params);
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::LOADING);

    // Still loading
    status = actionExecuteAttachment(ctx, params);
    EXPECT_EQ(status, BTStatus::RUNNING);

    // Done
    ctx.attachment_done = true;
    status = actionExecuteAttachment(ctx, params);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::IDLE);
    EXPECT_TRUE(ctx.cargo_secured);
}

TEST(BTEngineTest, UnloadingAttachmentActionCode15) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.cargo_secured = true;

    BTParams params;
    params["action_code"] = "15";  // unloading

    // IDLE → UNLOADING
    BTStatus status = actionExecuteAttachment(ctx, params);
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::UNLOADING);

    ctx.attachment_done = true;
    status = actionExecuteAttachment(ctx, params);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::IDLE);
    EXPECT_FALSE(ctx.cargo_secured);
}

// ═══════════════════════════════════════════════════════
// 10. SubTree Delegation
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, SubTreeDelegation) {
    BTEngine engine;
    bool sub_called = false;

    engine.registerAction("SubAction", [&](const BTParams&) {
        sub_called = true;
        return BTStatus::SUCCESS;
    });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="Main">
            <BehaviorTree ID="Main">
                <SubTree ID="Child"/>
            </BehaviorTree>
            <BehaviorTree ID="Child">
                <Action ID="SubAction"/>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::SUCCESS);
    EXPECT_TRUE(sub_called);
}

// ═══════════════════════════════════════════════════════
// 11. Task Available Condition
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, TaskAvailableCondition) {
    BTRobotContext ctx;
    BTParams empty;

    ctx.task_available = false;
    EXPECT_FALSE(conditionTaskAvailable(ctx, empty));

    ctx.task_available = true;
    EXPECT_TRUE(conditionTaskAvailable(ctx, empty));
}

// ═══════════════════════════════════════════════════════
// 12. Error Recovery: SendActionCode resets
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, SendActionCodeResetsError) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.has_errors = true;

    // Move to ERROR state: IDLE → MOVING → ERROR
    sm.transitionTo(RobotState::MOVING);
    sm.transitionTo(RobotState::ERROR);
    EXPECT_EQ(sm.getCurrentState(), RobotState::ERROR);

    BTParams params;
    params["action_code"] = "31";  // reset_errors

    BTStatus status = actionSendActionCode(ctx, params);
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::IDLE);
    EXPECT_FALSE(ctx.has_errors);
}

// ═══════════════════════════════════════════════════════
// 13. WaitUntilCharged Action
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, WaitUntilChargedReturnsRunningThenSuccess) {
    RobotConfig config = loadTestConfig();
    BatteryModel battery(config);
    BTRobotContext ctx;
    ctx.battery = &battery;

    // Drain battery to 50%
    // discharge_duration_s=54000 for 100%, so drain ~27000s for 50%
    for (int i = 0; i < 27000; ++i) {
        battery.update(1.0, true, false);
    }
    double pct = battery.getPercentage();
    EXPECT_LT(pct, 60.0);

    BTParams params;
    params["target_pct"] = "95";

    // Should return RUNNING since battery is below 95%
    EXPECT_EQ(actionWaitUntilCharged(ctx, params), BTStatus::RUNNING);

    // Charge battery
    battery.startCharging();
    // charge_duration_s=600 for 0→100%, so charge ~570s to get above 95%
    for (int i = 0; i < 600; ++i) {
        battery.update(1.0, false, false);
    }
    EXPECT_GE(battery.getPercentage(), 95.0);

    EXPECT_EQ(actionWaitUntilCharged(ctx, params), BTStatus::SUCCESS);
}

// ═══════════════════════════════════════════════════════
// 14. Registration Counts
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, RegistrationCounts) {
    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BatteryModel battery(config);
    ObstacleHandler obstacles(config);
    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.battery = &battery;
    ctx.obstacles = &obstacles;

    BTEngine engine;
    registerStandardActions(engine, ctx);
    registerStandardConditions(engine, ctx);

    // 17 action handlers registered (11 standard + 6 AMR)
    EXPECT_EQ(engine.getActionCount(), 17u);
    // 10 condition handlers registered (7 standard + 3 AMR)
    EXPECT_EQ(engine.getConditionCount(), 10u);
}

// ═══════════════════════════════════════════════════════
// 15. Full AGV Lifecycle: idle → task → move → load →
//     move → unload → battery check
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, FullAGVLifecycle) {
    // Build a simplified AGV tree that exercises the full lifecycle
    // without the infinite repeat (which requires RUNNING yields)
    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="Lifecycle">
            <BehaviorTree ID="Lifecycle">
                <Sequence>
                    <!-- Check for task -->
                    <Condition ID="TaskAvailable"/>
                    <Action ID="AcceptTask" task_id="T001"/>

                    <!-- Move to pickup -->
                    <Action ID="NavigateToNode" target_node="pickup_1"/>

                    <!-- Load -->
                    <Action ID="ExecuteAttachment" action_code="14" timeout_s="10"/>

                    <!-- Move to drop -->
                    <Action ID="NavigateToNode" target_node="drop_1"/>

                    <!-- Unload -->
                    <Action ID="ExecuteAttachment" action_code="15" timeout_s="10"/>

                    <!-- Report complete -->
                    <Action ID="ReportTaskComplete" task_id="T001"/>

                    <!-- Battery check via Fallback -->
                    <Fallback>
                        <Condition ID="BatteryAboveThreshold" threshold_pct="20"/>
                        <Sequence>
                            <Action ID="NavigateToNode" target_node="charger_1"/>
                            <Action ID="DockAtCharger" action_code="2"/>
                            <Action ID="StartCharging" action_code="3"/>
                            <Action ID="UndockFromCharger" action_code="4"/>
                        </Sequence>
                    </Fallback>
                </Sequence>
            </BehaviorTree>
        </root>
    )";

    RobotConfig config = loadTestConfig();
    RobotStateMachine sm(config);
    BatteryModel battery(config);
    ObstacleHandler obstacles(config);

    BTRobotContext ctx;
    ctx.state_machine = &sm;
    ctx.battery = &battery;
    ctx.obstacles = &obstacles;
    ctx.task_available = true;

    BTEngine engine;
    registerStandardActions(engine, ctx);
    registerStandardConditions(engine, ctx);
    ASSERT_TRUE(engine.loadFromString(xml));

    // === Phase 1: Task check + accept ===
    // TaskAvailable=true, AcceptTask succeeds
    // NavigateToNode: IDLE→MOVING, returns RUNNING
    BTStatus status = engine.tick();
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::MOVING);
    EXPECT_EQ(ctx.current_task_id, "T001");

    // === Phase 2: Move to pickup completes ===
    ctx.move_complete = true;
    status = engine.tick();
    // Move completes (MOVING→IDLE), then ExecuteAttachment(14): IDLE→LOADING, RUNNING
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::LOADING);

    // === Phase 3: Loading completes ===
    ctx.attachment_done = true;
    ctx.move_complete = false;  // reset for next move
    status = engine.tick();
    // Loading done (LOADING→IDLE), NavigateToNode(drop): IDLE→MOVING, RUNNING
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::MOVING);
    EXPECT_TRUE(ctx.cargo_secured);

    // === Phase 4: Move to drop completes ===
    ctx.move_complete = true;
    ctx.attachment_done = false;  // reset for unload
    status = engine.tick();
    // Move done (MOVING→IDLE), ExecuteAttachment(15): IDLE→UNLOADING, RUNNING
    EXPECT_EQ(status, BTStatus::RUNNING);
    EXPECT_EQ(sm.getCurrentState(), RobotState::UNLOADING);

    // === Phase 5: Unloading completes ===
    ctx.attachment_done = true;
    status = engine.tick();
    // Unload done (UNLOADING→IDLE), ReportTaskComplete, battery check
    // Battery is at 100% — BatteryAboveThreshold succeeds, Fallback returns SUCCESS
    // Entire Sequence succeeds
    EXPECT_EQ(status, BTStatus::SUCCESS);
    EXPECT_EQ(sm.getCurrentState(), RobotState::IDLE);
    EXPECT_TRUE(ctx.current_task_id.empty());  // task cleared
    EXPECT_FALSE(ctx.cargo_secured);           // cargo unloaded
}

// ═══════════════════════════════════════════════════════
// 16. Reset clears runtime state
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, ResetClearsState) {
    BTEngine engine;
    int call_count = 0;

    engine.registerAction("A", [&](const BTParams&) {
        call_count++;
        return (call_count == 1) ? BTStatus::RUNNING : BTStatus::SUCCESS;
    });
    engine.registerAction("B", [&](const BTParams&) { return BTStatus::SUCCESS; });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Sequence>
                    <Action ID="A"/>
                    <Action ID="B"/>
                </Sequence>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    // First tick: A returns RUNNING
    EXPECT_EQ(engine.tick(), BTStatus::RUNNING);

    // Reset — should start over
    engine.reset();
    call_count = 0;

    // Next tick should start from A again (reset cleared child index)
    // A returns RUNNING again (call_count becomes 1)
    EXPECT_EQ(engine.tick(), BTStatus::RUNNING);
}

// ═══════════════════════════════════════════════════════
// 17. Unregistered action returns FAILURE (surfaces config errors)
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, UnregisteredActionReturnsFailure) {
    BTEngine engine;

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Action ID="NonExistent"/>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::FAILURE);
}

// ═══════════════════════════════════════════════════════
// 18. Unregistered condition returns FAILURE (conservative)
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, UnregisteredConditionReturnsFailure) {
    BTEngine engine;

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Condition ID="NonExistent"/>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    EXPECT_EQ(engine.tick(), BTStatus::FAILURE);
}

// ═══════════════════════════════════════════════════════
// 19. TickWithoutLoad returns FAILURE
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, TickWithoutLoadReturnsFail) {
    BTEngine engine;
    EXPECT_EQ(engine.tick(), BTStatus::FAILURE);
}

// ═══════════════════════════════════════════════════════
// 20. XML params are passed to action callbacks
// ═══════════════════════════════════════════════════════

TEST(BTEngineTest, XMLParamsPassedToCallback) {
    BTEngine engine;
    std::string received_target;
    std::string received_code;

    engine.registerAction("Navigate", [&](const BTParams& p) {
        auto it_target = p.find("target_node");
        auto it_code   = p.find("action_code");
        if (it_target != p.end()) received_target = it_target->second;
        if (it_code   != p.end()) received_code   = it_code->second;
        return BTStatus::SUCCESS;
    });

    std::string xml = R"(
        <root BTCPP_format="4" main_tree_to_execute="T">
            <BehaviorTree ID="T">
                <Action ID="Navigate" target_node="k3" action_code="0" velocity_profile="standard"/>
            </BehaviorTree>
        </root>
    )";
    ASSERT_TRUE(engine.loadFromString(xml));

    engine.tick();
    EXPECT_EQ(received_target, "k3");
    EXPECT_EQ(received_code, "0");
}
