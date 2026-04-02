# fleet_core C++ Dependencies — Manual Installation Guide

The `external/` directory is empty (git submodules not cloned). Here's how to populate it manually using public open-source repos.

## Two types of dependencies:

### Type 1: vcpkg packages (auto-installed by cmake)
These install automatically when vcpkg bootstraps. You just need vcpkg itself.

### Type 2: external/ submodules (must be cloned manually)
These go into `Main_robotics/fleet_core/external/`. All are open source.

---

## Step 1: Install vcpkg

```bash
cd Main_robotics/fleet_core
git clone https://github.com/Microsoft/vcpkg.git ../vcpkg
../vcpkg/bootstrap-vcpkg.sh
```

cmake will find vcpkg and install these automatically:
- glm, libmodbus, curl, eigen3, gtest, gflags, benchmark
- cpptrace, mongo-cxx-driver, rapidjson, simdjson, c4core, ryml
- ceres, asio, jsoncpp, fmt, spdlog, openssl, tinyxml2
- lz4, bzip2, poly2tri, polyclipping, utfcpp, tbb
- cereal, c-ares, breakpad, libzip, zeromq
- abseil, protobuf, grpc, asio-grpc

## Step 2: Clone external/ submodules manually

```bash
cd Main_robotics/fleet_core/external
mkdir -p external && cd external

# RabbitMQ C client
git clone https://github.com/alanxz/rabbitmq-c.git

# RapidXML (header-only)
git clone https://github.com/discord/rapidxml.git rapidXML

# LP Solve (linear programming)
git clone https://github.com/ERGO-Code/HiGHS.git lp_solve
# OR: download from https://sourceforge.net/projects/lpsolve/

# OSQP (quadratic solver)
git clone --recursive https://github.com/osqp/osqp.git
git clone https://github.com/google/osqp-cpp.git

# Simple Web Server (header-only HTTP)
git clone https://github.com/eidheim/Simple-Web-Server.git

# BehaviorTree.CPP v4
git clone https://github.com/BehaviorTree/BehaviorTree.CPP.git behaviorTree
cd behaviorTree && git checkout v4.6.2 && cd ..

# Embree (Intel ray tracing — for graphics only, can skip with -DBUILD_GRAPHICS=OFF)
# git clone https://github.com/embree/embree.git

# xlnt (Excel library)
git clone https://github.com/tfussell/xlnt.git
```

## Step 3: Clone protocol/ submodule

```bash
cd Main_robotics/fleet_core

# protocol/ contains Addverb's communication protocol definitions
# This is likely a PRIVATE repo — but we can create a stub
mkdir -p protocol
# If protocol/ just defines message formats, we can stub it
# Check what cmake expects from protocol/
```

## Step 4: Build (in Docker for x86_64)

```bash
# From project root
docker build --platform linux/amd64 -f docker/Dockerfile -t wrie .
```

OR build locally if on Linux x86_64:

```bash
cd Main_robotics/fleet_core
mkdir build && cd build
cmake .. \
  -DBUILD_GRAPHICS=OFF \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_UNIT_TESTS=OFF \
  -DSKIP_CHECKS=ON \
  -DBUILD_SERVER=OFF \
  -DUSE_CLANG=OFF
make -j4 install
```

## What you get after build:

```
fleet_core/install/
├── bin/
│   ├── fmsApp              ← Fleet Management Server
│   └── fmsSimulatorApp     ← Fleet Simulator (for testing)
├── lib/
│   ├── libfleet_core.so
│   └── ...
└── assets/
    ├── scene/BotValley.map
    ├── models/agents/
    └── models/behavior/
```

## Minimum deps for fmsSimulatorApp (no graphics):

Only these external/ dirs are needed:
1. rabbitmq-c (TCP communication)
2. behaviorTree (BTCPP v4)
3. osqp + osqp-cpp (MPC solver)
4. lp_solve (ILP node reservation)
5. rapidXML (config parsing)
6. Simple-Web-Server (REST API)

Skip embree, xlnt, imgui, implot, nanovg, sdl2, glfw3 — those are graphics only.
