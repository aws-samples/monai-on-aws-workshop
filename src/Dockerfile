FROM nvcr.io/nvidia/pytorch:21.07-py3

# Set a docker label to advertise multi-model support on the container
LABEL com.amazonaws.sagemaker.capabilities.multi-models=true
# Set a docker label to enable container to use SAGEMAKER_BIND_TO_PORT environment variable if present
LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port=true

ENV TZ=Etc/UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Upgrade installed packages
RUN apt-get update && apt-get upgrade -y && apt-get autoclean && apt-get clean

# Install necessary dependencies for MMS and SageMaker Inference Toolkit
RUN apt-get -y install --no-install-recommends \
    build-essential \
    ca-certificates \
    openjdk-8-jdk-headless \
    python3-distutils \
    python3-gdcm \
    python-is-python3 \
    curl \
    vim \
    cmake \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && python --version \
    && curl -O https://bootstrap.pypa.io/get-pip.py \
    && python get-pip.py

ENV JAVA_HOME /usr/lib/jvm/java-8-openjdk-amd64
ENV DEBUG=YES
ENV KEEP_FILES=YES

# make sure all messages reach the console
ENV PYTHONUNBUFFERED=1

# Install MMS, and SageMaker Inference Toolkit to set up MMS
RUN python -m pip install --upgrade pip boto3 botocore && \
    python -m pip --no-cache-dir install multi-model-server \
                            sagemaker-inference \
                            retrying \
                            monai[all]==1.0.0 \
                            torch>=1.10.2 \
                            numpy>=1.21 \
                            nibabel>=3.2.1 \
                            pydicom==2.3.0 \
                            highdicom==0.19.0 \
                            SimpleITK>=2.0.0 \
                            typeguard>=2.12.1 \
                            monai-deploy-app-sdk==0.5.0 \
                            pylibjpeg-openjpeg \
                            AHItoDICOMInterface



# Copy entrypoint script to the image
COPY dockerd-entrypoint.py /usr/local/bin/dockerd-entrypoint.py
RUN chmod +x /usr/local/bin/dockerd-entrypoint.py

RUN mkdir -p /home/model-server/
RUN chmod a+w /home/model-server/
# Copy the default custom service file to handle incoming data and inference requests
COPY model_handler.py /home/model-server/model_handler.py
COPY app.py /home/model-server/app.py
COPY Api.py /home/model-server/Api.py
COPY ahi_data_loader_operator.py /home/model-server/ahi_data_loader_operator.py

# Model output folder
RUN mkdir -p /home/model-server/output/
RUN chmod a+w /home/model-server/output/

# Define an entrypoint script for the docker image
ENTRYPOINT ["python", "/usr/local/bin/dockerd-entrypoint.py"]

# Define command to be passed to the entrypoint
CMD ["serve"]