# ============================================================
# Stage 1: C++ Builder — compile FMS server with vcpkg deps
# ============================================================
FROM ubuntu:22.04 AS cpp-builder

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install build toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    zip \
    unzip \
    tar \
    pkg-config \
    libssl-dev \
    ninja-build \
    && apt-get clean \
    && true

# Clone and bootstrap vcpkg
RUN git clone https://github.com/microsoft/vcpkg.git /vcpkg \
    && /vcpkg/bootstrap-vcpkg.sh -disableMetrics

ENV VCPKG_ROOT=/vcpkg
ENV PATH="/vcpkg:${PATH}"

# Set up build directory
WORKDIR /app

# Copy dependency manifests first (layer caching — deps change rarely)
COPY vcpkg.json /app/vcpkg.json
COPY CMakeLists.txt /app/CMakeLists.txt
COPY cpp/ /app/cpp/

# Configure with cmake + vcpkg toolchain
# vcpkg will install all dependencies declared in vcpkg.json
RUN cmake -B build -S . \
    -DCMAKE_TOOLCHAIN_FILE=/vcpkg/scripts/buildsystems/vcpkg.cmake \
    -DCMAKE_BUILD_TYPE=Release

# Build — parallel using all available cores
RUN cmake --build build --parallel $(nproc)

# ============================================================
# Stage 2: Frontend Builder — build React dashboard
# ============================================================
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install
COPY frontend/ ./
RUN npm run build

# ============================================================
# Stage 3: Runtime — Python + compiled C++ binaries + frontend
# ============================================================
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11 and runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    libssl3 \
    curl \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && apt-get clean \
    && true

WORKDIR /app

# Copy compiled C++ binaries from builder stage
COPY --from=cpp-builder /app/build/cpp/fms_server /app/bin/fms_server

# Copy shared libraries the C++ binary might need
# (vcpkg builds are mostly static — this dir may be empty)
COPY --from=cpp-builder /app/build/cpp/ /tmp/cpp-build/
RUN mkdir -p /app/lib && find /tmp/cpp-build -name '*.so*' -exec cp {} /app/lib/ \; 2>/dev/null; true

# Set library path for any shared deps
ENV LD_LIBRARY_PATH=/app/lib:${LD_LIBRARY_PATH}

# Install Python dependencies
COPY python/requirements.txt /app/python/requirements.txt
RUN python3.11 -m pip install --no-cache-dir -r /app/python/requirements.txt

# Copy application code
COPY configs/ /app/configs/
COPY python/ /app/python/
COPY gazebo/ /app/gazebo/

# Copy built frontend from frontend-builder
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# Copy and prepare startup script
COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Ports:
#   65123 — C++ TCP server (robot protocol)
#   7012  — C++ REST server (fleet API)
#   8029  — Python FastAPI (API + intelligence)
#   5199  — React Dashboard
EXPOSE 65123 7012 8029 5199

CMD ["/app/start.sh"]
