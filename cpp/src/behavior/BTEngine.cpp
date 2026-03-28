// ──────────────────────────────────────────────────────────
// behavior/BTEngine.cpp — Lightweight Behavior Tree Engine
//
// Parses BTCPP v4 XML format using tinyxml2.
// Ticks nodes recursively: Sequence, Fallback, Action, etc.
//
// NOT a full BTCPP replacement — just enough to run AGV
// behavior trees for the FMS simulation.
// ──────────────────────────────────────────────────────────

#include "rdt/behavior/BTEngine.h"

#include <tinyxml2.h>
#include <algorithm>

namespace rdt {

// ── Constructor / Destructor ───────────────────────────

BTEngine::BTEngine()
    : loaded_(false)
{
}

BTEngine::~BTEngine() = default;

// ── Registration ───────────────────────────────────────

void BTEngine::registerAction(const std::string& name, BTActionCallback callback) {
    actions_[name] = std::move(callback);
}

void BTEngine::registerCondition(const std::string& name, BTConditionCallback callback) {
    conditions_[name] = std::move(callback);
}

// ── Loading ────────────────────────────────────────────

bool BTEngine::loadFromXML(const std::string& xml_path) {
    tinyxml2::XMLDocument doc;
    tinyxml2::XMLError err = doc.LoadFile(xml_path.c_str());
    if (err != tinyxml2::XML_SUCCESS) {
        return false;
    }
    return parseDocument(&doc);
}

bool BTEngine::loadFromString(const std::string& xml_string) {
    tinyxml2::XMLDocument doc;
    tinyxml2::XMLError err = doc.Parse(xml_string.c_str());
    if (err != tinyxml2::XML_SUCCESS) {
        return false;
    }
    return parseDocument(&doc);
}

bool BTEngine::parseDocument(void* doc_ptr) {
    auto* doc = static_cast<tinyxml2::XMLDocument*>(doc_ptr);

    // Find the <root> element
    auto* root_elem = doc->FirstChildElement("root");
    if (!root_elem) {
        return false;
    }

    // Read the main tree name
    const char* main_tree = root_elem->Attribute("main_tree_to_execute");
    if (!main_tree) {
        return false;
    }
    main_tree_name_ = main_tree;

    // Parse all <BehaviorTree> elements
    trees_.clear();
    for (auto* bt_elem = root_elem->FirstChildElement("BehaviorTree");
         bt_elem != nullptr;
         bt_elem = bt_elem->NextSiblingElement("BehaviorTree"))
    {
        const char* tree_id = bt_elem->Attribute("ID");
        if (!tree_id) {
            continue;
        }

        // Each BehaviorTree should have exactly one child (the root node)
        auto* child_elem = bt_elem->FirstChildElement();
        if (!child_elem) {
            continue;
        }

        auto root_node = parseNode(child_elem);
        if (root_node) {
            trees_[tree_id] = root_node;
        }
    }

    loaded_ = !trees_.empty() && trees_.count(main_tree_name_) > 0;
    return loaded_;
}

std::shared_ptr<BTNode> BTEngine::parseNode(void* element_ptr) {
    auto* elem = static_cast<tinyxml2::XMLElement*>(element_ptr);
    if (!elem) {
        return nullptr;
    }

    std::string tag = elem->Name();
    auto node = std::make_shared<BTNode>();

    // Determine node type from XML tag
    if (tag == "Sequence") {
        node->type = BTNodeType::SEQUENCE;
    } else if (tag == "ReactiveSequence") {
        node->type = BTNodeType::REACTIVE_SEQUENCE;
    } else if (tag == "Fallback") {
        node->type = BTNodeType::FALLBACK;
    } else if (tag == "Action") {
        node->type = BTNodeType::ACTION;
    } else if (tag == "Condition") {
        node->type = BTNodeType::CONDITION;
    } else if (tag == "Inverter") {
        node->type = BTNodeType::INVERTER;
    } else if (tag == "RepeatNode") {
        node->type = BTNodeType::REPEAT;
    } else if (tag == "RetryNode") {
        node->type = BTNodeType::RETRY;
    } else if (tag == "SubTree") {
        node->type = BTNodeType::SUBTREE;
    } else {
        // Unknown tag — treat as Action (some XMLs use custom action names)
        node->type = BTNodeType::ACTION;
    }

    // Read the ID attribute
    const char* id_attr = elem->Attribute("ID");
    if (id_attr) {
        node->id = id_attr;
    } else {
        // For unknown/custom tags, use the tag name as the ID
        node->id = tag;
    }

    // Read all XML attributes as params
    for (auto* attr = elem->FirstAttribute(); attr != nullptr; attr = attr->Next()) {
        std::string attr_name = attr->Name();
        if (attr_name != "ID") {  // ID is stored separately
            node->params[attr_name] = attr->Value();
        }
    }

    // Read num_cycles for Repeat/Retry nodes
    if (node->type == BTNodeType::REPEAT || node->type == BTNodeType::RETRY) {
        const char* cycles = elem->Attribute("num_cycles");
        if (cycles) {
            node->num_cycles = std::atoi(cycles);
        }
        const char* attempts = elem->Attribute("num_attempts");
        if (attempts) {
            node->num_cycles = std::atoi(attempts);
        }
    }

    // Parse child elements
    for (auto* child = elem->FirstChildElement();
         child != nullptr;
         child = child->NextSiblingElement())
    {
        auto child_node = parseNode(child);
        if (child_node) {
            node->children.push_back(child_node);
        }
    }

    return node;
}

// ── Ticking ────────────────────────────────────────────

BTStatus BTEngine::tick() {
    if (!loaded_) {
        return BTStatus::FAILURE;
    }

    auto it = trees_.find(main_tree_name_);
    if (it == trees_.end()) {
        return BTStatus::FAILURE;
    }

    return tickNode(it->second);
}

BTStatus BTEngine::tickNode(std::shared_ptr<BTNode> node) {
    if (!node) {
        return BTStatus::FAILURE;
    }

    switch (node->type) {
        case BTNodeType::SEQUENCE:          return tickSequence(node);
        case BTNodeType::REACTIVE_SEQUENCE: return tickReactiveSequence(node);
        case BTNodeType::FALLBACK:          return tickFallback(node);
        case BTNodeType::ACTION:            return tickAction(node);
        case BTNodeType::CONDITION:         return tickCondition(node);
        case BTNodeType::INVERTER:          return tickInverter(node);
        case BTNodeType::REPEAT:            return tickRepeat(node);
        case BTNodeType::RETRY:             return tickRetry(node);
        case BTNodeType::SUBTREE:           return tickSubTree(node);
    }
    return BTStatus::FAILURE;
}

BTStatus BTEngine::tickSequence(std::shared_ptr<BTNode> node) {
    // Resume from where we left off (current_child_index)
    for (int& i = node->current_child_index;
         i < static_cast<int>(node->children.size());
         ++i)
    {
        BTStatus child_status = tickNode(node->children[i]);

        if (child_status == BTStatus::RUNNING) {
            return BTStatus::RUNNING;
        }
        if (child_status == BTStatus::FAILURE) {
            node->current_child_index = 0;  // reset for next tick
            return BTStatus::FAILURE;
        }
        // SUCCESS — continue to next child
    }

    // All children succeeded
    node->current_child_index = 0;
    return BTStatus::SUCCESS;
}

BTStatus BTEngine::tickReactiveSequence(std::shared_ptr<BTNode> node) {
    // Always re-tick from the first child every tick
    for (auto& child : node->children) {
        BTStatus child_status = tickNode(child);

        if (child_status == BTStatus::RUNNING) {
            return BTStatus::RUNNING;
        }
        if (child_status == BTStatus::FAILURE) {
            return BTStatus::FAILURE;
        }
    }
    return BTStatus::SUCCESS;
}

BTStatus BTEngine::tickFallback(std::shared_ptr<BTNode> node) {
    // Resume from where we left off
    for (int& i = node->current_child_index;
         i < static_cast<int>(node->children.size());
         ++i)
    {
        BTStatus child_status = tickNode(node->children[i]);

        if (child_status == BTStatus::RUNNING) {
            return BTStatus::RUNNING;
        }
        if (child_status == BTStatus::SUCCESS) {
            node->current_child_index = 0;  // reset for next tick
            return BTStatus::SUCCESS;
        }
        // FAILURE — continue to next child
    }

    // All children failed
    node->current_child_index = 0;
    return BTStatus::FAILURE;
}

BTStatus BTEngine::tickAction(std::shared_ptr<BTNode> node) {
    auto it = actions_.find(node->id);
    if (it == actions_.end()) {
        // Unregistered action — treat as SUCCESS (non-critical)
        return BTStatus::SUCCESS;
    }
    return it->second(node->params);
}

BTStatus BTEngine::tickCondition(std::shared_ptr<BTNode> node) {
    auto it = conditions_.find(node->id);
    if (it == conditions_.end()) {
        // Unregistered condition — treat as FAILURE (conservative)
        return BTStatus::FAILURE;
    }
    return it->second(node->params) ? BTStatus::SUCCESS : BTStatus::FAILURE;
}

BTStatus BTEngine::tickInverter(std::shared_ptr<BTNode> node) {
    if (node->children.empty()) {
        return BTStatus::FAILURE;
    }

    BTStatus child_status = tickNode(node->children[0]);
    switch (child_status) {
        case BTStatus::SUCCESS: return BTStatus::FAILURE;
        case BTStatus::FAILURE: return BTStatus::SUCCESS;
        case BTStatus::RUNNING: return BTStatus::RUNNING;
    }
    return BTStatus::FAILURE;
}

BTStatus BTEngine::tickRepeat(std::shared_ptr<BTNode> node) {
    if (node->children.empty()) {
        return BTStatus::FAILURE;
    }

    bool infinite = (node->num_cycles < 0);

    while (infinite || node->cycle_count < node->num_cycles) {
        BTStatus child_status = tickNode(node->children[0]);

        if (child_status == BTStatus::RUNNING) {
            return BTStatus::RUNNING;
        }
        if (child_status == BTStatus::FAILURE) {
            node->cycle_count = 0;
            resetNode(node->children[0]);
            return BTStatus::FAILURE;
        }

        // SUCCESS — increment and loop
        node->cycle_count++;
        resetNode(node->children[0]);

        if (!infinite && node->cycle_count >= node->num_cycles) {
            node->cycle_count = 0;
            return BTStatus::SUCCESS;
        }

        // For infinite loops, return RUNNING to yield control
        if (infinite) {
            return BTStatus::RUNNING;
        }
    }

    node->cycle_count = 0;
    return BTStatus::SUCCESS;
}

BTStatus BTEngine::tickRetry(std::shared_ptr<BTNode> node) {
    if (node->children.empty()) {
        return BTStatus::FAILURE;
    }

    bool infinite = (node->num_cycles < 0);

    BTStatus child_status = tickNode(node->children[0]);

    if (child_status == BTStatus::SUCCESS) {
        node->cycle_count = 0;
        return BTStatus::SUCCESS;
    }

    if (child_status == BTStatus::RUNNING) {
        return BTStatus::RUNNING;
    }

    // FAILURE — retry
    node->cycle_count++;
    resetNode(node->children[0]);

    if (!infinite && node->cycle_count >= node->num_cycles) {
        node->cycle_count = 0;
        return BTStatus::FAILURE;
    }

    // Return RUNNING to signal we'll retry on next tick
    return BTStatus::RUNNING;
}

BTStatus BTEngine::tickSubTree(std::shared_ptr<BTNode> node) {
    auto it = trees_.find(node->id);
    if (it == trees_.end()) {
        return BTStatus::FAILURE;
    }
    return tickNode(it->second);
}

// ── Reset ──────────────────────────────────────────────

void BTEngine::reset() {
    for (auto& [name, root] : trees_) {
        resetNode(root);
    }
}

void BTEngine::resetNode(std::shared_ptr<BTNode> node) {
    if (!node) return;

    node->current_child_index = 0;
    node->cycle_count = 0;

    for (auto& child : node->children) {
        resetNode(child);
    }
}

// ── Queries ────────────────────────────────────────────

bool BTEngine::isLoaded() const {
    return loaded_;
}

std::string BTEngine::getMainTreeName() const {
    return main_tree_name_;
}

size_t BTEngine::getActionCount() const {
    return actions_.size();
}

size_t BTEngine::getConditionCount() const {
    return conditions_.size();
}

size_t BTEngine::getSubtreeCount() const {
    return trees_.size();
}

} // namespace rdt
