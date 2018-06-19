# ==================
# Compile CuraEngine
# ==================
FROM ubuntu:18.04 as curaengine_builder

WORKDIR /srv

# Install compiler and library
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y git cmake build-essential g++ libprotobuf-dev libarcus-dev protobuf-compiler libprotoc-dev

RUN git clone --depth 1 -b WIP_minimal_cura https://github.com/Ultimaker/Cura.git \
 && git clone --depth 1 -b WIP_minimal_uranium https://github.com/Ultimaker/Uranium.git \
 && mkdir -p Cura/materials \
 && git clone --depth 1 -b master https://github.com/Ultimaker/fdm_materials.git /srv/Cura/materials/fdm_materials \
 && git clone --depth 1 -b master https://github.com/Ultimaker/CuraEngine.git \
 && mkdir -p /srv/CuraEngine/build \
 && cd /srv/CuraEngine/build \
 && cmake .. \
 && make \
 && cp /srv/CuraEngine/build/CuraEngine /srv/Cura/

# Clean up
ADD docker/cleanup.sh /srv
RUN rm -rf /srv/CuraEngine \
 && /srv/cleanup.sh

# ==============
# Cura CLI image
# ==============
FROM ubuntu:18.04

WORKDIR /srv

RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends python3 \
    python3-sip python3-arcus python3-savitar \
    libprotobuf10 libgomp1 \
    python3-numpy python3-numpy-stl python3-scipy python3-magic python3-yaml

# Copy necessary parts
COPY --from=curaengine_builder /srv /srv/

# Environment variables
ENV PYTHONPATH=/srv/Cura:/srv/Uranium:$PYTHONPATH

# Remove unneeded packages and clean up APT cache
RUN apt-get autoclean -y \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists \
 && rm -rf /var/log/* \
 && rm -rf /tmp/*

WORKDIR /srv/Cura

ENTRYPOINT ["python3", "cura_app.py"]
