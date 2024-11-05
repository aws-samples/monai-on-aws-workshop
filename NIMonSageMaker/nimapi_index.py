import gzip
import json
import logging
import mimetypes
import os
import subprocess
import tempfile
import time
import uuid
from typing import Optional
from io import BytesIO

import numpy as np
import requests
import tritonclient.grpc as grpcclient
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from monai.transforms import LoadImage
from nvcf_helper_functions import helpers
from tritonclient.utils import np_to_triton_dtype
import SimpleITK as sitk
from nvidia import nvimgcodec
from pydicom import dcmread
import cupy as cp
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from aws_requests_auth.aws_auth import AWSRequestsAuth

from .schemas import BadInputError, InferenceRequest, ModelInfo
from .utils import get_filename_from_cd, is_url, remove_file


parent_dir = os.path.dirname(os.path.abspath(__file__))
triton_dir = os.path.join(os.path.dirname(parent_dir), "triton")
bundle_root = os.path.join(triton_dir, "vista3d", "1")
s3 = boto3.client('s3')
my_config = Config(region_name = os.getenv('AWS_REGION', 'us-east-1'))
ahi = boto3.client('medical-imaging', config=my_config)
decoder = nvimgcodec.Decoder()

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


async def input_exception_handler(request: Request, exc: BadInputError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder({"error_msg": [{"msg": exc.message}]}),
    )


async def servicedown_exception_handler(request: Request, exc: ConnectionRefusedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=jsonable_encoder({"error_msg": [{"msg": "Triton server for 'vista3d' is down."}]}),
    )


app = FastAPI(
    title="VISTA-3D NVIDIA MicroService APIs",
    description="VISTA-3D is a specialized interactive foundation model for segmenting and annotating human anatomies.",
    contact={
        "name": "NVIDIA Support",
        "url": "https://help.nvidia.com/",
    },
    version="1.0.0",
    termsOfService="https://nvidia.com/legal/terms-of-use",
    docs_url="/",
    redoc_url="/docs",
    swagger_ui_parameters={"syntaxHighlight": True, "defaultModelsExpandDepth": 0},
)
app.add_exception_handler(BadInputError, input_exception_handler)
app.add_exception_handler(ConnectionRefusedError, servicedown_exception_handler)


@app.get(
    path="/health/ready",
    operation_id="healthready",
    tags=["Health"],
    summary="Check if service is ready",
    description="Check if service is ready and model is ready for inference",
)
async def health_ready() -> bool:
    client = grpcclient.InferenceServerClient(url="localhost:8001", verbose=True)
    return client.is_server_ready() and client.is_model_ready("vista3d")


@app.get(
    path="/health/live",
    operation_id="healthlive",
    tags=["Health"],
    summary="Check if service is live",
    description="Check if service is up and running",
)
async def health_live() -> bool:
    client = grpcclient.InferenceServerClient(url="localhost:8001", verbose=True)
    return client.is_server_live()


@app.get(
    path="/vista3d/info",
    operation_id="info",
    tags=["Models"],
    summary="Model Information",
    description="Fetch detailed information about the model such as version, labels etc...",
)
async def info() -> ModelInfo:
    with open(os.path.join(bundle_root, "configs", "metadata.json")) as fp:
        metadata = json.load(fp)

    return ModelInfo(
        name=metadata.get("name"),
        description=metadata.get("description"),
        version=metadata.get("version"),
        labels=metadata.get("network_data_format", {}).get("outputs", {}).get("pred", {}).get("channel_def"),
    )


@app.post(
    path="/vista3d/inference",
    operation_id="inference",
    tags=["Models"],
    summary="Run Inference",
    description="Run Inference function of a model for segmenting and annotating human anatomies",
    responses={
        200: {
            "description": "OK",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
    },
)


class FileDownloader:
    def __init__(self, url: str, protocol: str):
        self.url = url
        self.protocol = protocol

    def download_from_http(self, destination_path: str) -> Optional[str]:
        """
        Download a file from an HTTP/HTTPS URL.

        Args:
            destination_path (str): The path where the downloaded file should be saved.

        Returns:
            str: The path to the downloaded file, or None if the download failed.
        """
        try:
            response = requests.get(self.url, stream=True)
            response.raise_for_status()

            file_path = os.path.join(destination_path, os.path.basename(self.url))
            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            return file_path
        except requests.exceptions.RequestException as e:
            logging.error(f"Error downloading from HTTP/HTTPS: {e}")
            return None

    def download_from_s3(self, destination_path: str) -> Optional[str]:
        """
        Download a file from an S3 bucket.

        Args:
            destination_path (str): The path where the downloaded file should be saved.

        Returns:
            str: The path to the downloaded file, or None if the download failed.
        """
        try:
            bucket_name, key = self.url.replace('s3://', '').split('/', 1)
            file_path = os.path.join(destination_path, os.path.basename(key))

            s3.download_file(Bucket=bucket_name, Key=key, Filename=file_path)
            return file_path
        except ClientError as e:
            logging.error(f"Error downloading from S3: {e}")
            return

    def download_from_ahi(self, destination_path: str) -> Optional[str]:
        """
        Download a file from Amazon Health Imaging.

        Args:
            destination_path (str): The path where the downloaded file should be saved.

        Returns:
            str: The path to the downloaded file, or None if the download failed.
        """
        try:
            # Implement the logic to download from Amazon Health Imaging
            # using the self.ahi_client and self.url
            pass
        except Exception as e:
            logging.error(f"Error downloading from Amazon Health Imaging: {e}")
            return None

    def download_file(self, destination_path: str) -> Optional[str]:
        """
        Download a file based on the provided protocol and URL.

        Args:
            destination_path (str): The path where the downloaded file should be saved.

        Returns:
            str: The path to the downloaded file, or None if the download failed.
        """
        if self.protocol == 'http' or self.protocol == 'https':
            return self.download_from_http(destination_path)
        elif self.protocol == 's3':
            return self.download_from_s3(destination_path)
        elif self.protocol == 'healthimaging':
            return self.download_from_ahi(destination_path)
        else:
            logging.error(f"Unsupported protocol: {self.protocol}")
            return None


async def parse_url(url: str) -> tuple[str, str]:
    """
    Parse a URL string and return a tuple containing the URL and the matched protocol.

    Args:
        url (str): The URL string to parse.

    Returns:
        tuple[str, str]: A tuple containing the URL and the matched protocol.
                         If no protocol is matched, the second element is an empty string.

    Raises:
        ValueError: If the URL string is empty or does not contain a colon.
    """
    if not is_url(url):
        logging.error(ValueError("URL string cannot be empty."))

    try:
        protocol, _ = url.split(":", 1)
    except ValueError:
        logging.error(ValueError("Invalid URL format. URL must contain a colon."))

    protocol = protocol.lower()
    matched_protocol = ""

    if protocol in ["s3", "healthimaging", "http", "https"]:
        matched_protocol = protocol
    
    if not matched_protocol:
        logging.error(ValueError(f"Unsupported protocol in URL {protocol}."))

    return url, matched_protocol


async def inference(request: InferenceRequest, background_tasks: BackgroundTasks, http_request: Request):
    success = False
    headers = http_request.headers
    start_ts = time.time()
    image_fetch_ts = 0.0
    image_file = None
    output = None

    try:
        image_url = request.image
        root_dir = os.environ.get("NIMS_WORKING_DIR", tempfile.gettempdir())
        working_dir = os.path.join(root_dir, tempfile.NamedTemporaryFile().name)
        os.makedirs(working_dir, exist_ok=True)
        
        logging.info(f"Downloading Remote URI => {image_file}")

        url, protocol = await parse_url(image_url)
        downloader = FileDownloader(url, protocol)
        donwnloader.download_file(working_dir)


        

        if is_url(image_url) and image_url.startswith("http"):
            if image_url.startswith("https://dicom-medical-imaging.us-east-1.amazonaws.com"):
                headers = {
                    'Accept': 'application/dicom; transfer-syntax=1.2.840.10008.1.2.1',
                }
                r = requests.get(
                    image_url,
                    headers=headers,
                    auth=AWSRequestsAuth(
                        aws_access_key=os.getenv('AWS_ACCESS_KEY_ID', ''), 
                        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', ''), 
                        aws_host='dicom-medical-imaging.us-east-1.amazonaws.com', 
                        aws_region=os.getenv('AWS_REGION', 'us-east-1'), 
                        aws_service='medical-imaging'
                    ),
                )
                dataset = dcmread(BytesIO(r.content))
                img = sitk.GetImageFromArray([dataset.pixel_array])
                image_file = os.path.join(working_dir, 'example-1.nii.gz')
                background_tasks.add_task(remove_file, working_dir)
                if not image_file:
                    output = {"error": "Can't determine filename to download from URI/Content Disposition"}
                    raise HTTPException(status_code=422, detail=output["error"])
                sitk.WriteImage(img, image_file)
            else:
                r = requests.get(image_url, allow_redirects=True)
                image_file = os.path.join(working_dir, get_filename_from_cd(image_url, r.headers.get("content-disposition")))
                background_tasks.add_task(remove_file, working_dir)
                if not image_file:
                    output = {"error": "Can't determine filename to download from URI/Content Disposition"}
                    raise HTTPException(status_code=422, detail=output["error"])
                with open(image_file, "wb") as fp:
                    fp.write(r.content)
        elif image_url.startswith("s3"):
            path_parts=image_url.replace("s3://","").split("/")
            bucket=path_parts.pop(0)
            key="/".join(path_parts)
            print(f"download s3 object from bucket: {bucket} and key: {key}")
            image_file = os.path.join(working_dir, path_parts[-1])
            background_tasks.add_task(remove_file, working_dir)
            if not image_file:
                output = {"error": "Can't determine filename to download from URI/Content Disposition"}
                raise HTTPException(status_code=422, detail=output["error"])
            with open(image_file, 'wb') as fp:
                s3.download_fileobj(bucket, key, fp)
        elif image_url.startswith("healthimaging://"):
            path_parts=image_url.replace("healthimaging://","").split("/")
            datastoreId=path_parts[0]
            imageSetId=path_parts[1]
            response = ahi.get_image_set_metadata(
                datastoreId=datastoreId,
                imageSetId=imageSetId
            )
            with open('/opt/nvidia/vista3d/imagesetmetadata.json', 'wb') as fp:
                fp.write( gzip.decompress(response["imageSetMetadataBlob"].read()) )
            subprocess.run([
                "/root/aws-healthimaging-samples/ahi-batch-image-frame-retrieve/build/apps/ahi-retrieve", 
                "-i", "/opt/nvidia/vista3d/imagesetmetadata.json", 
                "-r", os.getenv('AWS_REGION', 'us-east-1'), 
                "-a", os.getenv('AWS_ACCESS_KEY_ID', ''), 
                "-s", os.getenv('AWS_SECRET_ACCESS_KEY', ''), 
                "-f", "jph"
            ])
            image_path=f"/opt/nvidia/vista3d/{datastoreId}/{imageSetId}/"
            file_list = []
            for p in os.listdir(image_path):
                file_list.append(os.path.join(image_path, p))
            inputImages = decoder.read(file_list)
            cp_imgs = []
            for i in inputImages:
                frame = cp.asnumpy(cp.asarray(i))
                cp_imgs.append( frame[:,:,-1] )
            result_image=sitk.GetImageFromArray(cp_imgs)
            image_file = os.path.join(working_dir, 'example-1.nii.gz')
            background_tasks.add_task(remove_file, working_dir)
            if not image_file:
                output = {"error": "Can't determine filename to download from URI/Content Disposition"}
                raise HTTPException(status_code=422, detail=output["error"])
            sitk.WriteImage(result_image, image_file)
        else:
            output = {"error": "Invalid Image URL"}
            raise HTTPException(status_code=422, detail=output["error"])
        
        request.image = image_file
        image_fetch_ts = round(time.time() - start_ts, 2)
        print(f"Fetched Image from: {image_url}; Time Lapsed: {image_fetch_ts}")

        client = grpcclient.InferenceServerClient(url="localhost:8001", verbose=True)
        inputs = [grpcclient.InferInput("INPUT_REQUEST", [1], np_to_triton_dtype(np.object_))]
        outputs = [grpcclient.InferRequestedOutput("OUTPUT_RESPONSE")]

        input_request = request.model_dump_json()
        inputs[0].set_data_from_numpy(np.array([input_request], dtype=np.object_))

        response = client.infer("vista3d", inputs, request_id=str(uuid.uuid4().hex), outputs=outputs)
        output = json.loads(response.as_numpy("OUTPUT_RESPONSE")[0].decode())

        pred_file = output.get("pred", None) if output else None
        if pred_file and os.path.isfile(pred_file):
            print(f"Sending Output Mask: {pred_file}")

            media_types = mimetypes.guess_type(pred_file, strict=False)
            media_type = "application/octet-stream" if media_types is None or media_types[0] is None else media_types[0]

            success = True
            return FileResponse(pred_file, media_type=media_type, filename=os.path.basename(pred_file))

        raise HTTPException(
            status_code=500,
            detail=f"Failed to Run Inference.  Error: {output.get('error') if output else 'Unknown Error'}",
        )
    finally:
        properties = {
            "click_prompts": len(request.prompts.points) if request.prompts and request.prompts.points else 0,
            "class_prompts": len(request.prompts.classes) if request.prompts and request.prompts.classes else 0,
            "model": "vista3d",
            "start_time": start_ts,
            "end_time": time.time(),
            "image_fetch_time": image_fetch_ts,
            "total_latency": round(time.time() - start_ts, 2),
        }

        if not success:
            if image_file:
                try:
                    properties["image_size"] = list(LoadImage()(image_file).shape)
                except:
                    pass
            if output:
                properties["error"] = output.get("error")

        helpers.LOGGER.info(
            helpers.build_log_message(
                request_parameters={k: v for k, v in headers.items() if k and k.lower().startswith("nvcf")},
                inference_type="medical",
                properties=properties,
                event_type="AIPlayground_Inference",
                success=success,
            ),
        )
