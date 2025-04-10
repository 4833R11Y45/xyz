import traceback
from src import forms_recognizer, raw_text_utils, validation_util, scores_calculator, split_util, mapping_utils
from src.ner import spacy_inference
from src.utils import pdf_utils, azure_utils, currency_extraction, bank_details_util, vat_extraction
from src.ML import classification_inference
from src.generativeai import extraction_util
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException


FR_FIELD_TO_ENTITIY_MAPPING = {"PurchaseOrder": "PurchaseOrder",
                               "ABN": "ABN"}

PO_SYNONYMS = ["po/claim no", "purchase order", "sap", "customer order no", "order","customer order number",
               "your order no", "order no","order no .","order number","order id", "po no", "ship-to-ref" ,"po",
               "assessment number", "p o", "customer reference", "your reference", "reference", "our ref", "ref"]

ADCB_KEYWORDS = ["adcb", "al hilal bank", "abu dhabi commercial bank"]


# log_folder = "logs"
# log_filename = os.path.join(log_folder, "sc_app.log") #% datetime.datetime.now().strftime('%Y-%m-%d')
# handler = TimedRotatingFileHandler(log_filename, when="M", interval=2, backupCount=7, encoding='utf-8')
# logging.basicConfig(format='%(asctime)s; - %(name)s - %(levelname)s - %(message)s',
#                     level=logging.DEBUG, handlers=[handler])
# logging.basicConfig(level=logging.DEBUG)

# handler = TimedRotatingFileHandler(log_filename, when="M", interval=2, encoding='utf-8')
# handler.suffix = "%Y-%m-%d"
# logger = logging.getLogger()
# logger.addHandler(handler)

# log_writer = open(log_filename, 'a')
# sys.stdout = log_writer


def process_single_invoice(pdf, logger, log_filename, extension, version, run_classification, upload_log, final_processing=False, temp=False, file_id=None, correlation_id=None):
    try:
        tapal_placeholders = {"NTN": [], "STRN": []}

        azure_response = forms_recognizer.get_response(pdf, extension, logger, version)
        page_key, text_or_content, value_type = mapping_utils.get_response_structure(version)
        read_results = azure_response.get("analyzeResult", {}).get(page_key, [])
        if all(result.get("lines", []) == [] for result in read_results):
            logger.info("Page is blank or contains no meaningful content.")
            return None, ""

        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(azure_response, version)
        # For cases where there is no text, text is too short, or a blank page return the detected language as unknown
        if not raw_text or len(raw_text.strip()) < 3:
            return "Unknown"
        try:
            detected_language = detect(raw_text)
            if "yemen" in raw_text.lower():
                detected_language = "ar"
        except LangDetectException:
            return "Unknown"

        if (final_processing is True) and (version == "v3.1") and (temp is False):
            if any(bank in raw_text.lower() for bank in ADCB_KEYWORDS):
                azure_response = vat_extraction.extract_vat_info(azure_response)
            # if "InvoiceId" in azure_response['analyzeResult']["documents"][0]['fields']:
            azure_response = extraction_util.update_fields_using_genai(azure_response, detected_language)
        # raw_text = raw_text_utils.get_raw_text(azure_response)
        missing_fields = validation_util.get_missing_fields(azure_response,version)
        logger.debug("Missing fields: %s", str(missing_fields))
        page_blocks_list = raw_text_utils.identify_blocks(azure_response,version)
        other_fields = raw_text_utils.other_field_values(page_blocks_list)
        print("Other fields: %s", str(other_fields))

        # blocks_text = raw_text_utils.get_blocks_text(page_blocks_list)
        entities = spacy_inference.predict(raw_text)
        logger.debug("Extracted entities: %s", str(entities))
        entities = validation_util.validate_ner_fields(raw_text, entities, logger)
        bank_dets_entities, associated_bank_dets = bank_details_util.extract_bank_details(entities, raw_text, other_fields)
        logger.debug("Entities after validation: %s", str(entities))
        logger.debug("Associated bank entities: %s", str(associated_bank_dets))
        tapal_entities = spacy_inference.predict_ntn_strn_num(raw_text, tapal_placeholders)
        print(tapal_entities)
        container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
        detected_currency = currency_extraction.find_currency(azure_response, raw_text, container_key, text_or_content)
        tapal_entities = validation_util.populate_ntn_strn(raw_text, tapal_entities, version)
        strn_num = tapal_entities["STRN"]
        if not azure_response['analyzeResult'][container_key]:
            azure_response['analyzeResult'][container_key].append({'fields': {}})
        if strn_num:
            azure_response['analyzeResult'][container_key][0]['fields']["STRN"] = {
                "type": "string",
                "valueString": strn_num,
                text_or_content: strn_num
            }
        if "adj no" in other_fields:
            adj_no = pdf_utils.extract_adj_no(pdf)
            if adj_no:
                if adj_no:
                    azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                        "type": "string",
                        "valueString": adj_no,
                        text_or_content: adj_no
                    }
        if "tapal" in raw_text.lower() and final_processing:
            employee_ids = pdf_utils.extract_employee_ids(pdf)
            if employee_ids:
                azure_response = validation_util.populate_employee_id(azure_response, raw_text, version, employee_ids)
        iban_num = raw_text_utils.extract_iban_num(raw_text)
        if raw_text_utils.is_australian_address(raw_text):
            if bank_dets_entities["ABN"]:
                azure_response['analyzeResult'][container_key][0]['fields']["TaxID"] = \
                 {text_or_content: bank_dets_entities["ABN"], "valueString": bank_dets_entities["ABN"], "type": "ABN"}
            if bank_dets_entities["AccountNum"]:
                account_num = bank_dets_entities["AccountNum"][0]
                azure_response['analyzeResult'][container_key][0]['fields']["AccountDetails"] = \
                 {text_or_content: account_num, "valueString": account_num, "type": "AccountNum"}
        else:
            if tapal_entities["NTN"]:
                azure_response['analyzeResult'][container_key][0]['fields']["TaxID"] = \
                 {text_or_content: tapal_entities["NTN"], "valueString": tapal_entities["NTN"], "type": "NTN"}
            if iban_num:
                azure_response['analyzeResult'][container_key][0]['fields']["AccountDetails"] = \
                    {text_or_content: iban_num, "valueString": iban_num,
                     "type": "IBAN"}
            trns = []
            if "customer_TRN" in azure_response['analyzeResult'][container_key][0]['fields']:
                trns.append(azure_response['analyzeResult'][container_key][0]['fields']["customer_TRN"]["content"])
            if "vendor_TRN" in azure_response['analyzeResult'][container_key][0]['fields']:
                trns.append(azure_response['analyzeResult'][container_key][0]['fields']["vendor_TRN"]["content"])
            if trns:
                azure_response['analyzeResult'][container_key][0]['fields']["TaxID"] = \
                    {text_or_content: trns, "valueString": trns, "type": "TRN"}


        azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"] = bank_dets_entities
        azure_response['analyzeResult'][container_key][0]['fields']["AssocBankDetails"] = associated_bank_dets
        azure_response['analyzeResult'][container_key][0]['fields']["Currency"] = detected_currency
        azure_response = validation_util.populate_po(azure_response, raw_text, raw_text_without_spaces,
                                                     entities, PO_SYNONYMS, other_fields, missing_fields,
                                                     FR_FIELD_TO_ENTITIY_MAPPING, version)
        logger.debug("Entities after adding PO value: %s", str(entities))

        lpo_value = raw_text_utils.extract_lpo(raw_text)
        if lpo_value:
            azure_response['analyzeResult'][container_key][0]['fields']["LPO"] = {
                "type": "string",
                "valueString": lpo_value,
                text_or_content: lpo_value}

        azure_response['isTaxInvoice'] = raw_text_utils.check_is_tax_invoice(raw_text)
        azure_response['isCreditNote'] = raw_text_utils.check_is_credit_note(azure_response, raw_text, version)

        if detected_language != "ar":
            azure_response = validation_util.validate_po(azure_response, raw_text,version)
        azure_response = validation_util.validate_fr_fields(azure_response, raw_text, page_blocks_list, other_fields,
                                                            version, detected_language, final_processing)
        azure_response = validation_util.validate_invoice_from_raw_text(azure_response, raw_text, version)
        #azure_response = validation_util.populate_employee_id(azure_response, raw_text, version)
        if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields'] and "LPO" in azure_response['analyzeResult'][container_key][0]['fields']:
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {
                "type": "string",
                "valueString": lpo_value,
                text_or_content: lpo_value}
       # print(page_blocks_list)

        logger.debug("Entities: ", entities)
        logger.debug("Calculating overall confidence")
        overall_conf_score = scores_calculator.calc_conf_score(azure_response,version)
        logger.debug(overall_conf_score)
        logger.debug("Calculating completeness score")
        completeness_score = scores_calculator.calc_completeness_score(azure_response,version)
        logger.debug(completeness_score)
        azure_response['analyzeResult'][container_key][0]['overallConfidence'] = overall_conf_score
        azure_response['analyzeResult'][container_key][0]['completenessScore'] = completeness_score

        azure_response['invoiceB64Data'], azure_response['compressedFilePath'] = pdf_utils.base64_encode(pdf, final_processing, file_id, correlation_id)

        if version == 'v2.1':
            azure_response = validation_util.extract_total_tax(azure_response,raw_text)
        azure_response = validation_util.populate_credit_note_num(azure_response, other_fields, raw_text, version)
        azure_response = validation_util.convert_negative_to_positive(azure_response, "InvoiceTotal",version)
        azure_response = validation_util.convert_negative_to_positive(azure_response, "TotalTax",version)
        azure_response = validation_util.convert_negative_to_positive(azure_response, "SubTotal",version)
        azure_response = raw_text_utils.hardcoded_7_eleven_values(azure_response, final_processing, version)

        excluded = raw_text_utils.get_excluded_list(raw_text, page_blocks_list)
        azure_response["excludedLabels"] = excluded

        if completeness_score < 0.3 and detected_language != "ar":
            azure_response['isInvoice'] = False
        else:
            azure_response['isInvoice'] = True
        if run_classification:
            template = classification_inference.predict_template(raw_text)
            print("Predicted Invoice Template:", template)
            azure_response['invoiceTemplate'] = template

        azure_response['isBill'] = raw_text_utils.is_utility_bill(raw_text)
        if azure_response['isBill'] is True:
            azure_response['greenhouse_emission'] = raw_text_utils.extract_co2_emission(raw_text)
        azure_response['isScanned'] = pdf_utils.check_scanned(pdf)
        azure_response = validation_util.final_invoice_verification(raw_text, azure_response,version, detected_language)
        if upload_log is True:
            azure_utils.upload_blob(log_filename, logger)
        return azure_response, raw_text
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
        if upload_log is True:
            azure_utils.upload_blob(log_filename, logger)
        return None


def process_invoice(pdf, pdf_path, logger, log_filename, extension, process_always, version, run_classification,
                        upload_log=True, temp=False, file_id=None, correlation_id=None):
    print("Extension: ", extension)
    page_count = pdf_utils.get_page_count(pdf)
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    responses = []
    if page_count <= 1:
        azure_response, raw_text = process_single_invoice(pdf, logger, log_filename, extension, version, run_classification, upload_log=upload_log, final_processing=True, temp=temp, file_id=file_id, correlation_id=correlation_id)
        if (len(raw_text) < 350 or raw_text.count("&") >= 10 or raw_text.count("!") >= 20 or raw_text.count("%") >= 20) and extension.lower() == "pdf":
            updated_path = pdf_utils.convert_pdf_to_image(pdf)
            azure_response, raw_text = process_single_invoice(updated_path, logger, log_filename, "jpg", version, run_classification, upload_log=upload_log, final_processing=True, temp=temp, file_id=file_id, correlation_id=correlation_id)
        responses.append(azure_response)
    elif 1 < page_count < 30 or process_always is True:
        logger.info("PDF contains %s pages. Analysing PDF to identify if it contains multiple invoices" % page_count)
        # split_pdf_paths = pdf_utils.split_individual_page_into_multiple_pdfs(pdf, pdf_path)
        try:
            split_pdf_paths = pdf_utils.split_pdfs(pdf, pdf_path, list(range(1, page_count + 1)))
            temp_responses = []
            temp_raw_texts = []
            for path in split_pdf_paths:
                print("*"*50, path)
                # temp_azure_response = forms_recognizer.get_response(path, extension)
                temp_azure_response, temp_raw_text = process_single_invoice(path, logger, log_filename, extension, version, run_classification, upload_log=upload_log, file_id=file_id, correlation_id=correlation_id)
                if temp_azure_response is not None or len(temp_raw_text) < 350 or temp_raw_text.count("&") >= 10:
                    updated_path = pdf_utils.convert_pdf_to_image(path)
                    temp_azure_response, temp_raw_text = process_single_invoice(updated_path, logger, log_filename, "jpg", version, run_classification, upload_log=upload_log, file_id=file_id, correlation_id=correlation_id)
                if temp_azure_response:
                    temp_responses.append(temp_azure_response)
                    temp_raw_texts.append(temp_raw_text)
                # temp_responses.append(temp_azure_response)
                # temp_raw_texts.append(temp_raw_text)
            split_points = split_util.find_splits(temp_responses, temp_raw_texts,version)

            # split_points = pdf_utils.extract_text_and_find_split_points(pdf)
            logger.info("Found %s invoices in the pdf document" % len(split_points))
        except ValueError as e:
            print("There is an unknown issue with PDF, treating it as a single invoice")
            split_points = []
        if split_points:
            split_pdfs_paths = pdf_utils.split_pdfs(pdf, pdf_path, split_points)
            for individual_pdf in split_pdfs_paths:
                logger.info("Sending %s to Form Recognizer+AI Engine" % individual_pdf.split("/")[-1])
                azure_response, raw_text = process_single_invoice(individual_pdf, logger, log_filename, extension, version, run_classification, upload_log=upload_log, final_processing=True, file_id=file_id, correlation_id=correlation_id)
                if azure_response and azure_response.get('analyzeResult'):
                    responses.append(azure_response)
                else:
                    logger.info("Page %s is blank or invalid. Skipping..." % individual_pdf.split("/")[-1])
            if responses:
                responses = validation_util.validate_responses(responses, version)
            else:
                logger.warning("No valid responses to validate.")
        else:
            if page_count > 20 and temp_azure_response['isBill']:
                split_pdf_paths = pdf_utils.split_pdfs(pdf, pdf_path, list(range(1, min(page_count, 6))))
                tax_invoice_page = None
                # Checking for 'Tax Invoice' label in response of first 5 pages
                for i, path in enumerate(split_pdf_paths):
                    azure_response, raw_text = process_single_invoice(path, logger, log_filename, extension, version,
                                                                      run_classification, upload_log=upload_log,
                                                                      file_id=file_id, correlation_id=correlation_id)
                    if azure_response and azure_response.get('isTaxInvoice', False):
                        tax_invoice_page = i + 1
                        break

                if tax_invoice_page:
                    # If found, the page with tax invoice with 3 pages is sent in single split
                    start_page = tax_invoice_page
                    end_page = min(page_count, tax_invoice_page + 3)
                    split_pdf_path = pdf_utils.split_pdfs(pdf, pdf_path, list(range(start_page, end_page + 1)))[0]
                    logger.info("Sending pages %s to %s to Form Recognizer+AI Engine" % (start_page, end_page))
                    azure_response, raw_text = process_single_invoice(split_pdf_path, logger, log_filename, extension,
                                                                      version, run_classification,
                                                                      upload_log=upload_log, final_processing=True,
                                                                      file_id=file_id, correlation_id=correlation_id)
                    responses.append(azure_response)
                else:
                    # If not found, only first page is sent in response
                    split_points = [1]
                    split_pdfs_paths = pdf_utils.split_pdfs(pdf, pdf_path, split_points)
                    for individual_pdf in split_pdfs_paths:
                        logger.info("Sending %s to Form Recognizer+AI Engine" % individual_pdf.split("/")[-1])
                        azure_response, raw_text = process_single_invoice(individual_pdf, logger, log_filename,
                                                                          extension, version, run_classification,
                                                                          upload_log=upload_log, final_processing=True,
                                                                          file_id=file_id, correlation_id=correlation_id)
                        responses.append(azure_response)
            else:
                azure_response, raw_text = process_single_invoice(pdf, logger, log_filename, extension, version,
                                                                  run_classification, upload_log=upload_log,
                                                                  final_processing=True,
                                                                  file_id=file_id, correlation_id=correlation_id)
                if azure_response is not None and (len(raw_text) < 350 or raw_text.count("&") >= 14) and \
                        azure_response['analyzeResult'][container_key][0]['completenessScore'] < 0.2:
                    updated_path = pdf_utils.convert_pdf_to_image(pdf)
                    azure_response, raw_text = process_single_invoice(updated_path, logger, log_filename, "jpg",
                                                                      version,
                                                                      run_classification, upload_log=upload_log,
                                                                      final_processing=True,
                                                                      file_id=file_id, correlation_id=correlation_id)
                if azure_response:
                    responses.append(azure_response)

    else:
        print("Too many pages..Processing the first only")
        split_points = [1]
        split_pdfs_paths = pdf_utils.split_pdfs(pdf, pdf_path, split_points)
        for individual_pdf in split_pdfs_paths:
            logger.info("Sending %s to Form Recognizer+AI Engine" % individual_pdf.split("/")[-1])
            azure_response, raw_text = process_single_invoice(individual_pdf, logger, log_filename, extension, version, run_classification, upload_log=upload_log, final_processing=True, file_id=file_id, correlation_id=correlation_id)
            responses.append(azure_response)

    return responses
