# Medical Imaging NIM (NVIDIA Inference Microservice) on AWS

- [Preparation](#preparation)
- [Usage](#usage)
  * [Deploying to Sagemaker](#deploying-to-sagemaker)
  * [Deploying locally](#deploying-locally)
- [Testing (Sagemaker)](#testing--sagemaker-)
  * [Invocation](#invocation)
- [Testing (Local)](#testing--local-)
  * [Health](#health)
  * [Invocation](#invocation-1)
    + [Non-streaming](#non-streaming)
    + [Streaming](#streaming)
- [Cleanup](#cleanup)

## Introduction

This project deploys NVIDIA NIM for Medical Imaging (Vista-3D) with AWS services.

![Architecture Diagram](/Figures/nim-on-sagemaker.png)

## Preparation

Customize the environment variables below to match your AWS, NGC, etc. configuration(s). If needed, customize the the parameters passed to the `launch.sh` call to ensure proper mapping of frontend/backend ports and source entrypoint. At a minimum you should customize the following:
- `NGC_API_KEY`
- `DST_REGISTRY`
- `SG_INST_TYPE`
  - Note that `ml.g5.2xlarge` or similar variants are required for VISTA3D. 
- `SG_EXEC_ROLE_ARN`

First set up environment variables and create ECR image:
```bash
### Set your NGC API Key
export NGC_API_KEY=nvapi-your-api-key

export SRC_IMAGE_PATH=nvcr.io/nvidia/nim/medical_imaging_vista3d:24.03
export SRC_IMAGE_NAME="${SRC_IMAGE_PATH##*/}"
export SRC_IMAGE_NAME="${SRC_IMAGE_NAME%%:*}"
export DST_REGISTRY=your-registry.dkr.ecr.us-west-2.amazonaws.com/nim-shim

# Build shimmed image
docker login nvcr.io
docker pull ${SRC_IMAGE_PATH}
docker build -t ${DST_REGISTRY}:${SRC_IMAGE_NAME} -t nim-shim:latest .

# push to ECR
aws ecr get-login-password --region AWS Region | docker login --username AWS --password-stdin 123456789012.dkr.ecr.AWS Region.amazonaws.com  
aws ecr create-repository --repository-name nim-shim  --region AWS Region
docker push ${DST_REGISTRY}:${SRC_IMAGE_NAME}

export SG_EP_NAME="nim-llm-medical-image-vista3d"
export SG_EP_CONTAINER=${DST_REGISTRY}:${SRC_IMAGE_NAME}
export SG_INST_TYPE=ml.g5.2xlarge 
export SG_EXEC_ROLE_ARN="arn:aws:iam::AWS AccountId:role/service-role/IAM Role Name"
export SG_CONTAINER_STARTUP_TIMEOUT=850 #in seconds 
```

## Usage

### Deploying to Sagemaker

Review logs in Cloudwatch. Ensure proper instance types have been set for the correlated model you're running & startup timeout values have been set to sane values, especially for dynamic download of large models (70b+).

```bash
# Generate model JSON
envsubst < templates/sg-model.template > sg-model.json

# Create Model
aws sagemaker create-model --region us-east-1\
    --cli-input-json file://sg-model.json \
    --execution-role-arn $SG_EXEC_ROLE_ARN

# Create Endpoint Config
aws sagemaker create-endpoint-config --region us-east-1\
    --endpoint-config-name $SG_EP_NAME \
    --production-variants "$(envsubst < templates/sg-prod-variant.template)"

# Create Endpoint
aws sagemaker create-endpoint --region us-east-1\
    --endpoint-name $SG_EP_NAME \
    --endpoint-config-name $SG_EP_NAME
```

### Deploying locally

Start the container and monitor for:
- Caddy download & launch
- Model weight(s) download
- Service startup(s)


```bash
# Optional (but recommended to expedite future NIM launch times)
mkdir -p /opt/nim/cache

# Start NIM Shim container
docker run -it --rm --runtime=nvidia --shm-size=12GB -e NGC_API_KEY=$NGC_API_KEY -v "/opt/nim/cache:/opt/nim/.cache" -p 8080:8080 nim-shim:latest
```

## Testing (Sagemaker)

### Invocation
```bash
# Generate sample payload JSON
envsubst < templates/sg-test-payload.template > sg-invoke-payload.json

# Create sample invocation
aws sagemaker-runtime invoke-endpoint \
    --region AWS Region \
    --endpoint-name $SG_EP_NAME \
    --body file://sg-invoke-payload.json \
    --content-type application/json \
    output.nrrd
```

## Testing (Local)


### Health
Confirm Sagemaker health check will pass:
```bash
curl -X GET 127.0.0.1:8080/ping -vvv
```

### Invocation

```bash
curl -X POST 'http://0.0.0.0:8080/invocations' \
  -H "Content-Type: application/json" \
  --output output.nrrd \
  -d '{
    "image": "https://assets.ngc.nvidia.com/products/api-catalog/vista3d/example-1.nii.gz",
    "prompts": {
        "classes": ["liver", "spleen"]
    }
  }'
```




## Cleanup

Purge your Sagemaker resources (if desired) between runs:
```bash
# Cleanup Sagemaker
sg_delete_resources() {
    local endpoint_name=$1
    # Delete endpoint
    aws sagemaker delete-endpoint --endpoint-name $endpoint_name || true
    # Wait for the endpoint to be deleted
    aws sagemaker wait endpoint-deleted --endpoint-name $endpoint_name || true
    # Delete endpoint config
    aws sagemaker delete-endpoint-config --endpoint-config-name $endpoint_name || true
    # Delete model
    aws sagemaker delete-model --model-name $endpoint_name || true
}

# Delete existing resources
sg_delete_resources $SG_EP_NAME
```
