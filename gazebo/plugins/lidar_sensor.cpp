/*
 * lidar_sensor.cpp — Gazebo Fortress System Plugin
 *
 * Publishes LiDAR scan data on a gz-transport topic.
 * FOV, range, and ray count are read from SDF parameters.
 * Gaussian noise with configurable stddev is applied to range readings.
 *
 * This plugin is loaded by a <sensor type="gpu_lidar"> element in the robot
 * SDF.  It subscribes to the Gazebo lidar sensor data, adds configurable
 * noise, and republishes on a named topic for the FMS TCP bridge.
 *
 * Build: see CMakeLists.txt in this directory.
 */

#include <cmath>
#include <mutex>
#include <random>
#include <string>

#include <gz/sim/System.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/Sensor.hh>
#include <gz/plugin/Register.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/laserscan.pb.h>

namespace robotic_twin {

/// \brief LidarSensorPlugin — reads GPU lidar data and republishes with noise.
class LidarSensorPlugin
    : public gz::sim::System,
      public gz::sim::ISystemConfigure,
      public gz::sim::ISystemPreUpdate,
      public gz::sim::ISystemPostUpdate
{
public:
    LidarSensorPlugin() = default;
    ~LidarSensorPlugin() override = default;

    // -----------------------------------------------------------------------
    // ISystemConfigure — called once at model load
    // -----------------------------------------------------------------------
    void Configure(
        const gz::sim::Entity &_entity,
        const std::shared_ptr<const sdf::Element> &_sdf,
        gz::sim::EntityComponentManager &_ecm,
        gz::sim::EventManager &_eventMgr) override
    {
        // Read SDF parameters
        if (_sdf->HasElement("fov_deg"))
            fov_deg_ = _sdf->Get<double>("fov_deg");
        if (_sdf->HasElement("range_max"))
            range_max_ = _sdf->Get<double>("range_max");
        if (_sdf->HasElement("range_min"))
            range_min_ = _sdf->Get<double>("range_min");
        if (_sdf->HasElement("num_rays"))
            num_rays_ = _sdf->Get<int>("num_rays");
        if (_sdf->HasElement("noise_stddev"))
            noise_stddev_ = _sdf->Get<double>("noise_stddev");
        if (_sdf->HasElement("topic"))
            publish_topic_ = _sdf->Get<std::string>("topic");

        // Subscribe to the built-in GPU lidar topic
        std::string subscribe_topic = "/lidar";
        if (_sdf->HasElement("subscribe_topic"))
            subscribe_topic = _sdf->Get<std::string>("subscribe_topic");

        node_.Subscribe(subscribe_topic,
                        &LidarSensorPlugin::OnLidarMsg, this);

        // Advertise our output topic
        pub_ = node_.Advertise<gz::msgs::LaserScan>(publish_topic_);

        gzmsg << "[LidarSensorPlugin] Configured:"
              << " fov=" << fov_deg_
              << " range=[" << range_min_ << "," << range_max_ << "]"
              << " rays=" << num_rays_
              << " noise_stddev=" << noise_stddev_
              << " topic=" << publish_topic_
              << std::endl;
    }

    // -----------------------------------------------------------------------
    // ISystemPreUpdate — not used
    // -----------------------------------------------------------------------
    void PreUpdate(
        const gz::sim::UpdateInfo &_info,
        gz::sim::EntityComponentManager &_ecm) override
    {
        // No pre-update work needed.
    }

    // -----------------------------------------------------------------------
    // ISystemPostUpdate — republish with noise
    // -----------------------------------------------------------------------
    void PostUpdate(
        const gz::sim::UpdateInfo &_info,
        const gz::sim::EntityComponentManager &_ecm) override
    {
        // If there's a pending message, add noise and publish
        std::lock_guard<std::mutex> lock(msg_mutex_);
        if (!has_pending_msg_)
            return;

        // Apply Gaussian noise to each range reading
        auto noisy_msg = pending_msg_;
        std::normal_distribution<double> noise_dist(0.0, noise_stddev_);

        for (int i = 0; i < noisy_msg.ranges_size(); ++i) {
            double r = noisy_msg.ranges(i);
            if (std::isfinite(r)) {
                r += noise_dist(rng_);
                // Clamp to valid range
                r = std::max(range_min_, std::min(range_max_, r));
                noisy_msg.set_ranges(i, r);
            }
        }

        pub_.Publish(noisy_msg);
        has_pending_msg_ = false;
    }

private:
    // -----------------------------------------------------------------------
    // Lidar message callback
    // -----------------------------------------------------------------------
    void OnLidarMsg(const gz::msgs::LaserScan &_msg)
    {
        std::lock_guard<std::mutex> lock(msg_mutex_);
        pending_msg_ = _msg;
        has_pending_msg_ = true;
    }

    // Configuration
    double fov_deg_ = 360.0;
    double range_max_ = 5.0;
    double range_min_ = 0.08;
    int    num_rays_ = 360;
    double noise_stddev_ = 0.03;
    std::string publish_topic_ = "/lidar/noisy";

    // Transport
    gz::transport::Node node_;
    gz::transport::Node::Publisher pub_;

    // Message buffer
    std::mutex msg_mutex_;
    gz::msgs::LaserScan pending_msg_;
    bool has_pending_msg_ = false;

    // Random
    std::mt19937 rng_{std::random_device{}()};
};

}  // namespace robotic_twin

GZ_ADD_PLUGIN(
    robotic_twin::LidarSensorPlugin,
    gz::sim::System,
    robotic_twin::LidarSensorPlugin::ISystemConfigure,
    robotic_twin::LidarSensorPlugin::ISystemPreUpdate,
    robotic_twin::LidarSensorPlugin::ISystemPostUpdate)
