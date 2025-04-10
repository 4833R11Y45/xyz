import numpy as np
from src import mapping_utils

def get_items_conf_score(data,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    items_confidence_score = []
    for page in data['analyzeResult'][container_key]:
        if 'Items' in page['fields']:
            for item in page['fields']['Items']['valueArray']:
                if "confidence" in item:
                    items_confidence_score.append(item['confidence'])
    return np.mean(items_confidence_score)


def get_field_confidence(data, field_name, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    confidence_score = None
    for page in data['analyzeResult'][container_key]:
        for field in page['fields']:
            if field==field_name:
                if 'confidence' in page['fields'][field]:
                    confidence_score = page['fields'][field]['confidence']
                    break
    return confidence_score

def calc_conf_score(data,version):
    overall_conf_score = 0
    numerator = 0
    denominator = 0
    purchase_order_confidence_score = get_field_confidence(data, "PurchaseOrder",version)
    if purchase_order_confidence_score:
        numerator += 2 * purchase_order_confidence_score
        denominator += 2

    invoice_id_conf_score = get_field_confidence(data, "InvoiceId",version)
    if invoice_id_conf_score:
        numerator += 2 * invoice_id_conf_score
        denominator += 2

    invoice_date_conf_score = get_field_confidence(data, "InvoiceDate",version)
    if invoice_date_conf_score:
        numerator += invoice_date_conf_score
        denominator += 1

    due_date_conf_score = get_field_confidence(data, "DueDate",version)
    if due_date_conf_score:
        numerator += due_date_conf_score
        denominator += 1

    total_tax_conf_score = get_field_confidence(data, "TotalTax",version)
    if total_tax_conf_score:
        numerator += total_tax_conf_score
        denominator += 1

    customer_name_conf_score = get_field_confidence(data, "CustomerName",version)
    if customer_name_conf_score:
        numerator += customer_name_conf_score
        denominator += 1

    customer_addr_conf_score = get_field_confidence(data, "CustomerAddress",version)
    if customer_addr_conf_score:
        numerator += 0.5 * customer_addr_conf_score
        denominator += 0.5

    vendor_name_conf_score = get_field_confidence(data, "VendorName",version)
    if vendor_name_conf_score:
        numerator += vendor_name_conf_score
        denominator += 1

    vendor_addr_conf_score = get_field_confidence(data, "VendorAddress",version)
    if vendor_addr_conf_score:
        numerator += 0.5 * vendor_addr_conf_score
        denominator += 0.5

    avg_line_items_conf_score = get_items_conf_score(data,version)
    if avg_line_items_conf_score:
        numerator += 1.5 * avg_line_items_conf_score
        denominator += 1.5

    if denominator != 0:
        overall_conf_score = numerator / denominator
    else:
        overall_conf_score = 0
    return overall_conf_score


def check_field_existence(data, field_name,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    for page in data['analyzeResult'][container_key]:
        for field in page['fields']:
            if field==field_name:
                return True
    return False


def calc_completeness_score(data,version):
    completeness_score = 0
    numerator = 0
    denominator = 0
    purchase_order_existence = check_field_existence(data, "PurchaseOrder",version)
    if purchase_order_existence:
        numerator += 2
    denominator += 2

    invoice_id_existence = check_field_existence(data, "InvoiceId",version)
    if invoice_id_existence:
        numerator += 2
    denominator += 2

    invoice_date_existence = check_field_existence(data, "InvoiceDate",version)
    if invoice_date_existence:
        numerator += 1
    denominator += 1

    due_date_existence = check_field_existence(data, "DueDate",version)
    if due_date_existence:
        numerator += 1
    denominator += 1

    total_tax_existence = check_field_existence(data, "TotalTax",version)
    if total_tax_existence:
        numerator += 1
    denominator += 1

    customer_name_existence = check_field_existence(data, "CustomerName",version)
    if customer_name_existence:
        numerator += 1
    denominator += 1

    customer_addr_existence = check_field_existence(data, "CustomerAddress",version)
    if customer_addr_existence:
        numerator += 1
    denominator += 1

    vendor_name_existence = check_field_existence(data, "VendorName",version)
    if vendor_name_existence:
        numerator += 1
    denominator += 1

    vendor_addr_existence = check_field_existence(data, "VendorAddress",version)
    if vendor_addr_existence:
        numerator += 1
    denominator += 1

    vendor_addr_recpt_existence = check_field_existence(data, "VendorAddressRecipient",version)
    if vendor_addr_recpt_existence:
        numerator += 1
    denominator += 1

    billing_addr_existence = check_field_existence(data, "BillingAddressRecipient",version)
    if billing_addr_existence:
        numerator += 0.5
    denominator += 0.5

    billing_addr_recpt_existence = check_field_existence(data, "BillingAddressRecipient",version)
    if billing_addr_recpt_existence:
        numerator += 0.5
    denominator += 0.5

    billing_addr_recpt_existence = check_field_existence(data, "InvoiceTotal",version)
    if billing_addr_recpt_existence:
        numerator += 3
    denominator += 3

    completeness_score = numerator / denominator
    return completeness_score
