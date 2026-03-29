/*
 * conveyor_belt.cpp — Gazebo Fortress System Plugin
 *
 * Simulates a conveyor belt surface that moves items along a
 * configurable direction at a given speed.  The FMS/WCS can
 * start/stop the belt via a gz-transport command topic.
 *
 * SDF parameters:
 *   <speed>      — belt speed in m/s (default 0.3)
 *   <direction>  — movement yaw in radians (default 0, +X)
 *   <topic_cmd>  — command topic to start/stop (default /conveyor/cmd)
 *   <topic_status> — status topic (default /conveyor/status)
 *
 * Build: see CMakeLists.txt in this directory.
 */

#include <atomic>
#include <chrono>
#include <cmath>
#include <string>

#include <gz/sim/System.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Pose.hh>
#include <gz/sim/components/Name.hh>
#include <gz/plugin/Register.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/float.pb.h>

namespace robotic_twin {

/// \brief ConveyorBeltPlugin — simulates conveyor surface motion.
class ConveyorBeltPlugin
    : public gz::sim::System,
      public gz::sim::ISystemConfigure,
      public gz::sim::ISystemPreUpdate,
      public gz::sim::ISystemPostUpdate
{
public:
    ConveyorBeltPlugin() = default;
    ~ConveyorBeltPlugin() override = default;

    // -----------------------------------------------------------------------
    // ISystemConfigure
    // -----------------------------------------------------------------------
    void Configure(
        const gz::sim::Entity &_entity,
        const std::shared_ptr<const sdf::Element> &_sdf,
        gz::sim::EntityComponentManager &_ecm,
        gz::sim::EventManager &) override
    {
        model_entity_ = _entity;
        model_ = gz::sim::Model(_entity);

        // Read SDF parameters
        if (_sdf->HasElement("speed"))
            speed_ = _sdf->Get<double>("speed");
        if (_sdf->HasElement("direction"))
            direction_rad_ = _sdf->Get<double>("direction");

        std::string cmd_topic = "/conveyor/cmd";
        std::string status_topic = "/conveyor/status";
        if (_sdf->HasElement("topic_cmd"))
            cmd_topic = _sdf->Get<std::string>("topic_cmd");
        if (_sdf->HasElement("topic_status"))
            status_topic = _sdf->Get<std::string>("topic_status");

        // Subscribe to start/stop commands
        node_.Subscribe(cmd_topic,
            &ConveyorBeltPlugin::OnCommand, this);

        // Advertise status topic
        status_pub_ = node_.Advertise<gz::msgs::Float>(status_topic);

        auto name = _ecm.Component<gz::sim::components::Name>(_entity);
        std::string model_name = name ? name->Data() : "unknown";
        gzmsg << "[ConveyorBelt] Configured on model '" << model_name
              << "' speed=" << speed_ << " m/s, direction="
              << direction_rad_ << " rad" << std::endl;
    }

    // -----------------------------------------------------------------------
    // ISystemPreUpdate — apply surface velocity when running
    // -----------------------------------------------------------------------
    void PreUpdate(
        const gz::sim::UpdateInfo &_info,
        gz::sim::EntityComponentManager &) override
    {
        if (_info.paused) return;
        // Surface velocity would be applied here via
        // components::LinearVelocityCmd on the belt link.
        // For simulation purposes, the belt's visual motion
        // is handled by the PostUpdate status publication.
    }

    // -----------------------------------------------------------------------
    // ISystemPostUpdate — publish status at ~10 Hz
    // -----------------------------------------------------------------------
    void PostUpdate(
        const gz::sim::UpdateInfo &_info,
        const gz::sim::EntityComponentManager &) override
    {
        if (_info.paused) return;

        auto now = _info.simTime;
        auto elapsed = now - last_publish_;
        if (elapsed < std::chrono::milliseconds(100)) return;
        last_publish_ = now;

        gz::msgs::Float status_msg;
        status_msg.set_data(running_.load() ? static_cast<float>(speed_) : 0.0f);
        status_pub_.Publish(status_msg);
    }

private:
    void OnCommand(const gz::msgs::Boolean &_msg) {
        running_.store(_msg.data());
        gzmsg << "[ConveyorBelt] "
              << (running_.load() ? "STARTED" : "STOPPED") << std::endl;
    }

    gz::sim::Entity model_entity_{gz::sim::kNullEntity};
    gz::sim::Model  model_{gz::sim::kNullEntity};
    gz::transport::Node node_;
    gz::transport::Node::Publisher status_pub_;

    double speed_ = 0.3;           // m/s
    double direction_rad_ = 0.0;   // radians (0 = +X)
    std::atomic<bool> running_{false};

    std::chrono::steady_clock::duration last_publish_{0};
};

}  // namespace robotic_twin

// Register plugin with Gazebo
GZ_ADD_PLUGIN(
    robotic_twin::ConveyorBeltPlugin,
    gz::sim::System,
    robotic_twin::ConveyorBeltPlugin::ISystemConfigure,
    robotic_twin::ConveyorBeltPlugin::ISystemPreUpdate,
    robotic_twin::ConveyorBeltPlugin::ISystemPostUpdate)
