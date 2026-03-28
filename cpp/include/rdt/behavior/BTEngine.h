#pragma once

// ──────────────────────────────────────────────────────────
// rdt/behavior/BTEngine.h — Lightweight Behavior Tree Engine
//
// Custom BT engine that loads BTCPP v4 XML format and ticks
// nodes without depending on BehaviorTree.CPP (which has
// compile errors in v4.6.2 due to a lexy typo).
//
// Supported node types:
//   Sequence        — ticks children left-to-right; fails on first FAILURE
//   ReactiveSequence — re-ticks from first child every tick
//   Fallback        — ticks children left-to-right; succeeds on first SUCCESS
//   Action          — calls a registered callback via action ID
//   Condition       — calls a registered callback, returns SUCCESS/FAILURE
//   Inverter        — decorator that inverts child result
//   RepeatNode      — decorator that repeats child N times (-1 = infinite)
//   RetryNode       — decorator that retries child on FAILURE
//   SubTree         — delegates to another named BehaviorTree
//
// Usage:
//   BTEngine bt;
//   bt.registerAction("Move", [&](const BTParams&) { ... });
//   bt.registerCondition("BatteryLow", [&](const BTParams&) { ... });
//   bt.loadFromXML("configs/behavior_trees/default_agv.xml");
//   BTStatus result = bt.tick();
// ──────────────────────────────────────────────────────────

#include <string>
#include <functional>
#include <memory>
#include <unordered_map>
#include <vector>

namespace rdt {

// ── BT Status ──────────────────────────────────────────

enum class BTStatus {
    SUCCESS,
    FAILURE,
    RUNNING
};

inline std::string bt_status_to_string(BTStatus s) {
    switch (s) {
        case BTStatus::SUCCESS: return "SUCCESS";
        case BTStatus::FAILURE: return "FAILURE";
        case BTStatus::RUNNING: return "RUNNING";
    }
    return "UNKNOWN";
}

// ── BT Parameters ──────────────────────────────────────

/// Key-value parameters attached to Action/Condition nodes from XML attributes.
using BTParams = std::unordered_map<std::string, std::string>;

// ── Callback types ─────────────────────────────────────

/// Action callback: receives XML params, returns BTStatus.
using BTActionCallback = std::function<BTStatus(const BTParams& params)>;

/// Condition callback: receives XML params, returns true (SUCCESS) or false (FAILURE).
using BTConditionCallback = std::function<bool(const BTParams& params)>;

// ── BT Node (internal tree node) ───────────────────────

enum class BTNodeType {
    SEQUENCE,
    REACTIVE_SEQUENCE,
    FALLBACK,
    ACTION,
    CONDITION,
    INVERTER,
    REPEAT,
    RETRY,
    SUBTREE
};

struct BTNode {
    BTNodeType                        type;
    std::string                       id;         // node ID (Action/Condition name, SubTree target)
    BTParams                          params;     // XML attributes
    std::vector<std::shared_ptr<BTNode>> children;

    // Runtime state for Sequence/Fallback (tracks which child is active)
    int current_child_index = 0;

    // Repeat/Retry: how many cycles (-1 = infinite)
    int num_cycles  = 1;
    int cycle_count = 0;
};

// ── BTEngine ───────────────────────────────────────────

class BTEngine {
public:
    BTEngine();
    ~BTEngine();

    /// Register an action handler by name.
    /// The name must match the "ID" attribute in the XML Action node.
    void registerAction(const std::string& name, BTActionCallback callback);

    /// Register a condition handler by name.
    /// The name must match the "ID" attribute in the XML Condition node.
    void registerCondition(const std::string& name, BTConditionCallback callback);

    /// Load a behavior tree from a BTCPP v4 XML file.
    /// @param xml_path  Path to the XML file
    /// @return true if loaded successfully, false on parse error
    bool loadFromXML(const std::string& xml_path);

    /// Load a behavior tree from an XML string (for testing).
    /// @param xml_string  XML content
    /// @return true if loaded successfully
    bool loadFromString(const std::string& xml_string);

    /// Tick the main tree once.
    /// @return the status of the root node after one tick
    BTStatus tick();

    /// Reset all runtime state (child indices, cycle counts).
    void reset();

    /// Check if a tree is loaded.
    bool isLoaded() const;

    /// Get the name of the main tree.
    std::string getMainTreeName() const;

    /// Get the number of registered actions.
    size_t getActionCount() const;

    /// Get the number of registered conditions.
    size_t getConditionCount() const;

    /// Get the number of subtrees loaded.
    size_t getSubtreeCount() const;

private:
    /// Parse all BehaviorTree elements from the XML document.
    bool parseDocument(void* doc_ptr);

    /// Recursively parse an XML element into a BTNode.
    std::shared_ptr<BTNode> parseNode(void* element_ptr);

    /// Tick a single node recursively.
    BTStatus tickNode(std::shared_ptr<BTNode> node);

    /// Tick specific node types.
    BTStatus tickSequence(std::shared_ptr<BTNode> node);
    BTStatus tickReactiveSequence(std::shared_ptr<BTNode> node);
    BTStatus tickFallback(std::shared_ptr<BTNode> node);
    BTStatus tickAction(std::shared_ptr<BTNode> node);
    BTStatus tickCondition(std::shared_ptr<BTNode> node);
    BTStatus tickInverter(std::shared_ptr<BTNode> node);
    BTStatus tickRepeat(std::shared_ptr<BTNode> node);
    BTStatus tickRetry(std::shared_ptr<BTNode> node);
    BTStatus tickSubTree(std::shared_ptr<BTNode> node);

    /// Reset runtime state of a node and all its children.
    void resetNode(std::shared_ptr<BTNode> node);

    // Registered callbacks
    std::unordered_map<std::string, BTActionCallback>    actions_;
    std::unordered_map<std::string, BTConditionCallback> conditions_;

    // Parsed trees: tree_name → root node
    std::unordered_map<std::string, std::shared_ptr<BTNode>> trees_;

    // The name of the main tree to execute
    std::string main_tree_name_;

    // Whether a tree has been loaded
    bool loaded_;
};

} // namespace rdt
