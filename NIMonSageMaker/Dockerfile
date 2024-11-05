FROM nvcr.io/nvidia/nim/medical_imaging_vista3d:24.03
USER 0

ENV CADDY_BINURL=https://caddyserver.com/api/download?os=linux&arch=amd64
ENV CADDY_CONF=/opt/caddy-config.json
ENV AWS_ACCESS_KEY_ID=
ENV AWS_SECRET_ACCESS_KEY=
ENV AWS_REGION=us-east-1

COPY launch.sh caddy-config.json serve /opt/
COPY nimapi_index.py /opt/nvidia/vista3d/nimapi/index.py
RUN chmod u+x /opt/serve

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y build-essential && \
    apt-get install -y software-properties-common && \
    apt-get install -y byobu curl git htop man unzip vim wget && \
    apt-get install -y cmake libssl-dev nghttp2 libnghttp2-dev && \
    apt-get install -y curl python-pip && \
    apt-get autoremove -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade boto3 botocore aws-requests-auth SimpleITK nvidia-nvimgcodec-cu12 cupy-cuda12x pydicom

WORKDIR /root
RUN \
    git clone https://github.com/aws-samples/aws-healthimaging-samples.git && \
    cd aws-healthimaging-samples/ahi-batch-image-frame-retrieve/ && \
    git submodule update --init --recursive && \
    mkdir -p build && mkdir -p imageFrames && rm -rf imageFrames/* && \
    if [ $(arch) = 'x86_64' ]; then (cd build && cmake -DCMAKE_BUILD_TYPE=Release -DOJPH_DISABLE_INTEL_SIMD=OFF ..) fi && \
    if  [ $(arch) != 'x86_64' ]; then (cd build && cmake -DCMAKE_BUILD_TYPE=Release -DOJPH_DISABLE_INTEL_SIMD=ON ..) fi && \
    (cd build && make -j) || { exit 1; }

RUN curl -L -o "/usr/local/bin/caddy" "$CADDY_BINURL" && \
    chmod a+x /usr/local/bin/caddy /opt/launch.sh

ENTRYPOINT ["sh", "-xe", "-c", "/opt/launch.sh -c $CADDY_CONF -e /opt/serve"]

