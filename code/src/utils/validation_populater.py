import re
import json
import requests
import backoff
from src import mapping_utils
from src.ner import spacy_inference
from src.utils import helper


SHIPMENT_NUM_LABEL = ['delivery docket', 'shipper number', 'delivery no']


def populate_shipment_number(azure_response, other_fields, raw_text, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)

    if "mitsubishi" in raw_text.lower():
        matched_labels = [label for label in SHIPMENT_NUM_LABEL if label in other_fields]

        if matched_labels:
            matched_delivery_label = matched_labels[0]
            delivery_number = other_fields.get(matched_delivery_label, [None])[0]

            if delivery_number and any(char.isdigit() for char in delivery_number):
                azure_response['analyzeResult'][container_key][0]['fields']["ShipmentNumber"] = {
                    "type": "string",
                    "valueString": delivery_number,
                    text_or_content: delivery_number
                }
        else:
            if "shipment" in raw_text.lower():
                # Prioritizing to check the S00 9-digit number first
                match_s00 = re.search(r'\bS00\d{6}\b', raw_text)
                if match_s00:
                    shipment_number_s00 = match_s00.group(0)
                    azure_response['analyzeResult'][container_key][0]['fields']["ShipmentNumber"] = {
                        "type": "string",
                        "valueString": shipment_number_s00,
                        text_or_content: shipment_number_s00
                    }
                else:
                    # If no "S00" pattern is found, then try matching the 6-digit number
                    match = re.search(r'(?<!\d|\b/)\b\d{6}\b(?!/\d|\d)', raw_text)
                    if match:
                        shipment_number = match.group(0)
                        azure_response['analyzeResult'][container_key][0]['fields']["ShipmentNumber"] = {
                            "type": "string",
                            "valueString": shipment_number,
                            text_or_content: shipment_number
                        }
    elif "costco" in raw_text.lower():
        if "visy" in raw_text.lower() and "packaging" in raw_text.lower():
            if "InvoiceId" in azure_response['analyzeResult'][container_key][0]['fields']:
                invoice_id = azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"]
                azure_response['analyzeResult'][container_key][0]['fields']["ShipmentNumber"] = {
                    "type": "string",
                    "valueString": invoice_id,
                    text_or_content: invoice_id
                }

    return azure_response


def populate_dc_num(azure_response, raw_text, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if 'tapal' in raw_text.lower() and 'dc no' in raw_text.lower():
        if 'Items' in azure_response['analyzeResult'][container_key][0]['fields']:
            for item in azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']:
                content = item[text_or_content]
                content_lines = content.split('\n')
                dc_no = content_lines[-1]
                item['valueObject']['ShipmentNumber'] = {
                    "type": "string",
                    "valueString": dc_no,
                    "content": dc_no
                }

    return azure_response


def populate_cost_center(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "Items" in azure_response['analyzeResult'][container_key][0]['fields']:
        line_items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']

        for item in line_items:
            item_text = item[text_or_content]
            cost_center_match = re.search(r'\b\d{4}TC\w+\b', item_text)

            if cost_center_match:
                cost_center = cost_center_match.group(0)
                item['valueObject']['CostCenter'] = {
                    "type": "string",
                    "valueString": cost_center,
                    "content": cost_center
                }

    return azure_response


def populate_total_tax(azure_response, other_fields,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if not "TotalTax" in azure_response['analyzeResult'][container_key][0]['fields']:
        for field in other_fields:
            if "gst" in field:
                gst_value = other_fields[field][0]
                updated_gst_value = gst_value.replace("$", "").replace(",", "")
                if updated_gst_value.replace('.', '').isnumeric():
                    azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"] = {}
                    azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                        text_or_content] = gst_value

                    if value_type == "valueCurrency":
                        azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                            value_type] = {"amount": updated_gst_value}
                        azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                            "type"] = "currency"
                    elif value_type == "valueNumber":
                        azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                            value_type] = updated_gst_value
                        azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                            "type"] = "number"
                    else:
                        raise KeyError(f"Unsupported value type: {value_type}")
                    break

    return azure_response


def populate_customer_add_recipient(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if 'CustomerAddressRecipient' not in azure_response['analyzeResult'][container_key][0]['fields']:
        if 'ShippingAddressRecipient' in azure_response['analyzeResult'][container_key][0]['fields']:
            azure_response['analyzeResult'][container_key][0]['fields']['CustomerAddressRecipient'] = \
            azure_response['analyzeResult'][container_key][0]['fields']['ShippingAddressRecipient']
    return azure_response


def populate_invoice_total_from_items(azure_response):
    if "Items" in azure_response['analyzeResult']['documentResults'][0]['fields']:
        item_array = azure_response['analyzeResult']['documentResults'][0]['fields']['Items']['valueArray']

        if len(item_array) == 1 and "valueObject" in item_array[0]:
            value_object = item_array[0]["valueObject"]
            if "UnitPrice" in value_object and "valueNumber" in value_object["UnitPrice"]:
                unit_price_value = value_object["UnitPrice"]["valueNumber"]

                if "InvoiceTotal" in azure_response['analyzeResult']['documentResults'][0]['fields']:
                    try:
                        invoice_total_value = \
                            azure_response['analyzeResult']['documentResults'][0]['fields']["InvoiceTotal"][
                                "valueNumber"]

                        if abs(unit_price_value) > 50 * abs(invoice_total_value):
                            print(f"Unreasonably high unit price detected: {unit_price_value}, skipping")
                        elif abs(invoice_total_value) < abs(unit_price_value):
                            try:
                                azure_response['analyzeResult']['documentResults'][0]['fields']["InvoiceTotal"] = {
                                    "type": "number",
                                    "text": str(unit_price_value),
                                    "valueNumber": unit_price_value
                                }
                                print(f"Total Invoice: {unit_price_value}")
                            except ValueError:
                                pass
                    except KeyError:
                        azure_response['analyzeResult']['documentResults'][0]['fields']["InvoiceTotal"] = {
                            "type": "number",
                            "text": str(0),
                            "valueNumber": 0
                        }
    return azure_response


def populate_contract_num(azure_response, raw_text, other_fields, version):
    """
        Populating the contract ID from regex pattern incase if it is not predicted by the model but present in the invoice.
        """
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    contract_num = spacy_inference.predict_contract_num(raw_text)
    if "palm trace lic" in other_fields:
        license_num = other_fields["palm trace lic"][0]
        if contract_num == license_num:
            contract_num = None
    if "acct" in other_fields:
        acct_num = other_fields["acct"][0]
        if contract_num == acct_num:
            contract_num = None
    if "contract number" in other_fields and contract_num is None:
        contract_num = other_fields["contract number"][0].upper()
    if "contract no ." in other_fields  and contract_num is None:
        contract_num = other_fields["contract no ."][0].upper()

    def is_valid_contract_num(contract_num):
        # To remove contract numbers that are not digits or do not start with C
        if contract_num.isdigit() or contract_num.startswith("C") or contract_num.startswith("LC"):
            return True
        return False

    def is_contract_num_in_line_items(azure_response, contract_num):
        # Function to check if the predicted contract number lies in the line items
        if "Items" in azure_response['analyzeResult'][container_key][0]['fields']:
            line_items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
            for item in line_items:
                item_text = item[text_or_content]
                if contract_num in item_text:
                    return True
        return False

    def is_contract_num_invoice_id(azure_response, contract_num):
        # Function to check if the contract number is the same as the invoice ID
        invoice_id = azure_response['analyzeResult'][container_key][0]['fields'].get("InvoiceId", {}).get("valueString",
                                                                                                          "")
        return contract_num == invoice_id

    def is_contract_num_purchase_order(azure_response):
        # Function to check if the purchase order is present in response
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
            po_num = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
            if po_num:
                return True
        return False

    if contract_num and helper.is_not_float_string(contract_num) and is_valid_contract_num(contract_num) and contract_num!="CW":
        # if not is_contract_num_in_line_items(azure_response, contract_num) and not is_contract_num_invoice_id(azure_response, contract_num) and not is_contract_num_purchase_order(azure_response):
        if not is_contract_num_invoice_id(azure_response, contract_num) and not is_contract_num_purchase_order(
                azure_response):
            azure_response['analyzeResult'][container_key][0]['fields']["ContractId"] = {
              "type": "string",
              "valueString": contract_num,
              text_or_content: contract_num}
    else:
        contract_pattern = re.compile(r'\bL*CW\s*#*\s*\d+\b')
        matches = contract_pattern.findall(raw_text)
        if matches:

            azure_response['analyzeResult'][container_key][0]['fields']["ContractId"] = {
                "type": "string",
                "valueString": matches[0],
                text_or_content: matches[0]
            }
            print("Contract ID:", matches[0])
        else:
            print("Contract ID not found in the raw text.")
    return azure_response


def populate_account_number(azure_response, other_fields, raw_text, version):
    # Get structure details based on version
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    vendor_list = ["agl", "origin", "telstra", "energy intelligence", "energy australia"]
    raw_text_lower = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_text.replace("\n", " ")).lower()
    # Check if any vendor from vendor_list and 'mitsubishi' are both present
    vendor_found = any(vendor in raw_text_lower for vendor in vendor_list)
    mitsubishi_found = 'mitsubishi' in raw_text_lower
    # Only proceed if both a vendor name AND 'mitsubishi' are found in the raw text
    if vendor_found and mitsubishi_found:
        print("Both vendor and 'mitsubishi' found, proceeding with account number extraction...")
        account_num = spacy_inference.predict_account_num(raw_text)
        if account_num:
            if "/" in account_num:
                account_num = account_num.replace(" ", "").split("/")[0][:10]
            account_num = account_num.replace(" ", "").replace("Tax", "").replace("Supply1", "")
        other_account_num = None
        if "account number" in other_fields:
            other_account_num = other_fields["account number"][0].replace(" ", "")
        if account_num and other_account_num:
            if len(other_account_num) > len(account_num) and account_num in other_account_num:
                account_num = other_account_num
        elif other_account_num:
            account_num = other_account_num
        # Check if account number matches an ABN, skip if they match
        if "BankDetails" in azure_response['analyzeResult'][container_key][0]['fields']:
            if "ABN" in azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]:
                ABNs = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]["ABN"]
                for abn in ABNs:
                    if account_num == abn and len(account_num) == 11:
                        print("Account number matches ABN, skipping.")
                        account_num = None
                        break

        if not account_num:
            match = re.search(r'(\d{4}\s\d{3}\s\d{3})', raw_text)
            if match:
                account_num = match.group(0).replace(" ", "")

        if account_num and len(account_num) > 5:
            azure_response['analyzeResult'][container_key][0]['fields']["CustomerAccountNumber"] = {
                "type": "string",
                "valueString": account_num,
                text_or_content: account_num
            }

        print("Account Number:", account_num)

    else:
        # Exit early if both vendor and mitsubishi are not found
        print("Either vendor or 'mitsubishi' not found, skipping account number extraction.")

    return azure_response


def populate_billing_info(azure_response,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if not "BillingAddress" in azure_response['analyzeResult'][container_key][0]['fields']:
        if "VendorAddress" in azure_response['analyzeResult'][container_key][0]['fields']:
            azure_response['analyzeResult'][container_key][0]['fields']["BillingAddress"] = \
                azure_response['analyzeResult'][container_key][0]['fields']["VendorAddress"]

    if not "BillingAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']:
        if "VendorAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']:
            vendor_address_recipient = azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"][text_or_content]
            if vendor_address_recipient != "Ltd":
                azure_response['analyzeResult'][container_key][0]['fields']["BillingAddressRecipient"] = \
                azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"]
            else:
                if "AccountName" in azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]:
                    account_name = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]["AccountName"]
                    if account_name:
                        azure_response['analyzeResult'][container_key][0]['fields']["BillingAddressRecipient"] = {
                            text_or_content: account_name[0],
                            "type": "string",
                            "valueString": account_name[0] }

    return azure_response


@backoff.on_exception(backoff.expo, Exception, max_retries=3)
def get_unspsc_response(items_list):
    unspsc_response = requests.post("http://classification.spendconsole.ai:8000/predict",
                                    data=json.dumps({"items": items_list}),
                                    headers={'Content-Type': 'application/json'})
    return unspsc_response


def populate_unspsc_code(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    items_list = []
    if 'Items' in azure_response['analyzeResult'][container_key][0]['fields']:
        for item in azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']:
            if item and "valueObject" in item:
                if "Description" in item["valueObject"]:
                    items_list.append(item["valueObject"]["Description"][text_or_content])
                else:
                    items_list.append("")
            else:
                items_list.append("")

        try:
            unspsc_response = requests.post("http://classification.spendconsole.ai:8000/predict", data=json.dumps({"items":items_list}), headers={'Content-Type': 'application/json'})
            if unspsc_response.status_code == 200:
                results = unspsc_response.json()["results"]
                for i, item in enumerate(azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']):
                    if item and "valueObject" in item:
                        if "Description" in item["valueObject"]:
                            item["valueObject"]["Description"]["unspscCategory"] = results[i]["category"]
                            item["valueObject"]["Description"]["unspscCategoryCode"] = results[i]["category_code"]
        except requests.ConnectionError:
            for i, item in enumerate(
                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']):
                if item and "valueObject" in item:
                    if "Description" in item["valueObject"]:
                        item["valueObject"]["Description"]["unspscCategory"] = ""
                        item["valueObject"]["Description"]["unspscCategoryCode"] = ""

    return azure_response


def populate_contact_person(azure_response, version, other_fields):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "attn" in other_fields:
        azure_response['analyzeResult'][container_key][0]['fields']["CustomerBusinessContact"] = other_fields["attn"]
    elif "att" in other_fields:
        azure_response['analyzeResult'][container_key][0]['fields']["CustomerBusinessContact"] = other_fields["att"]
    return azure_response
