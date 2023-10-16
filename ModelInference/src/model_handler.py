"""
ModelHandler defines an example model handler for MONAI Deploy
"""
import glob
import json
import logging
import os
import re
import torch
from collections import namedtuple
from importlib import import_module
import numpy as np
import boto3
logging.info(f"######## boto3 version {boto3.__version__}")

from app import AISpleenSegApp
from AHItoDICOMInterface.AHItoDICOM import AHItoDICOM

account_id = boto3.client("sts").get_caller_identity()["Account"]
region = boto3.Session().region_name

class ModelHandler(object):
    """
    A sample Model handler implementation.
    """

    def __init__(self):
        self.initialized = False
        self.shapes = None
    
    def initialize(self, context):
        """
        Initialize model. This will be called during model loading time
        :param context: Initial context contains model server system properties.
        :return:
        """
        self.initialized = True
        properties = context.system_properties
        logging.debug("properties: {}".format(properties))
        model_dir = properties.get("model_dir")
        os.environ["model_dir"] = model_dir
        logging.debug("files in model_dir: {}".format(os.listdir(model_dir)))
        
        gpu_id = properties.get("gpu_id")
        # device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # model = torch.jit.load(model_dir+'/model.ts', map_location=device)

        helper = AHItoDICOM()
        self.monai_app_instance = AISpleenSegApp(helper, do_run=False, path="/home/model-server/")
        logging.debug(f"MONAI App Info: {self.monai_app_instance.get_package_info()}")
        self.s3_client = boto3.client("s3")

    def preprocess(self, request):
        """
        Transform raw input into model input data.
        :param request: list of raw requests
        :return: list of preprocessed model input data
        """
        # Take the input data and pre-process it make it inference ready
        inputStr = request[0].get("body").decode('UTF8')
        datastoreId = json.loads(inputStr)['inputs'][0]['datastoreId']
        imageSetId = json.loads(inputStr)['inputs'][0]['imageSetId']
        
        with open('/home/model-server/inputImageSets.json', 'w') as f:
            f.write(json.dumps({
                "datastoreId": datastoreId, 
                "imageSetId": imageSetId
            }))
        
        return '/home/model-server/inputImageSets.json'

    def inference(self, model_input, targetmodel):
        """
        Internal inference methods
        :param model_input: transformed model input data list
        :return: list of inference output in NDArray
        """
        logging.debug("input file: {}".format(model_input))
        logging.debug("input file: {}".format(targetmodel.split('.')[0]))

        self.monai_app_instance.run(
            input=model_input,
            output="/home/model-server/output/",
            workdir="/home/model-server/",
            model=f"{os.environ['model_dir']}/{targetmodel.split('.')[0]}.ts"
        )

        logging.info("#### MONAI App complete")
        logging.info("#### output files: {}".format(os.listdir("/home/model-server/output/")))
        
        
        for root,dirs,files in os.walk("/home/model-server/output/"):
            logging.info(files)
            for file in files:
                self.s3_client.upload_file(os.path.join(root,file), f"sagemaker-{region}-{account_id}", 'monaideploy/'+file)

        return [{f"s://sagemaker-{region}-{account_id}/monaideploy/{file}": "outputs3file"}]

    def handle(self, data, context):
        """
        Call preprocess, inference and post-process functions
        :param data: input data
        :param context: mms context
        """
        request_header = context.get_all_request_header(0) ## {'body': {'content-type': 'application/json'}, 'Accept': 'application/json', 'User-Agent': 'AHC/2.0', 'Host': '169.254.180.2:8080', 'Content-Length': '115', 'X-Amzn-SageMaker-Target-Model': 'model.tar.gz', 'Content-Type': 'application/json'}
        model_input = self.preprocess(data)
        model_out = self.inference(model_input, request_header['X-Amzn-SageMaker-Target-Model'])
        return model_out

_service = ModelHandler()


def handle(data, context):
    if not _service.initialized:
        _service.initialize(context)

    if data is None:
        return None

    return _service.handle(data, context)
