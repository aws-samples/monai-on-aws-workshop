import glob
import json
import logging
import os
import torch
from importlib import import_module
import boto3

from app import AISpleenSegApp

from AHItoDICOMInterface.AHItoDICOM import AHItoDICOM
helper = AHItoDICOM()

JSON_CONTENT_TYPE = 'application/json'

account_id = boto3.client("sts").get_caller_identity()["Account"]
region = boto3.Session().region_name

def model_fn(model_dir, context):
    logging.info("##### context system properties: {}".format(context.system_properties))
    logging.info("##### model files: {}".format(os.listdir( model_dir )))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = torch.jit.load(model_dir+'/model.ts', map_location=device)
    
    monai_app_instance = AISpleenSegApp(helper, do_run=False, path="/home/model-server")
    logging.info(f"#### MONAI App Info: {monai_app_instance.get_package_info()}")

    return monai_app_instance


def input_fn(serialized_input_data, content_type=JSON_CONTENT_TYPE):
    if content_type == JSON_CONTENT_TYPE:
        input_data = json.loads(serialized_input_data)
        logging.info("#### input_data: {}".format(input_data))
        return input_data

    else:
        raise Exception('Requested unsupported ContentType in Accept: ' + content_type)
        return


def predict_fn(input_data, model):
    
    with open('/home/model-server/inputImageSets.json', 'w') as f:
        f.write(json.dumps(input_data))
        
    output_folder = "/home/model-server/output"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    model.run(
        input='/home/model-server/inputImageSets.json',
        output=output_folder,
        workdir='/home/model-server',
        model='/opt/ml/model/model.ts'
    )

    logging.info("MONAI App complete")
    logging.info("###### output files: {}".format(os.listdir(output_folder)))
    return 


def output_fn(prediction_output, accept=JSON_CONTENT_TYPE):
    s3_client = boto3.client("s3")
    for root,dirs,files in os.walk("/home/model-server/output/"):
        for file in files:
            s3_client.upload_file(os.path.join(root,file), f'sagemaker-{region}-{account_id}', 'monaideploy/'+file)
    
    if accept == JSON_CONTENT_TYPE:
        return json.dumps({f"s://sagemaker-{region}-{account_id}/monaideploy/{}".format(file): "1"}), accept

    raise Exception('Requested unsupported ContentType in Accept: ' + accept)