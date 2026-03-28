# Robot Configuration

Robot presets are YAML files that define everything about a robot type: how it moves, its physical dimensions, sensor configuration, battery behavior, MPC controller tuning, and firmware action codes.

**YAML configs are the source of truth.** The C++ FMS and Gazebo simulation both read these files at runtime. No robot parameters are hardcoded in code.

## YAML Format

### Sections

#### `name` and `type`
```yaml
name: "DiffDrive_AMR"
type: differential_drive   # Options: differential_drive, unidirectional, omnidirectional
```

#### `motion` — Movement parameters
```yaml
motion:
  max_linear_velocity: 2.0       # m/s — max forward speed
  min_linear_velocity: 0.02      # m/s — minimum before stopping (diff_drive only)
  max_angular_velocity: 2.5      # rad/s — max rotation speed
  min_angular_velocity: 0.02     # rad/s (diff_drive only)
  linear_acceleration: 0.8       # m/s^2 — how fast it speeds up
  linear_deceleration: 0.8       # m/s^2 — how fast it slows down
  jerk_max: 10.0                 # m/s^3 — smoothness of acceleration changes
  position_tolerance: 0.07       # m — "close enough" to target position
  angular_tolerance: 0.025       # rad — "close enough" to target heading
  creep_distance: 0.02           # m — final approach distance (slow approach)
  creep_velocity: 0.02           # m/s — final approach speed
  exit_velocity: 0.4             # m/s — speed when leaving a node
```

For unidirectional robots, `max_linear_velocity_curve` sets reduced speed on turns:
```yaml
  max_linear_velocity_curve: 0.6 # m/s — reduced speed on curves (unidirectional only)
```

#### `dimensions` — Physical size
```yaml
dimensions:
  length: 0.8                    # m
  width: 0.6                     # m
  height: 0.3                    # m
  weight: 50.0                   # kg (empty)
  payload_capacity: 500.0        # kg — max load
  wheel_separation: 0.5          # m — distance between drive wheels
  wheel_radius: 0.075            # m
```

#### `sensors` — Onboard sensors
```yaml
sensors:
  lidar:
    enabled: true
    type: "2d"                   # Options: 2d, 3d
    fov_deg: 360                 # Field of view in degrees (360 for AMR, 30 for AGV)
    range_m: 5.0                 # Max detection range in meters
    rays: 360                    # Number of rays per scan
    height_m: 0.15               # Mounting height from ground
    noise_stddev_m: 0.03         # Gaussian noise standard deviation
  barcode_reader:
    enabled: true
    debounce_ms: 5               # Minimum milliseconds between reads
    failure_threshold: 5         # Consecutive failures before "sensor failing" state
  imu:
    enabled: true                # Inertial measurement unit
    noise_stddev_deg: 3.0        # Heading noise in degrees
```

#### `battery` — Charge/discharge behavior
```yaml
battery:
  charge_duration_s: 600         # Seconds from 0% to 100%
  discharge_duration_s: 54000    # Seconds of operation at 100% (15 hours)
  motion_energy_factor: 1.05     # Energy multiplier when moving (>1.0)
  attachment_energy_factor: 1.0  # Energy multiplier when attachment is active
  critical_threshold_pct: 20     # Seek charger below this percentage
  initial_charge_pct: 100        # Starting charge in simulation
```

#### `obstacle_thresholds` — Safety distances
```yaml
obstacle_thresholds:
  critical_m: 0.7               # Emergency stop distance
  warning_m: 0.8                # Decelerate distance
  planning_m: 1.5               # Replan path distance
```

#### `attachment` — Load handling mechanism
```yaml
attachment:
  type: "none"                   # Options: none, conveyor, lifter, tug
  load_time_s: 3.0              # Seconds to load cargo
  unload_time_s: 3.0            # Seconds to unload cargo
```

#### `mpc` — Model Predictive Controller tuning
```yaml
mpc:
  num_opt_vars: 12              # Optimization variables per solve
  dt: 0.1                       # Time step (seconds)
  position_weight: 1.0          # Cost weight for position tracking
  velocity_weight: 0.0          # Cost weight for velocity tracking
  weight_scale: 0.05            # Overall weight scaling factor
  jerk_scale: 1.0               # Jerk penalty scaling
  acceleration_scale: 1.0       # Acceleration penalty scaling
  final_position_offset: 0.015  # Acceptable final position error (m)
  final_velocity_threshold: 0.05 # Acceptable final velocity (m/s)
  osqp_iterations: 500          # OSQP solver max iterations
  osqp_eps_abs: 0.01            # OSQP absolute tolerance
  osqp_eps_rel: 0.01            # OSQP relative tolerance
```

#### `behavior_tree` — Which BT XML to load
```yaml
behavior_tree: "default_amr.xml"  # File in configs/behavior_trees/
```

#### `action_codes` — Firmware commands
```yaml
action_codes:
  move: 0                        # Navigate to target node
  charge_dock: 2                 # Dock at charging station
  start_charging: 3              # Begin charging
  charge_undock: 4               # Undock from charger
  start_loading: 14              # Activate load mechanism
  start_unloading: 15            # Activate unload mechanism
  reset_errors: 31               # Soft error reset
  hard_reset: 51                 # Full hardware reset
```

#### `response_codes` — Firmware feedback
```yaml
response_codes:
  reached_dock: 10               # Robot arrived at dock position
  reached_predock: 8             # Robot at pre-dock alignment point
  charging_stopped: 18           # Charging finished or interrupted
  charging_error: 501            # Charger communication failure
  load_error: 401                # Load mechanism failure
  unload_error: 402              # Unload mechanism failure
```

## Included Presets

| File | Robot Type | Use Case |
|------|-----------|----------|
| `differential_drive.yaml` | AMR (2-wheel differential) | General warehouse transport, 360-deg LiDAR, supports lifter |
| `unidirectional.yaml` | AGV (forward-only conveyor) | Sortation lines, conveyor top-load, narrow LiDAR FOV |

## Creating a Custom Robot

1. Copy the closest preset:
   ```bash
   cp configs/robots/differential_drive.yaml configs/robots/my_robot.yaml
   ```

2. Edit the values for your robot. At minimum, change:
   - `name` — unique identifier
   - `motion` speeds — match your hardware specs
   - `dimensions` — match your physical robot
   - `battery` durations — from your robot's datasheet
   - `attachment.type` — what load mechanism you have

3. Validate your YAML:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('configs/robots/my_robot.yaml')); print('OK')"
   ```

4. Launch with your preset:
   ```bash
   ROBOT=my_robot docker compose up
   ```
