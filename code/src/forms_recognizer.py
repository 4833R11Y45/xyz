import os
import json
import polling2
import requests
import traceback
import backoff
from azure.core.exceptions import ResourceNotFoundError

from src.utils import helper, azure_utils


OCP_APIM_SUBSCRIPTION_KEY = os.getenv("OCP_APIM_SUBSCRIPTION_KEY")

def test(response):
    response = json.loads(response.content)
    if 'status' in response:
        return response['status'] == 'succeeded'
    return False


def build_api_endpoint(version):
    if version == 'v2.1':
        return 'https://invoiceaiformrecogniser.cognitiveservices.azure.com/formrecognizer/v2.1/prebuilt/invoice/analyze?includeTextDetails=true'
    elif version == 'v3.1':
        return 'https://invoiceaiformrecogniser.cognitiveservices.azure.com/formrecognizer/documentModels/prebuilt-invoice:analyze?api-version=2023-07-31'
    else:
        raise ValueError(f"Unsupported version: {version}")


def get_form_recognizer_response(blob_url):
    try:
        response_path = azure_utils.download_blob_file(blob_url, "./")
        print("File found on azure")
    except ResourceNotFoundError:
        print("File NOT found on azure")
        response_path = None
    return response_path



@backoff.on_exception(backoff.expo, Exception, max_time=30)
def get_response(pdf, type, logger, version):
    pdf_md5 = helper.check_md5sum(pdf)
    if version == "v2.1":
        container_name = "formrecognizer-responses-v2"
    elif version == "v3.1":
        container_name = "formrecognizer-responses-v3"
    blob_url = f"{container_name}//{pdf_md5}.json"
    response_path = get_form_recognizer_response(blob_url)
    if response_path is None:
        if type == "pdf":
            content_type = "application/pdf"
        elif type in ["png", "jpg", "jpeg"]:
            content_type = f"image/{type}"
        elif type == "bmp":
            content_type = "image/bmp"
        elif type in ["tiff", "tif"]:
            content_type = "image/tiff"
        else:
            raise ValueError(f"Unsupported file type: {type}")

        api_endpoint = build_api_endpoint(version)
        print(f"API Endpoint: {api_endpoint}")
        with open(pdf, "rb") as file:
            response = requests.post(
                api_endpoint,
                headers={'Content-Type': content_type,
                         'Ocp-Apim-Subscription-Key': OCP_APIM_SUBSCRIPTION_KEY},
                data=file
            )

        print(response.headers)
        get_url = response.headers['Operation-Location']

        try:
            new_response = polling2.poll(lambda: requests.get(get_url,
                                                              headers={'Content-Type': content_type,
                                                                       'Ocp-Apim-Subscription-Key':
                                                                           OCP_APIM_SUBSCRIPTION_KEY}),
                                         step=1, timeout=200, check_success=test)
        except polling2.TimeoutException as e:
            print(traceback.format_exc())
            logger.error(traceback.format_exc())
            raise e
        except Exception as e:
            print(f"An error occurred: {e}")
            logger.error(f"An error occurred: {e}")

        azure_response = json.loads(new_response.content)
        with open(f"{pdf_md5}.json", "w") as f:
            json.dump(azure_response, f)
        azure_utils.upload_blob(f"{pdf_md5}.json", logger, container_name)
        if os.path.isfile(f"{pdf_md5}.json"):
            os.remove(f"{pdf_md5}.json")
    else:
        with open(response_path, "r") as f:
            azure_response = json.load(f)
        os.remove(response_path)
    return azure_response
