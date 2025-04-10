import asyncio
import os
import mimetypes
import sys
import json
import backoff
import traceback
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from src.utils import azure_utils, pdf_utils, arabic_util
from src import raw_text_utils
import tempfile
from processor import process_invoice
from exception_processor import process_exceptions
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
from PIL import Image
import subprocess
import pyodbc
import time
from src.utils.translation import translate_document
from werkzeug.utils import secure_filename
from src.utils.azure_utils import upload_blob
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import shutil

class LogFileHandler(FileSystemEventHandler):
    def __init__(self, logger):
        self.logger = logger
        self.last_upload_time = {}
        self.upload_cooldown = 5  # seconds between uploads for each file
        
    def on_modified(self, event):
        if not event.is_directory:
            current_time = time.time()
            file_path = event.src_path
            
            # Check if enough time has passed since last upload
            if (file_path not in self.last_upload_time or 
                current_time - self.last_upload_time.get(file_path, 0) >= self.upload_cooldown):
                try:
                    upload_blob(file_path, self.logger)
                    self.last_upload_time[file_path] = current_time
                except Exception as e:
                    print(f"Error uploading log to blob storage: {str(e)}")

def start_log_file_monitoring(log_files, logger):
    event_handler = LogFileHandler(logger)
    observer = Observer()
    
    for log_file in log_files:
        observer.schedule(event_handler, path=os.path.dirname(log_file), recursive=False)
    
    observer.start()
    return observer

# Configure logging
log_folder = "logs"
if not os.path.isdir(log_folder):
    os.mkdir(log_folder)

environment = os.getenv("ENVIRONMENT", "development")

# Main service bus logger (existing)
log_filename = "sc_servicebus_" + str(environment) + ".log"
log_filename = os.path.join(log_folder, log_filename)

# New loggers for success and failure
success_log_filename = os.path.join(log_folder, f"successful_files_{environment}.log")
failed_log_filename = os.path.join(log_folder, f"failed_files_{environment}.log")

# Create a custom formatter with readable timestamps
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Configure main service bus logger (existing)
servicebus_handler = TimedRotatingFileHandler(log_filename, when="D", interval=2, backupCount=7, encoding='utf-8')
servicebus_handler.setFormatter(formatter)
servicebus_stream_handler = logging.StreamHandler(sys.stdout)
servicebus_stream_handler.setFormatter(formatter)
servicebus_logger = logging.getLogger('servicebus_logger')
servicebus_logger.setLevel(logging.INFO)
servicebus_logger.addHandler(servicebus_handler)
servicebus_logger.addHandler(servicebus_stream_handler)
servicebus_logger.propagate = False

# Configure success logger
success_handler = TimedRotatingFileHandler(success_log_filename, when="D", interval=2, backupCount=30, encoding='utf-8')
success_handler.setFormatter(formatter)
success_logger = logging.getLogger('success_logger')
success_logger.setLevel(logging.INFO)
success_logger.addHandler(success_handler)
success_logger.propagate = False

# Configure failure logger
failure_handler = TimedRotatingFileHandler(failed_log_filename, when="D", interval=2, backupCount=30, encoding='utf-8')
failure_handler.setFormatter(formatter)
failure_logger = logging.getLogger('failure_logger')
failure_logger.setLevel(logging.INFO)
failure_logger.addHandler(failure_handler)
failure_logger.propagate = False

# Start file monitoring for blob storage uploads
log_files = [log_filename, success_log_filename, failed_log_filename]
observer = start_log_file_monitoring(log_files, servicebus_logger)


# Helper function to get file size in MB
def get_file_size_mb(file_path):
    try:
        size_bytes = os.path.getsize(file_path)
        return round(size_bytes / (1024 * 1024), 2)  # Convert to MB and round to 2 decimal places
    except Exception as e:
        return f"Error getting file size: {str(e)}"


# Helper function to log file processing details
def log_file_processing_details(logger, status, file_data, file_path, page_count, correlation_id, version, 
                              run_classification, run_translation, process_always, tenantid, error=None):
    file_size = get_file_size_mb(file_path)
    
    details = {
        "status": status,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_details": {
            "originalFilename": file_data.get('originalFileName'),
            "fileId": file_data.get('fileId'),
            "fileType": file_data.get('fileType'),
            "size_mb": file_size,
            "page_count": page_count
        },
        "processing_parameters": {
            "correlation_id": correlation_id,
            "version": version,
            "run_classification": run_classification,
            "run_translation": run_translation,
            "process_always": process_always,
            "tenant_id": tenantid
        }
    }
    
    if error:
        details["error"] = str(error)
    
    logger.info(json.dumps(details, indent=2))

ALLOWED_EXTENSION = "pdf"
IMAGE_ALLOWED_EXTENSIONS = ["jpeg", "jpg", "png", "bmp", "tiff", "tif"]
WORD_ALLOWED_EXTENSIONS = ["doc", "docx"]
UPLOAD_FOLDER = "/home/sc_servicebus_data/invoices"
SERVICE_BUS_CONNECTION_STRING = os.getenv("AZURE_SERVICEBUS_CONNECTION_STRING")
SERVICE_BUS_QUEUE_NAME_RECEIVE = os.getenv("SERVICE_BUS_QUEUE_NAME_RECEIVE")
SERVICE_BUS_QUEUE_EXCEPTIONS_RECEIVE = os.getenv("SERVICE_BUS_QUEUE_EXCEPTIONS_RECEIVE")
SERVICE_BUS_QUEUE_EXCEPTIONS_SEND = os.getenv("SERVICE_BUS_QUEUE_EXCEPTIONS_SEND")
# db_connection = db_utils.connect_db()


WHITELISTED_SUPPLIERS = {
    "telstra": 5,
    "komatsu": 0,
    "hertz": 0,
    "agl south australia": 5,
    "team global express": 5,
    "carey mining": 5,
    "coates hire": 5,
    "sg fleet australia": 5,
    "australia post": 5,
    "messagemedia": 5,
    "shell energy": 5,
    "quarrico": 0,
    "ara fire": 5
}


async def process_exceptions_resolution(message):
    try:
        start = datetime.datetime.now()
        data = json.loads(str(message))
        invoice_id = data.get("invoice_id")
        exceptions = data.get("exceptions")
        connection_id = data.get("connectionId")
        user_id = data.get("userId")
        send_queue_name = data.get("queueName")

        servicebus_logger.info(f"Processing exceptions resolution for invoice ID: {invoice_id}")
        servicebus_logger.info(f"Connection ID: {connection_id}, User ID: {user_id}")

        if invoice_id:
            exception_resolution_start_time = time.time()
            try:
                actions = process_exceptions(invoice_id, exceptions)
                servicebus_logger.info(f"Successfully processed exceptions for invoice ID: {invoice_id}")
            except pyodbc.OperationalError as db_error:
                    servicebus_logger.error(f"Database communication error for invoice ID {invoice_id}: {str(db_error)}")
                    actions = {"error": "Database communication error", "details": str(db_error)}
            except KeyError as key_error:
                    servicebus_logger.error(f"Key error for invoice ID {invoice_id}: {str(key_error)}")
                    await send_response_to_queue(invoice_id, str(key_error))
                    actions = {"error": "Invoice ID not found", "details": str(key_error)}
                
            processing_time = time.time() - exception_resolution_start_time
            servicebus_logger.info(f"Exception processing time for invoice ID {invoice_id}: {processing_time:.2f} seconds")
            
            await send_response_to_queue(invoice_id, actions, connection_id, user_id, send_queue_name)
        
    except Exception as e:
        servicebus_logger.error(f"Critical error processing exceptions resolution: {str(e)}")
        servicebus_logger.error(f"Stack trace: {traceback.format_exc()}")


async def send_response_to_queue(invoice_id, actions, connection_id, user_id, send_queue_name):
    try:
        servicebus_logger.info(f"Sending response for invoice ID {invoice_id} to queue {send_queue_name}")
        message_content = {
            "invoice_id": invoice_id,
            "connectionId": connection_id,
            "userId": user_id,
            "actions": actions
        }
        message_body = json.dumps(message_content)

        message = ServiceBusMessage(message_body)
        service_bus_client = ServiceBusClient.from_connection_string(conn_str=SERVICE_BUS_CONNECTION_STRING)
        sender = service_bus_client.get_queue_sender(queue_name=send_queue_name)
        await sender.send_messages(message)

        servicebus_logger.info(f"Successfully sent response for invoice ID {invoice_id} to queue {send_queue_name}")
    except Exception as e:
        servicebus_logger.error(f"Failed to send response for invoice ID {invoice_id}: {str(e)}")
        servicebus_logger.error(f"Stack trace: {traceback.format_exc()}")
        raise


def is_valid_pdf(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type == 'application/pdf'


@backoff.on_exception(backoff.expo, Exception, max_tries=3)
async def process_single_file(file_data, start, process_always, correlation_id, version, run_classification, run_translation, tenant_id):
    downloaded_file_path = None
    try:
        file_id = file_data.get('fileId')
        file_path = file_data.get('filePath')
        file_type = file_data.get('fileType')
        file_name = file_data.get('originalFileName')
        
        servicebus_logger.info(f"Starting to process file: {file_name} (ID: {file_id}, Type: {file_type}, Correlation ID: {correlation_id})")
        
        if not os.path.isdir(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        processing_folder = os.path.join(UPLOAD_FOLDER, correlation_id+str(datetime.datetime.now()).replace(":", "_"))
        os.mkdir(processing_folder)
            
        downloaded_file_path = azure_utils.download_blob_file(file_path, processing_folder)
        
        filename = os.path.basename(downloaded_file_path)
        extension = filename.lower().split('.')[-1]
        filename = secure_filename(filename)
        if filename == extension:
            filename = arabic_util.secure_filename(filename)

        servicebus_logger.info(
            f"Detected file extension: {extension} and file type: {file_type} for file {file_name} with correlation ID {correlation_id}")
        output = None
        # invoice translation
        if run_translation:
            servicebus_logger.info(f'Translation triggered for file -> {filename}')
            translated_file_path, invoice_lang = translate_document(downloaded_file_path)
            translated_file_url, translated_path = azure_utils.upload_file_on_azure(translated_file_path, file_id,
                                                                                    correlation_id,
                                                                                    "translated_invoice")
            downloaded_file_path = translated_file_path
            
        if file_type.lower() == ALLOWED_EXTENSION and is_valid_pdf(downloaded_file_path):
            page_count = pdf_utils.get_page_count(downloaded_file_path)
            servicebus_logger.info(f"PDF contains {page_count} pages. Analyzing for multiple invoices...")
            matched_supplier = None
            if page_count > 50:
                first_page_pdf = pdf_utils.split_pdfs(downloaded_file_path, processing_folder, [1, 2])[0]
                temp_output = process_invoice(first_page_pdf, processing_folder, servicebus_logger, log_filename,
                                              extension.lower(),
                                              process_always, version=version,
                                              run_classification=run_classification, temp=True, file_id=file_id,
                                              correlation_id=correlation_id)
                temp_raw_text = raw_text_utils.get_raw_text(temp_output[0], version)
                for supplier in WHITELISTED_SUPPLIERS:
                    if supplier in temp_raw_text[0].lower():
                        matched_supplier = supplier
                        break
            if (page_count <= 50) or (matched_supplier is not None):
                if matched_supplier is not None and page_count > 50:
                    if WHITELISTED_SUPPLIERS[matched_supplier] != 0:
                        downloaded_file_path = pdf_utils.split_pdfs(downloaded_file_path, processing_folder, [0, WHITELISTED_SUPPLIERS[matched_supplier]])[0]
                output = process_invoice(downloaded_file_path, processing_folder, servicebus_logger, log_filename,
                                         extension.lower(),
                                         process_always, version=version, run_classification=run_classification,
                                         file_id=file_id, correlation_id=correlation_id)
                if output is None:
                    error_msg = "File processing failed with internal server error"
                    log_file_processing_details(
                        failure_logger, "FAILED", file_data, downloaded_file_path, 
                        page_count, correlation_id, version, run_classification, 
                        run_translation, process_always, tenant_id, error=error_msg
                    )
                    return {
                        "fileId": file_id,
                        "originalFileName": file_name,
                        "fileType": file_type,
                        "error": "Internal Server Error",
                    }
                else:
                    log_file_processing_details(
                        success_logger, "SUCCESS", file_data, downloaded_file_path, 
                        page_count, correlation_id, version, run_classification, 
                        run_translation, process_always, tenant_id
                    )
                    servicebus_logger.info(f"File processed successfully: {file_name}")
            else:
                error_msg = "Max Page Limit Reached"
                log_file_processing_details(
                    failure_logger, "FAILED", file_data, downloaded_file_path, 
                    0, correlation_id, version, run_classification, 
                    run_translation, process_always, tenant_id, error=error_msg
                )
                return {
                    "fileId": file_id,
                    "originalFileName": file_name,
                    "fileType": file_type,
                    "error": "Max Page Limit Reached",
                }

        elif file_type.lower() in IMAGE_ALLOWED_EXTENSIONS:
            if not run_translation:
                with Image.open(downloaded_file_path) as img:
                    if img.height <= 350:
                        servicebus_logger.info(
                            f"File with correlation ID {correlation_id} and file name {file_name} skipped due to lower image height.")
                        return None
                    output = process_invoice(downloaded_file_path, processing_folder, servicebus_logger, log_filename,
                                             extension.lower(),
                                             process_always=False, version=version,
                                             run_classification=run_classification, file_id=file_id,
                                             correlation_id=correlation_id)
                    if output is None:
                        error_msg = "Image processing failed with internal server error"
                        log_file_processing_details(
                            failure_logger, "FAILED", file_data, downloaded_file_path, 
                            1, correlation_id, version, run_classification, 
                            run_translation, process_always, tenant_id, error=error_msg
                        )
                        return {
                            "fileId": file_id,
                            "originalFileName": file_name,
                            "fileType": file_type,
                            "error": "Internal Server Error",
                        }
                    else:
                        log_file_processing_details(
                            success_logger, "SUCCESS", file_data, downloaded_file_path, 
                            1, correlation_id, version, run_classification, 
                            run_translation, process_always, tenant_id
                        )
            else:  # if running translation, file already converted to pdf, will process as a pdf file
                output = process_invoice(downloaded_file_path, processing_folder, servicebus_logger, log_filename,
                                         extension.lower(),
                                         process_always, version=version, run_classification=run_classification,
                                         file_id=file_id, correlation_id=correlation_id)
                if output is None:
                    error_msg = "File processing failed with internal server error"
                    log_file_processing_details(
                        failure_logger, "FAILED", file_data, downloaded_file_path, 
                        0, correlation_id, version, run_classification, 
                        run_translation, process_always, tenant_id, error=error_msg
                    )
                    return {
                        "fileId": file_id,
                        "originalFileName": file_name,
                        "fileType": file_type,
                        "error": "Internal Server Error",
                    }
                else:
                    log_file_processing_details(
                        success_logger, "SUCCESS", file_data, downloaded_file_path, 
                        0, correlation_id, version, run_classification, 
                        run_translation, process_always, tenant_id
                    )
                    servicebus_logger.info(f"File processed successfully: {file_name}")
        else:
            if not file_name.lower().endswith('.pdf'):
                # If the file name doesn't end with .pdf, log an error and return the unsupported file type response
                error_msg = "Unsupported file type"
                log_file_processing_details(
                    failure_logger, "FAILED", file_data, downloaded_file_path, 
                    0, correlation_id, version, run_classification, 
                    run_translation, process_always, tenant_id, error=error_msg
                )
                return {
                    "fileId": file_id,
                    "originalFileName": file_name,
                    "fileType": file_type,
                    "error": "Unsupported file type",
                }
            else:
                # If the file name ends with .pdf, attempt to process the file directly as a PDF
                servicebus_logger.info(
                    f"Processing file with correlation ID {correlation_id} and file name {file_name} as a PDF despite unsupported file type.")
                try:
                    # Processing the file as a PDF using the already downloaded file path
                    output = process_invoice(downloaded_file_path, processing_folder, servicebus_logger, log_filename,
                                             extension="pdf",
                                             process_always=process_always, version=version,
                                             run_classification=run_classification, file_id=file_id,
                                             correlation_id=correlation_id)

                    if output is None:
                        error_msg = "File processing failed with internal server error"
                        log_file_processing_details(
                            failure_logger, "FAILED", file_data, downloaded_file_path, 
                            0, correlation_id, version, run_classification, 
                            run_translation, process_always, tenant_id, error=error_msg
                        )
                        return {
                            "fileId": file_id,
                            "originalFileName": file_name,
                            "fileType": file_type,
                            "error": "Internal Server Error",
                        }
                    else:
                        log_file_processing_details(
                            success_logger, "SUCCESS", file_data, downloaded_file_path, 
                            0, correlation_id, version, run_classification, 
                            run_translation, process_always, tenant_id
                        )
                        servicebus_logger.info(f"File processed successfully: {file_name}")
                except Exception as e:
                    error_msg = str(e)
                    log_file_processing_details(
                        failure_logger, "FAILED", file_data, downloaded_file_path or "File not downloaded", 
                        0, correlation_id, version, run_classification, 
                        run_translation, process_always, tenant_id, error=error_msg
                    )
                    servicebus_logger.error(traceback.format_exc())
                    servicebus_logger.error(
                        f"Error processing file with correlation ID {correlation_id}, file name {file_name}: {str(e)}")
                    return {
                        "fileId": file_id,
                        "originalFileName": file_name,
                        "fileType": file_type,
                        "error": str(e),
                    }

        servicebus_logger.info(f"Response dumped to azure storage blob for file with correlation ID {correlation_id} and file name {file_name}.")
        json_response = json.dumps(output, indent=4)
        is_invoice = output[0].get('isInvoice', False)
        is_credit_note = output[0].get('isCreditNote', False)
        response_path, result_path = azure_utils.upload_file_on_azure(json_response, file_id, correlation_id,"json_response")
        compressed_file_path = output[0]['compressedFilePath']
        response = {
            "fileId": file_id,
            "filePath": file_path,
            "resultPath": result_path,
            "fileType": file_type,
            "originalFileName": file_name,
            "isInvoice": is_invoice,
            "isCreditNote": is_credit_note,
            "compressedFilePath": compressed_file_path,
            "error": None,
        }

        if run_translation:
            response["invoiceOriginalLanguage"] = invoice_lang
            response["translatedFilePath"] = translated_path

        return response
    except Exception as e:
        error_msg = str(e)
        log_file_processing_details(
            failure_logger, "FAILED", file_data, downloaded_file_path or "File not downloaded", 
            0, correlation_id, version, run_classification, 
            run_translation, process_always, tenant_id, error=error_msg
        )
        servicebus_logger.error(f"Error processing file {file_name} (Correlation ID: {correlation_id})")
        servicebus_logger.error(f"Error details: {str(e)}")
        servicebus_logger.error(f"Stack trace: {traceback.format_exc()}")
        return {
            "fileId": file_id,
            "originalFileName": file_name,
            "fileType": file_type,
            "error": str(e),
        }
    finally:
        if os.path.exists(processing_folder):
            try:
                shutil.rmtree(processing_folder)
                servicebus_logger.info(f"Cleaned up all processing files for correlation id: {correlation_id}")
            except Exception as e:
                servicebus_logger.error(f"Failed to clean up processing files for correlation id {correlation_id}: {str(e)}")


async def process_and_upload_file(message):
    try:
        start = datetime.datetime.now()
        data = json.loads(str(message))
        correlation_id = data.get('correlationId')
        process_always = data.get('processAllPages')
        tenant_id = data.get('tenantId')
        source_type = data.get('sourceType')
        supplier_customer_id = data.get('supplierCustomerId')
        files_data = data.get('files', [])
        queue_name_send = data.get('queueName')
        version = data.get('version', 'v2.1')
        run_classification = data.get('runClassification', False)
        run_translation = data.get('translate', False)

        servicebus_logger.info(f"Started processing message batch:")
        servicebus_logger.info(f"- Correlation ID: {correlation_id}")
        servicebus_logger.info(f"- Files to process: {len(files_data)}")
        servicebus_logger.info(f"- Version: {version}")
        servicebus_logger.info(f"- Classification enabled: {run_classification}")
        servicebus_logger.info(f"- Translation enabled: {run_translation}")

        responses = await asyncio.gather(
            *[process_single_file(
                file_data, start, process_always, correlation_id,
                version, run_classification, run_translation, tenant_id
            ) for file_data in files_data]
        )
        
        successful = [r for r in responses if r and not r.get('error')]
        failed = [r for r in responses if r and r.get('error')]
        skipped = len(responses) - len(successful) - len(failed)
        
        servicebus_logger.info(f"Batch processing complete for correlation ID {correlation_id}:")
        servicebus_logger.info(f"- Total files: {len(responses)}")
        servicebus_logger.info(f"- Successful: {len(successful)}")
        servicebus_logger.info(f"- Failed: {len(failed)}")
        servicebus_logger.info(f"- Skipped: {skipped}")
        
        valid_responses = [r for r in responses if r is not None]
        await send_message_to_queue(
            correlation_id, tenant_id, source_type,
            supplier_customer_id, valid_responses, queue_name_send
        )
        
    except Exception as e:
        servicebus_logger.error(f"Critical error in batch processing for correlation ID {correlation_id}")
        servicebus_logger.error(f"Error details: {str(e)}")
        servicebus_logger.error(f"Stack trace: {traceback.format_exc()}")
        raise


async def send_message_to_queue(correlation_id, tenant_id, source_type, supplier_customer_id, responses, queue_name_send):
    try:
        message_content = {
            "files": responses,
            "correlationId": correlation_id,
            "tenantId": tenant_id,
            "sourceType": source_type,
            "supplierCustomerId": supplier_customer_id,
            "queueName": queue_name_send
        }
        message_body = json.dumps(message_content)

        message = ServiceBusMessage(message_body)
        service_bus_client = ServiceBusClient.from_connection_string(conn_str=SERVICE_BUS_CONNECTION_STRING)
        sender = service_bus_client.get_queue_sender(queue_name=queue_name_send)
        await sender.send_messages(message)

        servicebus_logger.info(f"Sent confirmation message for correlation ID {correlation_id} to {queue_name_send}")
    except Exception as e:
        servicebus_logger.error(f"Error sending message: {str(e)}")


async def process_invoice_messages():
    try:
        servicebus_logger.info("Starting invoice message processing service")
        async with ServiceBusClient.from_connection_string(
                conn_str=SERVICE_BUS_CONNECTION_STRING,
                logging_enable=True,
        ) as servicebus_client:
            receiver = servicebus_client.get_queue_receiver(queue_name=SERVICE_BUS_QUEUE_NAME_RECEIVE)
            servicebus_logger.info(f"Connected to queue: {SERVICE_BUS_QUEUE_NAME_RECEIVE}")

            async with receiver:
                while True:
                    invoice_msgs = await receiver.receive_messages(max_wait_time=5, max_message_count=20)
                    if invoice_msgs:
                        servicebus_logger.info(f"Received batch of {len(invoice_msgs)} messages")
                    for message in invoice_msgs:
                        try:
                            servicebus_logger.info("Processing message...")
                            asyncio.create_task(process_and_upload_file(message))
                            await receiver.complete_message(message)
                        except Exception as e:
                            servicebus_logger.error(f"Error processing message: {str(e)}")
                            servicebus_logger.error(f"Stack trace: {traceback.format_exc()}")

    except Exception as e:
        servicebus_logger.error("Critical error in invoice message processing service")
        servicebus_logger.error(f"Error details: {str(e)}")
        servicebus_logger.error(f"Stack trace: {traceback.format_exc()}")


async def process_exception_messages():
    try:
        async with ServiceBusClient.from_connection_string(
                conn_str=SERVICE_BUS_CONNECTION_STRING,
                logging_enable=True,
        ) as servicebus_client:

            receiver = servicebus_client.get_queue_receiver(queue_name=SERVICE_BUS_QUEUE_EXCEPTIONS_RECEIVE)

            async with receiver:
                while True:
                    exceptions_msgs = await receiver.receive_messages(max_wait_time=5, max_message_count=20)

                    for message in exceptions_msgs:
                        try:
                            print("Message received:", message.body)
                            await receiver.complete_message(message)
                            asyncio.create_task(process_exceptions_resolution(message))
                        except Exception as e:
                            print(f"Error processing exceptions message: {str(e)}")

    except Exception as e:
        print(f"Error listening for exceptions messages: {str(e)}")


async def listen_for_messages():
    print("IN LISTEN TO MESSAGE")
    while True:
        try:
            await asyncio.gather(
                process_invoice_messages(),
                process_exception_messages()
            )
        except Exception as e:
            print(f"Error listening for messages: {str(e)}")
        await asyncio.sleep(5)
        print("Sleeping")

