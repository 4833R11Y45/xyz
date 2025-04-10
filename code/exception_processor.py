import json
import time
import concurrent.futures

from src.utils import azure_utils
from src.generativeai import user_action_automation
from src import db_utils


EXCEPTION_FIELD_MAPPING = {'Invoice.General.Tax': 'Tax',
                            'Invoice.NonZero.Amount': 'Items',
                            'Invoice.NonZero.Quantity': 'Items',
                            'Invoice.NonZero.UnitPrice': 'Items',
                            'Invoice.PO.PurchaseOrder': 'PurchaseOrder',
                            'Invoice.PO.PurchaseOrder.DueDate': 'DueDate',
                            'Invoice.PO.PurchaseOrder.Inactive': 'PurchaseOrder',
                            'Invoice.PO.PurchaseOrder.InvoiceDate': 'InvoiceDate',
                            'Invoice.PO.PurchaseOrder.InvoiceExceedAmount': 'OriginalInvoiceTotal',
                            'Invoice.PO.PurchaseOrder.Regex': 'PurchaseOrder',
                            'Invoice.PO.PurchaseOrder.RemainingAmount': 'PurchaseOrder',
                            'Invoice.PO.PurchaseOrder.Supplier': 'PurchaseOrder',
                            'Invoice.PO.PurchaseOrder.UnitPriceTolerance': 'Items',
                            'Invoice.PO.PurchaseOrderNumber': 'PurchaseOrder',
                            'Invoice.PurchaseOrder.LineItemQtyToPoQty': 'OriginalInvoiceTotal',
                            'Invoice.Required.AllowanceCharge': 'Items',
                            'Invoice.Required.Amount': 'Items',
                            'Invoice.Required.BillingAddress': 'BillingAddress',
                            'Invoice.Required.BullingAddressRecipient': 'BullingAddressRecipient',
                            'Invoice.Required.CustomerAbn': 'CustomerAbn',
                            'Invoice.Required.CustomerAddress': 'CustomerAddress',
                            'Invoice.Required.CustomerName': 'CustomerName',
                            'Invoice.Required.Description': 'Items',
                            'Invoice.Required.DueDate': 'DueDate',
                            'Invoice.Required.GlCode': 'Items',
                            'Invoice.Required.InvoiceDate': 'InvoiceDate',
                            'Invoice.Required.InvoiceNumber': 'InvoiceNumber',
                            'Invoice.Required.OriginalOriginalInvoiceTotal': 'OriginalInvoiceTotal',
                            'Invoice.Required.PurchaseOrder': 'PurchaseOrder',
                            'Invoice.Required.Quantity': 'Items',
                            'Invoice.Required.RemittanceAddress': 'RemittanceAddress',
                            'Invoice.Required.RemittanceAddressRecipient': 'RemittanceAddressRecipient',
                            'Invoice.Required.RequesterEmail': 'RequesterEmail',
                            'Invoice.Required.SubTotal': 'SubTotal',
                            'Invoice.Required.SupplierAbn': 'SupplierAbn',
                            'Invoice.Required.SupplierAddress': 'VendorAddress',
                            'Invoice.Required.SupplierCity': 'VendorAddress',
                            'Invoice.Required.SupplierCountry': 'VendorAddress',
                            'Invoice.Required.SupplierName': 'VendorName',
                            'Invoice.Required.SupplierPostCode': 'VendorAddress',
                            'Invoice.Required.SupplierState': 'VendorAddress',
                            'Invoice.Required.TaxCategory': 'Items',
                            'Invoice.Required.TaxDescription': 'Items',
                            'Invoice.Required.Total': 'OriginalInvoiceTotal',
                            'Invoice.Required.Unit': 'Items',
                            'Invoice.Required.UnitPrice': 'Items',
                            'Invoice.Supplier': 'VendorName',
                            'Invoice.Supplier.ABN': 'SupplierAbn',
                            'Invoice.Supplier.Name': 'VendorName',
                            'Invoice.Calculated.OriginalToCalculated': 'OriginalInvoiceTotal',
                            'Invoice.General.NoLineItems': 'Items'}
ITEMS_RELATED_FIELDS = ['OriginalInvoiceTotal', 'Tax', 'SubTotal']

DB_CONNECTION = db_utils.connect_db()

def process_exceptions(invoice_id, exceptions):
    actions = []

    start_time = time.time()
    relevant_fields = [EXCEPTION_FIELD_MAPPING[exception['id']] for exception in exceptions if exception['id'] in EXCEPTION_FIELD_MAPPING ]
    relevant_fields = list(set(relevant_fields))
    if any(field in ITEMS_RELATED_FIELDS for field in relevant_fields) and "Items" not in relevant_fields:
        relevant_fields.append("Items")
    print("Relevant fields: ", relevant_fields)
    relevant_fields_data = db_utils.get_processed_invoice_data(invoice_id, relevant_fields, DB_CONNECTION)
    print("Relevant fields data: ", relevant_fields_data)
    print("Time taken to get invoice data from db: ", time.time()-start_time)

    azure_start_time = time.time()
    invoice_num, ocr_text = azure_utils.get_invoice_json_from_azure_storage(
        relevant_fields_data['AnalyzeResultFileName'].split('.')[0] + '.json')  # form recognizer ocr text
    print("Relevant fields data: ", relevant_fields_data)
    print("Time taken to get invoice data from azure: ", time.time()-azure_start_time)

    exception_resolution_start_time = time.time()
    exception_data = []
    for exception in exceptions:
        exception_relevant_data = {}
        if exception['id'] in EXCEPTION_FIELD_MAPPING:
            field = EXCEPTION_FIELD_MAPPING[exception['id']]
            exception_relevant_data[field] = relevant_fields_data[field]
        exception_data.append((exception["id"], exception["description"], ocr_text, exception_relevant_data))
    print("Exception data: ", exception_data)
    # exception_data = [(exception.get("id"), exception.get("description"), ocr_text, extracted_values) for exception in
    #                   exceptions]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        print("HEREEE")
        actions = list(executor.map(resolve_exceptions, exception_data))
    # for exception in exceptions:
    #     print("Exception: ", exception)
    #     exception_resolution_start_time_itr = time.time()
    #     exception_id = exception.get("id")
    #     exception_content = exception.get("description")
    #     action = resolve_exceptions(exception_id, exception_content, ocr_text, extracted_values)
    #     actions.append(action)
    #     print(f"Resolved exceptions for exception ID {exception_id}")
    #     print("Time taken to resolve exception: ", time.time() - exception_resolution_start_time_itr)
    print("Total Time taken to resolve all exceptions: ", time.time() - exception_resolution_start_time)
    print("********Exception resolution action: ", actions)

    return actions

# def resolve_exceptions(exception_id, exception_content, ocr_text, extracted_values):
def resolve_exceptions(exception_data):
    print("ALSO HERE")
    exception_id, exception_content, ocr_text, extracted_values = exception_data
    # print("Exception: ", exception_content)
    if extracted_values:
        result = user_action_automation.llm_response(ocr_text, exception_content, extracted_values)

        # print("LLM response: ", result)
        # print("*"*10)

        json_response = json.loads(result)

        response = {
            "id": exception_id,
            "description": json_response['Description for resolved exceptions'],
            "oldValue": json_response["Previous Values"],
            "newValue": json_response['Updated Values'],
            "Errors Encountered": json_response['Errors Encountered'],
            "valueType": json_response['Value Type'],
            "changeType": json_response['Change Type']
        }

        if isinstance(response["Errors Encountered"], str):
            print ()
            if not response["Errors Encountered"] == "None" and response["Errors Encountered"]:
                response["Errors Encountered"] = [response["Errors Encountered"]]
            else:
                response["Errors Encountered"] = []
    else:
        response = {
            "id": exception_id,
            "description": "None",
            "oldValue": "None",
            "newValue": "None",
            "Errors Encountered": ["We don't deal with this kind of exception at the moment"],
            "valueType": "Invalid",
            "changeType": "None"
        }

        print ("**Response: ", response)

    if isinstance(response["Errors Encountered"], str):
        if not response["Errors Encountered"] == "None" and response["Errors Encountered"]:
            response["Errors Encountered"] = [response["Errors Encountered"]]
        else:
            response["Errors Encountered"] = []
    # except Exception as e:
    #     print(e)

    return response