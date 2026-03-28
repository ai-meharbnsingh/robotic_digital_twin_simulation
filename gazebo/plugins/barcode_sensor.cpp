/*
 * barcode_sensor.cpp — Gazebo Fortress System Plugin
 *
 * Simulates an irayple-style barcode reader mounted under the robot.
 * Reads the robot's world position from Gazebo, checks it against a
 * floor barcode grid (0.8m spacing), and publishes the barcode ID
 * on a gz-transport topic.
 *
 * Features:
 *   - Grid spacing configurable via SDF parameter (default 0.8m)
 *   - Tolerance for barcode detection (how close to grid center)
 *   - Debounce timer matching irayple spec (5ms default)
 *   - Publishes barcode_id as gz::msgs::Int32
 *
 * Build: see CMakeLists.txt in this directory.
 */

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
#include <gz/msgs/int32.pb.h>
#include <gz/msgs/stringmsg.pb.h>

namespace robotic_twin {

/// \brief BarcodeSensorPlugin — simulates floor barcode reader.
class BarcodeSensorPlugin
    : public gz::sim::System,
      public gz::sim::ISystemConfigure,
      public gz::sim::ISystemPostUpdate
{
public:
    BarcodeSensorPlugin() = default;
    ~BarcodeSensorPlugin() override = default;

    // -----------------------------------------------------------------------
    // ISystemConfigure
    // -----------------------------------------------------------------------
    void Configure(
        const gz::sim::Entity &_entity,
        const std::shared_ptr<const sdf::Element> &_sdf,
        gz::sim::EntityComponentManager &_ecm,
        gz::sim::EventManager &_eventMgr) override
    {
        model_entity_ = _entity;

        // SDF parameters
        if (_sdf->HasElement("grid_spacing"))
            grid_spacing_ = _sdf->Get<double>("grid_spacing");
        if (_sdf->HasElement("tolerance"))
            tolerance_ = _sdf->Get<double>("tolerance");
        if (_sdf->HasElement("debounce_ms"))
            debounce_ms_ = _sdf->Get<double>("debounce_ms");
        if (_sdf->HasElement("topic"))
            topic_ = _sdf->Get<std::string>("topic");
        if (_sdf->HasElement("origin_x"))
            origin_x_ = _sdf->Get<double>("origin_x");
        if (_sdf->HasElement("origin_y"))
            origin_y_ = _sdf->Get<double>("origin_y");

        // Advertise barcode ID topic (Int32) and string topic
        pub_id_ = node_.Advertise<gz::msgs::Int32>(topic_);
        pub_str_ = node_.Advertise<gz::msgs::StringMsg>(topic_ + "/string");

        gzmsg << "[BarcodeSensorPlugin] Configured:"
              << " grid_spacing=" << grid_spacing_
              << " tolerance=" << tolerance_
              << " debounce_ms=" << debounce_ms_
              << " topic=" << topic_
              << " origin=(" << origin_x_ << "," << origin_y_ << ")"
              << std::endl;
    }

    // -----------------------------------------------------------------------
    // ISystemPostUpdate — check position against barcode grid
    // -----------------------------------------------------------------------
    void PostUpdate(
        const gz::sim::UpdateInfo &_info,
        const gz::sim::EntityComponentManager &_ecm) override
    {
        if (_info.paused)
            return;

        // Get model world pose
        auto pose_comp = _ecm.Component<gz::sim::components::Pose>(model_entity_);
        if (!pose_comp)
            return;

        const auto &pose = pose_comp->Data();
        double robot_x = pose.Pos().X();
        double robot_y = pose.Pos().Y();

        // Compute nearest grid point
        double rel_x = robot_x - origin_x_;
        double rel_y = robot_y - origin_y_;

        int grid_ix = static_cast<int>(std::round(rel_x / grid_spacing_));
        int grid_iy = static_cast<int>(std::round(rel_y / grid_spacing_));

        double nearest_x = origin_x_ + grid_ix * grid_spacing_;
        double nearest_y = origin_y_ + grid_iy * grid_spacing_;

        double dist = std::sqrt(
            (robot_x - nearest_x) * (robot_x - nearest_x) +
            (robot_y - nearest_y) * (robot_y - nearest_y));

        // Check if within tolerance
        if (dist > tolerance_)
        {
            // Not over a barcode — clear last ID so next detection triggers
            over_barcode_ = false;
            return;
        }

        // Compute barcode ID from grid indices
        // Use a large-enough grid width to avoid collisions
        int barcode_id = grid_iy * grid_cols_ + grid_ix;

        // Debounce — same barcode requires cooldown period
        auto now = _info.simTime;
        auto elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            now - last_publish_time_).count();
        double elapsed_ms = elapsed_ns / 1e6;

        if (over_barcode_ && barcode_id == last_barcode_id_ && elapsed_ms < debounce_ms_)
            return;

        // Publish
        gz::msgs::Int32 id_msg;
        id_msg.set_data(barcode_id);
        pub_id_.Publish(id_msg);

        gz::msgs::StringMsg str_msg;
        str_msg.set_data("BC_" + std::to_string(grid_ix) + "_" + std::to_string(grid_iy));
        pub_str_.Publish(str_msg);

        last_barcode_id_ = barcode_id;
        last_publish_time_ = now;
        over_barcode_ = true;
    }

private:
    gz::sim::Entity model_entity_{gz::sim::kNullEntity};

    // Configuration
    double grid_spacing_ = 0.8;    // metres between barcodes
    double tolerance_ = 0.05;      // metres — detection radius
    double debounce_ms_ = 5.0;     // irayple debounce period
    double origin_x_ = 0.0;       // grid origin X
    double origin_y_ = 0.0;       // grid origin Y
    int    grid_cols_ = 10000;     // virtual grid width for ID calculation
    std::string topic_ = "/barcode";

    // State
    bool over_barcode_ = false;
    int  last_barcode_id_ = -1;
    std::chrono::steady_clock::duration last_publish_time_{};

    // Transport
    gz::transport::Node node_;
    gz::transport::Node::Publisher pub_id_;
    gz::transport::Node::Publisher pub_str_;
};

}  // namespace robotic_twin

GZ_ADD_PLUGIN(
    robotic_twin::BarcodeSensorPlugin,
    gz::sim::System,
    robotic_twin::BarcodeSensorPlugin::ISystemConfigure,
    robotic_twin::BarcodeSensorPlugin::ISystemPostUpdate)
