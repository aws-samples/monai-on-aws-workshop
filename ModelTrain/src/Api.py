import array
import json
import logging
import importlib  
import boto3
import io
import sys
import time
import os
import gzip
from openjpeg import decode

logging.basicConfig( level="INFO" )

class MedicalImaging: 
    def __init__(self, endpoint=""):
        session = boto3.Session()
        if len(endpoint)>1:
            self.client = boto3.client('medical-imaging', endpoint_url=endpoint)
        else:
            self.client = boto3.client('medical-imaging')
    
    def stopwatch(self, start_time, end_time):
        time_lapsed = end_time - start_time
        return time_lapsed*1000 
    
    
    def getMetadata(self, datastoreId, imageSetId):
        start_time = time.time()
        dicom_study_metadata = self.client.get_image_set_metadata(datastoreId=datastoreId , imageSetId=imageSetId )
        json_study_metadata = json.loads( gzip.decompress(dicom_study_metadata["imageSetMetadataBlob"].read()) )
        end_time = time.time()
        logging.debug(f"Metadata fetch  : {self.stopwatch(start_time,end_time)} ms")   
        return json_study_metadata

    
    def listDatastores(self):
        start_time = time.time()
        response = self.client.list_datastores()
        end_time = time.time()
        logging.debug(f"List Datastores  : {self.stopwatch(start_time,end_time)} ms")        
        return response
    
    
    def createDatastore(self, datastoreName):
        start_time = time.time()
        response = self.client.create_datastore(datastoreName=datastoreName)
        end_time = time.time()
        logging.debug(f"Create Datastore  : {self.stopwatch(start_time,end_time)} ms")        
        return response
    
    
    def getDatastore(self, datastoreId):
        start_time = time.time()
        response = self.client.get_datastore(datastoreId=datastoreId)
        end_time = time.time()
        logging.debug(f"Get Datastore  : {self.stopwatch(start_time,end_time)} ms")        
        return response
    
    
    def deleteDatastore(self, datastoreId):
        start_time = time.time()
        response = self.client.delete_datastore(datastoreId=datastoreId)
        end_time = time.time()
        logging.debug(f"Delete Datastore  : {self.stopwatch(start_time,end_time)} ms")        
        return response
    
    
    def startImportJob(self, datastoreId, IamRoleArn, inputS3, outputS3):
        start_time = time.time()
        response = self.client.start_dicom_import_job(
            datastoreId=datastoreId,
            dataAccessRoleArn = IamRoleArn,
            inputS3Uri = inputS3,
            outputS3Uri = outputS3,
            clientToken = "demoClient"
        )
        end_time = time.time()
        logging.debug(f"Start Import Job  : {self.stopwatch(start_time,end_time)} ms")        
        return response
    
    
    def getImportJob(self, datastoreId, jobId):
        start_time = time.time()
        response = self.client.get_dicom_import_job(datastoreId=datastoreId, jobId=jobId)
        end_time = time.time()
        logging.debug(f"Get Import Job  : {self.stopwatch(start_time,end_time)} ms")        
        return response
    

    def listImportJobs(self, datastoreId, jobStatus='COMPLETED'):
        start_time = time.time()
        response = self.client.list_dicom_import_jobs(
            datastoreId=datastoreId,
            jobStatus = jobStatus
        )
        end_time = time.time()
        logging.debug(f"List Import Jobs : {self.stopwatch(start_time,end_time)} ms")        
        return response
    
    
    def getFramePixels(self, datastoreId, imageSetId, imageFrameId):
        start_time = time.time()
        res = self.client.get_image_frame(
            datastoreId=datastoreId,
            imageSetId=imageSetId,
            imageFrameInformation={
                'imageFrameId': imageFrameId
            })
        end_time = time.time()
        logging.debug(f"Frame fetch     : {self.stopwatch(start_time,end_time)} ms") 
        start_time = time.time() 
        b = io.BytesIO()
        b.write(res['imageFrameBlob'].read())
        b.seek(0)
        d = decode(b)
        end_time = time.time()
        logging.debug(f"Frame decode    : {self.stopwatch(start_time,end_time)} ms")    
        return d 
