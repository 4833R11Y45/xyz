import os
import json
import asyncio
from datetime import date
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.storage.blob import BlobServiceClient

connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
blob_service_client = BlobServiceClient.from_connection_string(connect_str)
SERVICE_BUS_NAME = "invoice-parsing-dev"
SERVICE_BUS_CONNECTION_STRING = os.getenv("AZURE_SERVICEBUS_CONNECTION_STRING")
TODAY = date.today()


def upload_file_on_azure(input_filepath, file_id, correlation_id):
    container_name = "inputfiles"
    subfolder_name = correlation_id
    blob_name = f'{subfolder_name}/{file_id}'

    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

    try:
        with open(input_filepath, 'rb') as data:
            blob_client.upload_blob(data, overwrite=True)

        blob_file_path = f'https://{blob_client.account_name}.blob.core.windows.net/{blob_client.container_name}/{blob_client.blob_name}'
        print("File uploaded to : ", blob_file_path)
        return blob_file_path

    except Exception as e:
        print(f"Error uploading {input_filepath} to Azure Blob Storage: {str(e)}")
        raise


async def send_message_to_service_bus(input_file_path, SERVICE_BUS_NAME):
    file_id = os.path.basename(input_file_path)
    correlation_id = TODAY.strftime("%b-%d-%Y")

    try:
        blob_file_path = upload_file_on_azure(input_file_path, file_id, correlation_id)

        message_content = {
            "files": [{
                "fileId": file_id,
                "filePath": blob_file_path,
                "fileType": "pdf",
                "originalFileName": "test.pdf"
            }],
            "processAllPages": True,
            "correlationId": correlation_id,
            "tenantId": "ABCD",
            "sourceType": "upload",
            "supplierCustomerId": "test",
            "queueName": "invoice-parsing-result-uridah",
            "version": "v2.1",
            "runClassification": False,
            "translate": False
        }

        message_body = json.dumps(message_content)
        message = ServiceBusMessage(message_body)

        async with ServiceBusClient.from_connection_string(
                conn_str=SERVICE_BUS_CONNECTION_STRING
        ) as service_bus_client:
            async with service_bus_client.get_queue_sender(
                    queue_name=SERVICE_BUS_NAME
            ) as sender:
                await sender.send_messages(message)
                print(f"Sent input message to queue {SERVICE_BUS_NAME}")

    except Exception as e:
        print(f"Error sending response message: {str(e)}")
        raise


async def main():
    await send_message_to_service_bus(
        "C:\\Users\\urida\\Downloads\\Invoice (18).pdf",
        SERVICE_BUS_NAME
    )


if __name__ == "__main__":
    asyncio.run(main())