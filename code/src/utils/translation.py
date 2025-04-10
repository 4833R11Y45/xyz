from google.cloud import translate_v3beta1 as translate
import os
from PIL import Image
from src.utils import azure_utils
import json
import img2pdf
import tempfile
import logging
import fitz
logger = logging.getLogger("app_logger")
def set_google_application_credentials():
    google_credentials = azure_utils.get_google_credentials()

    # Create a temporary file to store credentials
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as temp_file:
        temp_file.write(json.dumps(google_credentials))

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file.name

set_google_application_credentials()
PROJECT_ID = "core-parsec-423823-m6"

def remove_text_layer(input_pdf, output_pdf):
    pdf_document = fitz.open(input_pdf)
    new_pdf = fitz.open()

    for page_number in range(len(pdf_document)):
        page = pdf_document.load_page(page_number)
        pix = page.get_pixmap()
        new_page = new_pdf.new_page(width=pix.width, height=pix.height)
        new_page.insert_image(new_page.rect, pixmap=pix)

    # creating temp file to store non ocr version
    temp_output_path = output_pdf + '.tmp'
    new_pdf.save(temp_output_path)
    new_pdf.close()
    pdf_document.close()

    # now overwrite non ocr file on same path
    os.replace(temp_output_path, output_pdf)
def convert_img_to_pdf(file_path):
    image = Image.open(file_path)
    pdf_bytes = img2pdf.convert(image.filename)
    file = open(f'{file_path}.pdf', "wb")
    file.write(pdf_bytes)
    image.close()
    file.close()
    logger.info(f"Converted image to PDF...")
    return f'{file_path}.pdf'


def translate_document(file_path: str):
    if any(file_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp']):
        file_path = convert_img_to_pdf(file_path)
    else:
        remove_text_layer(file_path, file_path)

    client = translate.TranslationServiceClient()
    parent = f"projects/{PROJECT_ID}/locations/global"

    with open(file_path, "rb") as document:
        document_content = document.read()

    document_input_config = {
        "content": document_content,
        "mime_type": "application/pdf",
    }

    response = client.translate_document(
        request={
            "parent": parent,
            "target_language_code": "en",
            "document_input_config": document_input_config,
        }
    )

    with open(file_path, 'wb') as f:
        f.write(response.document_translation.byte_stream_outputs[0])

    detected_lang = response.document_translation.detected_language_code

    logger.info(
        f"Response: Detected Language - {detected_lang}"
    )
    logger.info('Invoice Translated')
    return file_path, detected_lang
