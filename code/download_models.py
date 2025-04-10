import os
import sys
import shutil
import zipfile
from azure.storage.blob import BlobServiceClient


# connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
connect_str = sys.argv[1]
blob_service_client = BlobServiceClient.from_connection_string(connect_str)


def download_the_model(target_dir, file_name):
    target_dir = os.path.abspath(target_dir)
    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)

    blob_client = blob_service_client.get_blob_client(container="models", blob=file_name + ".zip")
    download_file_path = os.path.join(target_dir, file_name + ".zip")

    print("Path is: ", download_file_path)
    if os.path.isfile(download_file_path):
        print("Removing old file")
        os.remove(download_file_path)
    print("Downloading model from Azure Blob Storage..")
    with open(download_file_path, "wb") as download_file:
        download_file.write(blob_client.download_blob().readall())

    if os.path.isdir(os.path.join(target_dir, file_name)):
        print("Deleting old model folder")
        shutil.rmtree(os.path.join(target_dir, file_name))

    print("Extracting model file...")
    with zipfile.ZipFile(download_file_path, 'r') as zip_ref:
        zip_ref.extractall(os.path.join(target_dir, file_name))


models = ["ner_model_Nov15", "bank_dets_model_v3", "ner_model_credit_note_12_Mar_25", "ner_model_tapal_27Dec23",
          "ner_model_contract_num_11_Mar_25", "classifcation_model_6May_2024", "ner_model_account_num_19Sept"]

for model in models:
    download_the_model("models", model)

