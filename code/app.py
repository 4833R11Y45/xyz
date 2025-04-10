import os
import sys
import time
import traceback
from time import sleep
import flask
import subprocess
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import asyncio
from src import service_bus, db_utils
import json
import threading
from processor import process_invoice, process_single_invoice
from exception_processor import process_exceptions
from src.utils.translation import translate_document
from src.utils import arabic_util

log_folder = "logs"
if not os.path.isdir(log_folder):
    os.mkdir(log_folder)

log_filename = os.path.join(log_folder, "sc_app.log")
handler = TimedRotatingFileHandler(log_filename, when="D", interval=2, backupCount=7, encoding='utf-8')
stream_handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger('app_logger')
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(stream_handler)
logger.propagate = False

# db_connection = db_utils.connect_db()

ALLOWED_EXTENSION = "pdf"
IMAGE_ALLOWED_EXTENSIONS = ["jpeg", "jpg", "png", "bmp", "tiff", "tif"]
WORD_ALLOWED_EXTENSIONS = ["doc", "docx"]
UPLOAD_FOLDER = "sc_data/invoices"

app = flask.Flask(__name__)
app.config["DEBUG"] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

correct_auth_token = os.getenv("SPEND_CONSOLE_AUTH_TOKEN")

@app.route('/', methods=['POST'])
def invoice_processor():
    start = datetime.datetime.now()
    start = datetime.datetime.now()
    logger.info("Calling ML service for processing the invoice at %s", start.strftime("%m/%d/%Y, %H:%M:%S"))

    if flask.request.method == 'POST':
        version = flask.request.args.get('version', 'v2.1')
        print(f"Received version: {version}")
        run_classification = flask.request.args.get('run_classification', 'False').lower() == 'true'
        translate = flask.request.args.get('translate', 'False').lower() == 'true'
        print(f"Run Classification: {run_classification}")
        file = flask.request.files.get('file')
        if file is not None:
            if file.filename == '':
                logger.info('No selected file')
                return flask.redirect(flask.request.url)
            extension = file.filename.lower().split('.')[-1]
            # if extension.lower() == ALLOWED_EXTENSION:
            if 'Auth-Token' in flask.request.headers and flask.request.headers['Auth-Token'] == correct_auth_token:

                logger.info("Invoice name: %s", file.filename)
                filename = secure_filename(file.filename)
                if filename == extension:
                    filename = arabic_util.secure_filename(file.filename)
                if not os.path.isdir(UPLOAD_FOLDER):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                pdf_name = os.path.join(UPLOAD_FOLDER, filename)
                file.save(pdf_name)
                # invoice translation
                if translate:
                    logger.info(f'Translation triggered for Invoice -> {file.filename}')
                    pdf_name, _ =translate_document(pdf_name)

                if extension.lower() == ALLOWED_EXTENSION:
                    output = process_invoice(pdf_name, UPLOAD_FOLDER, logger, log_filename, extension.lower(),process_always=False,version=version,run_classification=run_classification, temp=False)
                    if not output:
                        return flask.jsonify("Internal Server Error"), 500
                    logger.info("Processing time: %s", (datetime.datetime.now() - start).seconds)
                    return flask.jsonify(output)
                elif extension.lower() in IMAGE_ALLOWED_EXTENSIONS:
                    if not translate:
                        img = Image.open(pdf_name)
                        if img.height > 350:
                            output = process_invoice(pdf_name, UPLOAD_FOLDER, logger, log_filename, extension.lower(),process_always=False,version=version,run_classification=run_classification, temp=False)
                            if not output:
                                logger.error("Empty response")
                                return flask.jsonify("Internal Server Error"), 500
                            logger.info("Processing time: %s", (datetime.datetime.now() - start).seconds)
                            return flask.jsonify(output)
                        else:
                            return flask.jsonify("Not Acceptable"), 406
                        logger.info("Processing time: %s", (datetime.datetime.now() - start).seconds)
                        return flask.jsonify(output)
                    else: # File already converted to pdf, hence will process like normal pdf file
                        output = process_invoice(pdf_name, UPLOAD_FOLDER, logger, log_filename, extension.lower(),
                                                 process_always=False, version=version,
                                                 run_classification=run_classification, temp=False)
                        if not output:
                            return flask.jsonify("Internal Server Error"), 500
                        logger.info("Processing time: %s", (datetime.datetime.now() - start).seconds)
                        return flask.jsonify(output)
                # elif extension.lower() in WORD_ALLOWED_EXTENSIONS:
                #     print(pdf_name)
                #     opt = subprocess.check_output(['libreoffice', '--convert-to', 'pdf', '--outdir', UPLOAD_FOLDER ,pdf_name])
                #     # opt = subprocess.check_output(["abiword", " --to=pdf", pdf_name])
                #     output = process_invoice(pdf_name.replace("."+extension, ".pdf"), UPLOAD_FOLDER, logger, log_filename,extension=extension.lower(),process_always=False,version=version,run_classification=run_classification)
                #     if not output:
                #         return flask.jsonify("Internal Server Error"), 500
                #     logger.info("Processing time: %s", (datetime.datetime.now() - start).seconds)
                #     return flask.jsonify(output)
                else:
                    return flask.jsonify("Bad Request"), 400


            else:
                return flask.jsonify("Incorrect authentication token"), 401
            # elif extension.lower() in IMAGE_ALLOWED_EXTENSIONS:

        else:
            return flask.jsonify("Bad Request"), 400
@app.route('/exceptions_resolution', methods=['POST'])
def form_upload():
    #try:
    data = flask.request.get_json()
    invoice_id = data.get("invoice_id")
    exceptions = data.get("exceptions")

    print(f"Invoice ID '{invoice_id}' is received, fetching json file.")
    # json_filename = db_utils.get_json_filename(invoice_id, db_connection)

    # if json_filename:
    actions = process_exceptions(invoice_id, exceptions)
    # print("Invoice number: ", json_filename)
    # else:
    #     print("No json file associated with this invoice ID.")

    response = {
        "invoiceId": invoice_id,
        "actions": actions
    }
    #except Exception as e:
       # return flask.jsonify({"message": f"There was an error uploading the file : {e}"}), 500

    return flask.jsonify(response), 200
@app.route('/health_check', methods=['GET'])
def test():
    return flask.jsonify("Test passed")

t= threading.Thread(target=asyncio.run, args=(service_bus.listen_for_messages(),))
t.start()


# if __name__ == '__main__':
#     asyncio.run(service_bus.listen_for_messages())

# if __name__ == '__main__':
#       app.run(host="0.0.0.0", port=5000, use_reloader=False)
