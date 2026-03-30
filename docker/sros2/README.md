# SROS2 Security Configuration

Production ROS2 deployments MUST use SROS2 (Secure ROS2) to encrypt
DDS traffic and authenticate ROS2 nodes. This directory contains the
setup steps and example configuration for the ROS2 Bridge service.

## Overview

SROS2 uses DDS Security plugins with X.509 certificates for:
- **Authentication:** Each ROS2 node proves identity via a signed certificate.
- **Access Control:** Per-topic publish/subscribe permissions.
- **Encryption:** All DDS traffic is encrypted (AES-GCM by default).

## Setup Steps

### 1. Create the keystore

```bash
# Inside the ros2_bridge container (ros:humble base)
ros2 security create_keystore /sros2_keystore
```

### 2. Generate keys for each participant

```bash
# FMS bridge node
ros2 security create_enclave /sros2_keystore /rdt_ros2_bridge

# Per-robot nodes (repeat for each robot)
ros2 security create_enclave /sros2_keystore /AMR-01
ros2 security create_enclave /sros2_keystore /AMR-02
ros2 security create_enclave /sros2_keystore /AGV-01
```

### 3. Define access control policies

Create `policies.xml` in the keystore (see example below):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<policy version="0.2.0">
  <enclaves>
    <!-- FMS Bridge: subscribe to all robot topics, publish nav goals -->
    <enclave path="/rdt_ros2_bridge">
      <profiles>
        <profile ns="/" node="rdt_ros2_bridge">
          <topics publish="ALLOW">
            <topic>*/navigate_to_pose</topic>
            <topic>*/cmd_vel</topic>
          </topics>
          <topics subscribe="ALLOW">
            <topic>*/odom</topic>
            <topic>*/scan</topic>
            <topic>*/battery_state</topic>
            <topic>*/tf</topic>
            <topic>/map</topic>
          </topics>
        </profile>
      </profiles>
    </enclave>

    <!-- Per-robot enclave: publish sensor data, subscribe to commands -->
    <enclave path="/AMR-01">
      <profiles>
        <profile ns="/AMR-01" node="amr01_nav">
          <topics publish="ALLOW">
            <topic>odom</topic>
            <topic>scan</topic>
            <topic>battery_state</topic>
            <topic>tf</topic>
          </topics>
          <topics subscribe="ALLOW">
            <topic>navigate_to_pose</topic>
            <topic>cmd_vel</topic>
          </topics>
        </profile>
      </profiles>
    </enclave>
  </enclaves>
</policy>
```

### 4. Generate permissions from policy

```bash
ros2 security create_permission /sros2_keystore /rdt_ros2_bridge policies.xml
ros2 security create_permission /sros2_keystore /AMR-01 policies.xml
```

### 5. Set environment variables

Add to `docker-compose.yml` or `.env.docker`:

```yaml
environment:
  ROS_SECURITY_KEYSTORE: /sros2_keystore
  ROS_SECURITY_ENABLE: "true"
  ROS_SECURITY_STRATEGY: "Enforce"    # Reject unsigned nodes
  ROS_SECURITY_ENCLAVE_OVERRIDE: /rdt_ros2_bridge
```

### 6. Mount the keystore volume

```yaml
volumes:
  - ./sros2/keystore:/sros2_keystore:ro
```

## Docker Compose Integration

Add the following to `docker-compose.yml` under the `ros2_bridge` service:

```yaml
ros2_bridge:
  image: ros:humble
  environment:
    ROS_SECURITY_KEYSTORE: /sros2_keystore
    ROS_SECURITY_ENABLE: "true"
    ROS_SECURITY_STRATEGY: "Enforce"
    ROS_SECURITY_ENCLAVE_OVERRIDE: /rdt_ros2_bridge
  volumes:
    - ./sros2/keystore:/sros2_keystore:ro
```

## Security Considerations

- **Enforce mode** (`ROS_SECURITY_STRATEGY=Enforce`): Rejects ALL unsigned
  or unauthorized nodes. Use in production.
- **Permissive mode** (`ROS_SECURITY_STRATEGY=Permissive`): Logs violations
  but allows traffic. Use during development/testing only.
- **Key rotation:** Regenerate certificates before expiry (default 10 years).
  Automate with `ros2 security` CLI in CI/CD.
- **Keystore must NOT be committed to git.** Mount at runtime via Docker
  volumes or Kubernetes secrets. The `keystore/` directory is in `.gitignore`.

## File Layout

```
docker/sros2/
  README.md           -- this file (setup guide)
  policies.xml        -- access control policies (committed, no secrets)
  keystore/           -- generated certificates (NOT committed, .gitignore'd)
    enclaves/
      rdt_ros2_bridge/
        cert.pem
        key.pem
        governance.p7s
        permissions.p7s
      AMR-01/
        cert.pem
        key.pem
        ...
```
