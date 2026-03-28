#include <iostream>
#include <spdlog/spdlog.h>
#include "rdt/version.h"

int main(int argc, char* argv[]) {
    spdlog::info("Robotic Digital Twin — FMS Server v{}.{}.{}",
                 RDT_VERSION_MAJOR, RDT_VERSION_MINOR, RDT_VERSION_PATCH);
    spdlog::info("Waiting for implementation...");
    return 0;
}
