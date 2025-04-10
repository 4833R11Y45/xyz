import os
import sys
import glob
import json
import logging
from collections import defaultdict
from logging.handlers import TimedRotatingFileHandler
from PIL import Image
import processor
from src import forms_recognizer, raw_text_utils, validation_util
from src.ner import spacy_inference
from src.ML import classification_inference

log_folder = "../logs"
# log_filename = os.path.join(log_folder, "pytest.log")
log_filename = "pytest.log"
open(log_filename, 'a').close()
# os.makedirs(log_folder, exist_ok=True)
handler = TimedRotatingFileHandler(log_filename, when="D", interval=2, backupCount=7, encoding='utf-8')
stream_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(format='%(asctime)s; - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG, handlers=[handler, stream_handler])
# handler.suffix = "%Y-%m-%d"
logger = logging.getLogger()


class TestMLAPP():
    def test_sample(self):
        assert True

    def test_v2_output(self):
        test_pdf_path = "fixtures/CSVN515208.pdf"
        test_pdf_path = os.path.abspath(test_pdf_path)
        output = processor.process_invoice(test_pdf_path, "fixtures", logger, log_filename, "pdf",
                                           process_always=False, version='v2.1', upload_log=False,run_classification=False)
        assert output
        assert type(output[0]) == dict

    def test_v3_output(self):
        test_pdf_path = "fixtures/CSVN515208.pdf"
        test_pdf_path = os.path.abspath(test_pdf_path)
        output = processor.process_invoice(test_pdf_path, "fixtures", logger, log_filename, "pdf",
                                           process_always=False, version='v3.1', upload_log=False,run_classification=False)
        assert output
        assert type(output[0]) == dict

    def test_form_recognizer_response_v2_pdf(self, form_recognizer_response_v2):
        test_pdf_path = "fixtures/CSVN515208.pdf"
        test_pdf_path = os.path.abspath(test_pdf_path)
        azure_response = forms_recognizer.get_response(test_pdf_path, "pdf", logger, version='v2.1')
        print(type(azure_response))

        assert azure_response
        assert type(azure_response) == dict
        assert "status" in azure_response
        assert azure_response["status"] == "succeeded"
        assert azure_response["analyzeResult"] == form_recognizer_response_v2["analyzeResult"]

    def test_form_recognizer_response_v3_pdf(self, form_recognizer_response_v3):
        test_pdf_path = "fixtures/CSVN515208.pdf"
        test_pdf_path = os.path.abspath(test_pdf_path)
        azure_response = forms_recognizer.get_response(test_pdf_path, "pdf", logger, version='v3.1')
        print(type(azure_response))

        assert azure_response
        assert type(azure_response) == dict
        assert "status" in azure_response
        assert azure_response["status"] == "succeeded"
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["CustomerAddressRecipient"]["valueString"] == form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["CustomerAddressRecipient"]["valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["CustomerId"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["CustomerId"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["CustomerName"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["CustomerName"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["CustomerAddress"]["content"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["CustomerAddress"][
                   "content"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["DueDate"]["valueDate"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["DueDate"][
                   "valueDate"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["InvoiceDate"]["valueDate"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["InvoiceDate"][
                   "valueDate"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["InvoiceId"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["InvoiceId"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["InvoiceTotal"]["content"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["InvoiceTotal"][
                   "content"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["RemittanceAddress"]["content"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["RemittanceAddress"][
                   "content"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["RemittanceAddressRecipient"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["RemittanceAddressRecipient"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["ServiceAddressRecipient"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["ServiceAddressRecipient"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["ServiceEndDate"]["valueDate"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["ServiceEndDate"][
                   "valueDate"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["ServiceStartDate"]["valueDate"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["ServiceStartDate"][
                   "valueDate"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["SubTotal"]["content"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["SubTotal"][
                   "content"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["TotalTax"]["content"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["TotalTax"][
                   "content"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["VendorAddressRecipient"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["VendorAddressRecipient"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["VendorAddress"]["content"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["VendorAddress"][
                   "content"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["VendorName"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["VendorName"][
                   "valueString"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["VendorTaxId"]["valueString"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["VendorTaxId"][
                   "valueString"]
        assert len(azure_response["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"]) == \
               len(form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["Items"][
                   "valueArray"])
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0]["valueObject"]["Amount"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0]["valueObject"]["Amount"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0]["valueObject"][
                   "Quantity"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0][
                   "valueObject"]["Quantity"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0]["valueObject"][
                   "Description"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0][
                   "valueObject"]["Description"]
        assert azure_response["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0]["valueObject"][
                   "UnitPrice"] == \
               form_recognizer_response_v3["analyzeResult"]["documents"][0]["fields"]["Items"]["valueArray"][0][
                   "valueObject"]["UnitPrice"]

    def test_validate_missing_fields(self, form_recognizer_response_v2):
        missing_fields = validation_util.get_missing_fields(form_recognizer_response_v2, version='v2.1')
        assert missing_fields
        assert missing_fields == ['ABN']

    def test_other_fields(self, form_recognizer_response_v2):
        page_blocks_list = raw_text_utils.identify_blocks(form_recognizer_response_v2, version='v2.1')
        assert page_blocks_list

        other_fields = raw_text_utils.other_field_values(page_blocks_list)
        assert other_fields
        assert (type(other_fields) == dict or type(other_fields) == defaultdict)

    def test_raw_text_v2(self, form_recognizer_response_v2):
        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(form_recognizer_response_v2, version='v2.1')
        assert raw_text
        assert type(raw_text) == str

    def test_raw_text_v3(self, form_recognizer_response_v3):
        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(form_recognizer_response_v3, version='v3.1')
        assert raw_text
        assert type(raw_text) == str

    def test_spacy_inference_v2(self, form_recognizer_response_v2):
        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(form_recognizer_response_v2, version='v2.1')
        entities = spacy_inference.predict(raw_text)
        assert entities
        assert type(entities) == dict

    def test_spacy_inference_v3(self, form_recognizer_response_v3):
        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(form_recognizer_response_v3, version='v3.1')
        entities = spacy_inference.predict(raw_text)
        assert entities
        assert type(entities) == dict

    def test_classification_inference_v2(self,form_recognizer_response_v2):
        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(form_recognizer_response_v2, version='v2.1')
        entities = classification_inference.predict_template(raw_text)
        assert entities
        assert isinstance(entities, dict)
        assert 'predicted_category' in entities
        assert 'gl_code' in entities or entities['predicted_category'] not in classification_inference.category_to_gl_mapping

    def test_classification_inference_v3(self, form_recognizer_response_v3):
        raw_text, raw_text_without_spaces = raw_text_utils.get_raw_text(form_recognizer_response_v3, version='v3.1')
        entities = classification_inference.predict_template(raw_text)
        assert entities
        assert isinstance(entities, dict)
        assert 'predicted_category' in entities
        assert 'gl_code' in entities or entities[
            'predicted_category'] not in classification_inference.category_to_gl_mapping
    def test_extraction_v2(self):
        invoices = glob.glob("fixtures/Invoices Test Set/*/*/*.pdf")
        for invoice in invoices:
            print("Testing extraction results for: ", invoice)
            output = processor.process_invoice(invoice, "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v2.1', upload_log=False,run_classification=False)
            assert output
            with open(invoice.replace(".pdf", ".json"), "rb") as f:
                expected_output = json.load(f)

            if "PurchaseOrder" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["PurchaseOrder"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["PurchaseOrder"]["text"]

            if "InvoiceId" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceId"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceId"]["text"]

            if "InvoiceDate" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceDate"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceDate"]["text"]

            if "DueDate" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["DueDate"]["text"]  == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["DueDate"]["text"]

            if "CustomerName" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["CustomerName"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["CustomerName"]["text"]

            if "CustomerAddress" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["CustomerAddress"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["CustomerAddress"]["text"]

            if "CustomerAddressRecipient" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["CustomerAddressRecipient"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["CustomerAddressRecipient"]["text"]

            if "VendorName" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["VendorName"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["VendorName"]["text"]

            if "VendorAddress" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["VendorAddress"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["VendorAddress"]["text"]

            if "VendorAddressRecipient" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["VendorAddressRecipient"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["VendorAddressRecipient"]["text"]

            if "BillingAddress" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["BillingAddress"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BillingAddress"]["text"]

            if "BillingAddressRecipient" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["BillingAddressRecipient"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BillingAddressRecipient"]["text"]

            if "RemittanceAddress" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["RemittanceAddress"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["RemittanceAddress"]["text"]

            if "RemittanceAddressRecipient" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["RemittanceAddressRecipient"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["RemittanceAddressRecipient"]["text"]

            if "SubTotal" in output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["SubTotal"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["SubTotal"]["text"]

            if "TotalTax" in output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["TotalTax"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["TotalTax"]["text"]

            if "InvoiceTotal" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceTotal"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["InvoiceTotal"]["text"]

            if "AmountDue" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                assert output[0]["analyzeResult"]["documentResults"][0]["fields"]["AmountDue"]["text"] == \
                       expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["AmountDue"]["text"]

            if "BankDetails" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                if "ABN" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]:
                    assert sorted(set(output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["ABN"])) == \
                           sorted(set(expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["ABN"]))
                if "AccountName" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]:
                    assert sorted(set(output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["AccountName"])) == \
                           sorted(set(expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"][
                               "AccountName"]))
                if "AccountNum" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]:
                    assert sorted(set(output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["AccountNum"])) == \
                           sorted(set(expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"][
                               "AccountNum"]))
                if "BankName" in output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]:
                    assert sorted(set(output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["BankName"])) == \
                           sorted(set(expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"][
                               "BankName"]))
                if "BSB" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]:
                    assert sorted(set(output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["BSB"])) == \
                           sorted(set(expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["BSB"]))
                if "SwiftCode" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]:
                    assert sorted(set(output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"]["SwiftCode"])) == \
                           sorted(set(expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["BankDetails"][
                               "SwiftCode"]))

            assert output[0]["isInvoice"] is True

    def test_extraction_v3(self):
        invoices = glob.glob("fixtures/Invoices Test Set v3/*/*/*.pdf")
        for invoice in invoices:
            print("Testing extraction results for: ", invoice)
            output = processor.process_invoice(invoice, "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v3.1', upload_log=False,run_classification=False)
            assert output
            with open(invoice.replace(".pdf", ".json"), "rb") as f:
                expected_output = json.load(f)

            if "PurchaseOrder" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"]["content"]
                if "potential" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"]:
                    potential_output = sorted(set(output[0]["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"]["potential"]))
                    potential_expected = sorted(set(expected_output[0]["analyzeResult"]["documents"][0]["fields"]["PurchaseOrder"]["potential"]))
                    assert  potential_output == potential_expected

            if "InvoiceId" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceId"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceId"]["content"]

            if "InvoiceDate" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceDate"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceDate"]["content"]

            if "DueDate" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["DueDate"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["DueDate"]["content"]

            if "CustomerName" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["CustomerName"]["content"].replace(",", "") == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["CustomerName"]["content"].replace(",", "")

            if "CustomerAddress" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["CustomerAddress"]["content"].replace(",", "") == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["CustomerAddress"]["content"].replace(",", "")

            if "CustomerAddressRecipient" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["CustomerAddressRecipient"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["CustomerAddressRecipient"]["content"]

            if "VendorName" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["VendorName"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["VendorName"]["content"]

            if "VendorAddress" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["VendorAddress"]["content"].replace(",", "") == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["VendorAddress"]["content"].replace(",", "")

            if "VendorAddressRecipient" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["VendorAddressRecipient"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["VendorAddressRecipient"]["content"]

            if "BillingAddress" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                print("Output: ", output[0]["analyzeResult"]["documents"][0]["fields"]["BillingAddress"]["content"])
                print("Expected Output: ", expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BillingAddress"]["content"])
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["BillingAddress"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BillingAddress"]["content"]

            if "BillingAddressRecipient" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["BillingAddressRecipient"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BillingAddressRecipient"]["content"]

            if "RemittanceAddress" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["RemittanceAddress"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["RemittanceAddress"]["content"]

            if "RemittanceAddressRecipient" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["RemittanceAddressRecipient"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["RemittanceAddressRecipient"]["content"]

            if "SubTotal" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["SubTotal"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["SubTotal"]["content"]

            if "TotalTax" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["TotalTax"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["TotalTax"]["content"]

            if "InvoiceTotal" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceTotal"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["InvoiceTotal"]["content"]

            if "AmountDue" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                assert output[0]["analyzeResult"]["documents"][0]["fields"]["AmountDue"]["content"] == \
                       expected_output[0]["analyzeResult"]["documents"][0]["fields"]["AmountDue"]["content"]

            if "BankDetails" in output[0]["analyzeResult"]["documents"][0]["fields"]:
                if "ABN" in output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]:
                    assert sorted(output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["ABN"]) == \
                           sorted(
                               expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["ABN"])
                if "AccountName" in output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]:
                    assert output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["AccountName"] == \
                           expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"][
                               "AccountName"]
                if "AccountNum" in output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]:
                    assert output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["AccountNum"] == \
                           expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"][
                               "AccountNum"]
                if "BankName" in output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]:
                    assert output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["BankName"] == \
                           expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"][
                               "BankName"]
                if "BSB" in output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]:
                    assert sorted(output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["BSB"]) == \
                           sorted(expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["BSB"])
                if "SwiftCode" in output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]:
                    assert output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"]["SwiftCode"] == \
                           expected_output[0]["analyzeResult"]["documents"][0]["fields"]["BankDetails"][
                               "SwiftCode"]

            assert output[0]["isInvoice"] == expected_output[0]["isInvoice"]
    def test_noninvoice_v2(self):
        noninvoices = glob.glob("fixtures/Non Invoices Test Set/*/*.pdf")
        for noninvoice in noninvoices:
            print("Testing Non Invoice: ", noninvoice)
            output = processor.process_invoice(noninvoice, "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v2.1', upload_log=False,run_classification=False)
            assert output
            assert output[0]["isInvoice"] is False

    def test_invoice_split_v2(self):
        invoices = glob.glob(r"fixtures/Multi-page-invoices/*/*.pdf")
        for invoice in invoices:
            print("Testing for Multiple Invoices: ", invoices)
            output = processor.process_invoice(invoice, "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v2.1', upload_log=False,run_classification=False)
            assert output
            with open(invoice.replace(".pdf", ".json"), "rb") as f:
                expected_output = json.load(f)

            assert len(output) == len(expected_output)

    def test_images_v2(self):
        images = glob.glob(r"fixtures/Images/*")
        for image in images:
            print("Testing for images: ", images)
            IMAGE_ALLOWED_EXTENSIONS = ["jpeg", "jpg", "png", "bmp", "tiff", "tif"]
            extension = image.lower().split('.')[-1]
            output = None
            if extension.lower() in IMAGE_ALLOWED_EXTENSIONS:
                img = Image.open(image)
                if img.height > 350:
                    output = processor.process_invoice(image, "fixtures", logger, log_filename, extension.lower(),
                                                       process_always=False, version='v2.1', upload_log=False,run_classification=False)
            assert output is not None
            assert output[0]["isInvoice"] is True

    def test_creditmemo_v2(self):
        creditmemos = glob.glob("fixtures/credit_memos/*")
        for creditmemo in creditmemos:
            print("Testing Credit Memos: ", creditmemo)
            output = processor.process_invoice(creditmemo, "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v2.1', upload_log=False,run_classification=False)
            assert output
            assert output[0]["isCreditNote"] is True


    def test_contract_num_v2(self):
        contracts = glob.glob("fixtures/contracts_test/*.pdf")
        for contract in contracts:
            print("Testing Contract Invoices: ", contract)
            output = processor.process_invoice(os.path.abspath(contract), "fixtures", logger, log_filename, "pdf",
                                           process_always=False, version='v2.1', upload_log=False,
                                           run_classification=False)
            assert output

            expected_output_file = contract.replace(".pdf", ".json")
            with open(os.path.abspath(expected_output_file), "rb") as f:
                expected_output = json.load(f)
                if "ContractId" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                    expected_contract_id = expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]["ContractId"]
                    actual_contract_id = output[0]["analyzeResult"]["documentResults"][0]["fields"]["ContractId"]

                    assert actual_contract_id == expected_contract_id

    def test_contract_num_v3(self):
        contracts = glob.glob("fixtures/contracts_test_v3/*.pdf")
        for contract in contracts:
            print("Testing Contract Invoices: ", contract)
            output = processor.process_invoice(os.path.abspath(contract), "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v3.1', upload_log=False,
                                               run_classification=False)
            assert output

            expected_output_file = contract.replace(".pdf", ".json")
            with open(os.path.abspath(expected_output_file), "rb") as f:
                expected_output = json.load(f)
                if "ContractId" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                    expected_contract_id = expected_output[0]["analyzeResult"]["documents"][0]["fields"][
                        "ContractId"]
                    actual_contract_id = output[0]["analyzeResult"]["documents"][0]["fields"]["ContractId"]

                    assert actual_contract_id == expected_contract_id

    def test_shipment_num_v2(self):
        shipments = glob.glob("fixtures/shipment_number/*.pdf")
        for shipment in shipments:
            print("Testing Shipment Invoices: ", shipment)
            output = processor.process_invoice(os.path.abspath(shipment), "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v2.1', upload_log=False,
                                               run_classification=False)
            assert output

            expected_output_file = shipment.replace(".pdf", ".json")
            with open(os.path.abspath(expected_output_file), "rb") as f:
                expected_output = json.load(f)
                if "ShipmentNumber" in expected_output[0]["analyzeResult"]["documentResults"][0]["fields"]:
                    expected_shipment_num = expected_output[0]["analyzeResult"]["documentResults"][0]["fields"][
                        "ShipmentNumber"]
                    actual_shipment_num = output[0]["analyzeResult"]["documentResults"][0]["fields"]["ShipmentNumber"]

                    assert actual_shipment_num == expected_shipment_num
    def test_shipment_num_v3(self):
        shipments = glob.glob("fixtures/shipment_number_v3/*.pdf")
        for shipment in shipments:
            print("Testing Shipment Invoices: ", shipment)
            output = processor.process_invoice(os.path.abspath(shipment), "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v3.1', upload_log=False,
                                               run_classification=False)
            assert output

            expected_output_file = shipment.replace(".pdf", ".json")
            with open(os.path.abspath(expected_output_file), "rb") as f:
                expected_output = json.load(f)
                if "ShipmentNumber" in expected_output[0]["analyzeResult"]["documents"][0]["fields"]:
                    expected_shipment_num = expected_output[0]["analyzeResult"]["documents"][0]["fields"][
                        "ShipmentNumber"]
                    actual_shipment_num = output[0]["analyzeResult"]["documents"][0]["fields"]["ShipmentNumber"]

                    assert actual_shipment_num == expected_shipment_num

    #Commented the test below because none of the production customers are on V3 yet
    # def test_noninvoice_v3(self):
    #     noninvoices = glob.glob("fixtures/Non Invoices Test Set/*/*.pdf")
    #     for noninvoice in noninvoices:
    #         print("Testing Non Invoice: ", noninvoice)
    #         output = processor.process_invoice(
    #             noninvoice, "fixtures", logger, log_filename, "pdf",
    #             process_always=False, version='v3.1', upload_log=False,run_classification=False
    #         )
    #         assert output
    #         assert output[0]["isInvoice"] is False

    def test_invoice_split_v3(self):
        invoices = glob.glob(r"fixtures/Multi-page-invoices v3/*.pdf")
        for invoice in invoices:
            print("Testing for Multiple Invoices: ", invoices)
            output = processor.process_invoice(invoice, "fixtures", logger, log_filename, "pdf",
                                               process_always=False, version='v3.1', upload_log=False,run_classification=False)
            assert output
            with open(invoice.replace(".pdf", ".json"), "rb") as f:
                expected_output = json.load(f)

            assert len(output) == len(expected_output)

    def test_images_v3(self):
        images = glob.glob(r"fixtures/Images/*")
        for image in images:
            print("Testing for images: ", images)
            IMAGE_ALLOWED_EXTENSIONS = ["jpeg", "jpg", "png", "bmp", "tiff", "tif"]
            extension = image.lower().split('.')[-1]
            output = None
            if extension.lower() in IMAGE_ALLOWED_EXTENSIONS:
                img = Image.open(image)
                if img.height > 350:
                    output = processor.process_invoice(image, "fixtures", logger, log_filename, extension.lower(),
                                                       process_always=False, version='v3.1', upload_log=False,run_classification=False)
            assert output is not None
            assert output[0]["isInvoice"] is True

