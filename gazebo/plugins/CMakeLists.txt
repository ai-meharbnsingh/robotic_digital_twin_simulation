cmake_minimum_required(VERSION 3.16)
project(robotic_twin_gazebo_plugins VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# Find Gazebo Fortress packages
# Try gz-sim7 (Fortress) first, then fall back to gz-sim8 (Harmonic)
# ---------------------------------------------------------------------------
find_package(gz-sim7 QUIET)
if(gz-sim7_FOUND)
    set(GZ_SIM_VER 7)
    message(STATUS "Found Gazebo Fortress (gz-sim7)")
else()
    find_package(gz-sim8 QUIET)
    if(gz-sim8_FOUND)
        set(GZ_SIM_VER 8)
        message(STATUS "Found Gazebo Harmonic (gz-sim8)")
    else()
        # Try ignition-gazebo6 (older naming)
        find_package(ignition-gazebo6 QUIET)
        if(ignition-gazebo6_FOUND)
            set(GZ_SIM_VER 6)
            set(USE_IGNITION TRUE)
            message(STATUS "Found Ignition Gazebo 6")
        else()
            message(WARNING
                "No Gazebo Sim package found (gz-sim7, gz-sim8, ignition-gazebo6). "
                "Plugins will NOT be built. Install Gazebo Fortress or Harmonic.")
            return()
        endif()
    endif()
endif()

# Find transport
if(USE_IGNITION)
    find_package(ignition-transport11 REQUIRED)
    find_package(ignition-msgs8 REQUIRED)
    find_package(ignition-plugin1 REQUIRED COMPONENTS register)
    set(GZ_SIM_LIB ignition-gazebo6::ignition-gazebo6)
    set(GZ_TRANSPORT_LIB ignition-transport11::ignition-transport11)
    set(GZ_MSGS_LIB ignition-msgs8::ignition-msgs8)
    set(GZ_PLUGIN_LIB ignition-plugin1::register)
else()
    set(GZ_TRANSPORT_VER_MAJOR $<IF:$<EQUAL:${GZ_SIM_VER},7>,12,13>)
    find_package(gz-transport${GZ_TRANSPORT_VER_MAJOR} QUIET)
    find_package(gz-msgs QUIET)
    find_package(gz-plugin2 REQUIRED COMPONENTS register)
    set(GZ_SIM_LIB gz-sim${GZ_SIM_VER}::gz-sim${GZ_SIM_VER})
    set(GZ_PLUGIN_LIB gz-plugin2::register)
endif()

# ---------------------------------------------------------------------------
# LiDAR Sensor Plugin
# ---------------------------------------------------------------------------
add_library(lidar_sensor SHARED lidar_sensor.cpp)

target_link_libraries(lidar_sensor
    PRIVATE
        ${GZ_SIM_LIB}
        ${GZ_PLUGIN_LIB}
)

if(GZ_TRANSPORT_LIB)
    target_link_libraries(lidar_sensor PRIVATE ${GZ_TRANSPORT_LIB})
endif()
if(GZ_MSGS_LIB)
    target_link_libraries(lidar_sensor PRIVATE ${GZ_MSGS_LIB})
endif()

# ---------------------------------------------------------------------------
# Barcode Sensor Plugin
# ---------------------------------------------------------------------------
add_library(barcode_sensor SHARED barcode_sensor.cpp)

target_link_libraries(barcode_sensor
    PRIVATE
        ${GZ_SIM_LIB}
        ${GZ_PLUGIN_LIB}
)

if(GZ_TRANSPORT_LIB)
    target_link_libraries(barcode_sensor PRIVATE ${GZ_TRANSPORT_LIB})
endif()
if(GZ_MSGS_LIB)
    target_link_libraries(barcode_sensor PRIVATE ${GZ_MSGS_LIB})
endif()

# ---------------------------------------------------------------------------
# Conveyor Belt Plugin
# ---------------------------------------------------------------------------
add_library(conveyor_belt SHARED conveyor_belt.cpp)

target_link_libraries(conveyor_belt
    PRIVATE
        ${GZ_SIM_LIB}
        ${GZ_PLUGIN_LIB}
)

if(GZ_TRANSPORT_LIB)
    target_link_libraries(conveyor_belt PRIVATE ${GZ_TRANSPORT_LIB})
endif()
if(GZ_MSGS_LIB)
    target_link_libraries(conveyor_belt PRIVATE ${GZ_MSGS_LIB})
endif()

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install(TARGETS lidar_sensor barcode_sensor conveyor_belt
    LIBRARY DESTINATION lib/gazebo_plugins
    ARCHIVE DESTINATION lib/gazebo_plugins
)

message(STATUS "Gazebo plugins configured: lidar_sensor, barcode_sensor, conveyor_belt")
