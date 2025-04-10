import pytest
import os
from unittest.mock import patch, AsyncMock
from azure.servicebus import ServiceBusClient
from app import process_single_file, process_and_upload_file, send_message_to_queue, process_messages, listen_for_messages
import datetime


SERVICE_BUS_CONNECTION_STRING = os.getenv("AZURE_SERVICEBUS_CONNECTION_STRING")
@pytest.mark.asyncio
async def test_process_single_file():
    with patch("app.azure_utils.download_blob_file", AsyncMock(return_value="mocked_file.pdf")):
        with patch("app.process_invoice", return_value={"mocked_response": "success"}):
            with patch("app.azure_utils.upload_response", return_value=("/mocked/response/path", "/mocked/result/path")):
                file_data = {
                    "fileId": "mocked_file_id",
                    "filePath": "mocked_file_path",
                    "fileType": "mocked_file_type",
                }
                start = datetime.datetime.now()
                process_always = True
                correlation_id = "mocked_correlation_id"
                response = await process_single_file(file_data, start, process_always, correlation_id)

                print("Response:", response)

                assert response["fileId"] == "mocked_file_id"
                assert response["fileType"] == "mocked_file_type"


@pytest.mark.asyncio
async def test_process_and_upload_file():
    with patch("app.process_single_file", AsyncMock(return_value={"mocked_response": "success"})):
        with patch("app.send_message_to_queue", AsyncMock()):
            message = '{"correlationId": "123", "processAllPages": true, "tenantId": "456", "sourceType": "source", "supplierCustomerId": "789", "files": [{"fileId": "file123", "filePath": "/path/to/file", "fileType": "pdf"}], "queueName": "queue"}'
            await process_and_upload_file(message)

@pytest.mark.asyncio
async def test_send_message_to_queue():

    with patch("app.ServiceBusClient") as mock_service_bus_client:
        mock_sender = AsyncMock()
        mock_service_bus_client.from_connection_string.return_value.get_queue_sender.return_value = mock_sender

        #Testing send message to queue function
        await send_message_to_queue("mock_correlation_id", "mock_tenant_id", "mock_source_type",
                                    "mock_supplier_customer_id", [{}], "mock_queue_name_send")

        #send_messages method is awaited at least once
        mock_sender.send_messages.assert_awaited_once()


        #Assertion for correct connection string
        mock_service_bus_client.from_connection_string.assert_called_once_with(conn_str=SERVICE_BUS_CONNECTION_STRING)

@pytest.mark.asyncio
async def test_process_messages():
    mock_client = AsyncMock(spec=ServiceBusClient)

    with patch("app.ServiceBusClient.from_connection_string") as mock_from_connection_string:
        mock_from_connection_string.return_value.__aenter__.return_value = mock_client

        # Creating  AsyncMock for the receive_messages method
        receive_messages_mock = AsyncMock()
        mock_client.get_queue_receiver.return_value.receive_messages = receive_messages_mock
        await process_messages()

        #Assertion for correct connection string
        mock_from_connection_string.assert_called_once_with(conn_str=SERVICE_BUS_CONNECTION_STRING, logging_enable=True)

        receive_messages_mock.assert_awaited_once()



