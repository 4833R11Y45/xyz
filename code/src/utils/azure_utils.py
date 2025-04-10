import os
import uuid
from azure.storage.blob import BlobServiceClient
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from collections import defaultdict
import json

log_folder = "logs"
log_filename = os.path.join(log_folder, "sc_app.log")
# log_writer = open(log_filename, 'a', encoding='utf-8')
# sys.stdout = log_writer

connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
blob_service_client = BlobServiceClient.from_connection_string(connect_str)

CONTAINER_MAPPING = defaultdict(lambda:'outputfiles')
CONTAINER_MAPPING['translated_invoice'] = 'raw-uploads-test'
CONTAINER_MAPPING['compressed_output'] = 'compressedoutput'


BLOB_FILENAME_MAPPING = defaultdict(lambda:'.JSON')
BLOB_FILENAME_MAPPING['translated_invoice'] = '-translated.pdf'
BLOB_FILENAME_MAPPING['compressed_output'] = '.pdf'


def valid_model(model_path, file_name):
    if not os.path.isfile(os.path.join(model_path, "meta.json")):
        model_path = os.path.join(model_path, file_name)
        if not os.path.isfile(os.path.join(model_path, "meta.json")):
            return False
    return True


def download_blob_file(blob_url, target_dir):
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)

    parts = blob_url.split('/')
    container_name = parts[-3]
    directory_name = parts[-2]
    blob_name = parts[-1]
    if directory_name:
        blob_name = f"{directory_name}/{blob_name}"

    # Generate unique filename by adding UUID
    original_filename = os.path.basename(blob_url)
    file_base, file_ext = os.path.splitext(original_filename)
    unique_filename = f"{file_base}_{str(uuid.uuid4())}{file_ext}"
    download_file_path = os.path.join(target_dir, unique_filename)

    print("\nDownloading file to \n\t" + download_file_path)
    print("Downloading file from Azure Storage")
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    blob_data = blob_client.download_blob()
    content = blob_data.readall()

    with open(download_file_path, "wb") as download_file:
        download_file.write(content)

    return download_file_path


def upload_blob(file_path, logger, container_name="logs"):
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_path)
    logger.info("\nUploading to Azure Storage as blob:\n\t" + file_path)

    # Upload the created file
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)


def upload_file_on_azure(content, file_id, correlation_id, file_type):
    container_name = CONTAINER_MAPPING[file_type]
    subfolder_name = correlation_id
    blob_name = f'{subfolder_name}/{file_id}{BLOB_FILENAME_MAPPING[file_type]}'
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

    try:
        if file_type == "translated_invoice" or file_type == 'compressed_output':
            with open(content, 'rb') as data:
                blob_client.upload_blob(data, overwrite=True)
        else:
            blob_client.upload_blob(content, overwrite=True)

        blob_url = blob_client.url
        file_path = f'https://{blob_client.account_name}.blob.core.windows.net/{blob_client.container_name}/{blob_client.blob_name}'
        print(file_path)
    except Exception as e:
        return f"Error uploading {file_type} to Azure Blob Storage: {str(e)}", None

    return blob_url, file_path

def get_google_credentials():
    keyVaultName = "SpendConsole-kv"
    KVUri = f"https://{keyVaultName}.vault.azure.net"
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=KVUri, credential=credential)
    secretName = "aicredentials"
    retrieved_secret_value = client.get_secret(secretName).value
    google_credentials = json.loads(retrieved_secret_value)
    return google_credentials


def get_invoice_json_from_azure_storage(invoice_id):
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = "invoicejson-test"

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)
    blob_name = f"{invoice_id}"

    blob_client = container_client.get_blob_client(blob_name)
    blob_content = blob_client.download_blob().readall()
    json_response = json.loads(blob_content.decode("utf-8"))
    invoice_num = None
    ocr_text = ""
    # Checking invoice ID from both structures, then raising error if not found in both
    try:
        invoice_num = json_response[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceId"]["content"]
        ocr_text = str(json_response[0]["analyzeResult"]['content'])
    except KeyError:
        try:
            invoice_num = json_response[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceId"]["text"]
            for page in json_response[0]["analyzeResult"]["readResults"]:
                for line in page["lines"]:
                    ocr_text += line["text"] + "\n"
        except KeyError:
            print(f"Error: 'InvoiceId' not found in the expected JSON structure for invoice_id: {invoice_id}")

    return invoice_num, ocr_text
