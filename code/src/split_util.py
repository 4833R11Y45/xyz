from src import mapping_utils

def normalize_invoice_id(inv_id):
    # Normalizing the invoice ID by converting it to uppercase
    # and replacing common OCR mistakes, e.g., 'O' (letter) with '0' (number).
    if inv_id:
        inv_id = inv_id.upper()
        inv_id = inv_id.upper().replace('O', '0').replace('B', '8').replace('D', '0')
        inv_id = ''.join(inv_id.split())
    return inv_id

def find_splits(responses_array, raw_text_array, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    split_points = []
    first_inv_id = ""
    invoice_id_list = []
    invoice_bool_list = []
    supplier_name_list = []
    is_credit_note = []

    # Initialize the flag to track if any response has CustomerAccountNumber
    contains_customer_account = False

    # First loop to gather information and check for CustomerAccountNumber
    for n, response in enumerate(responses_array):
        invoice_id_found = False
        is_credit_note.append(response['isCreditNote'])
        is_invoice = response['isInvoice']

        for field in response['analyzeResult'][container_key][0]['fields']:
            if field == "InvoiceId":
                invoice_id_field = response['analyzeResult'][container_key][0]['fields']["InvoiceId"]
                if text_or_content in invoice_id_field:
                    inv_id_val = normalize_invoice_id(response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content])
                    if is_invoice:
                        invoice_id_list.append(inv_id_val)
                        invoice_bool_list.append(not response['nonInvoice'])
                        invoice_id_found = True
                    else:
                        invoice_id_found = False
                else:
                    print(f"Skipping InvoiceId as key '{text_or_content}' not found.")

            if field == "VendorName":
                supplier_name_val = response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
                supplier_name_list.append(supplier_name_val)

            if field == "CustomerAccountNumber":
                contains_customer_account = True

        if not invoice_id_found:
            invoice_id_list.append(None)
            invoice_bool_list.append(False)

        if "VendorName" not in response['analyzeResult'][container_key][0]['fields']:
            supplier_name_list.append(None)

    print(invoice_bool_list)
    print(invoice_id_list)

    # Send single split if "CustomerAccountNumber" found
    if contains_customer_account:
        print("Utility invoice detected. Treating as a single invoice.")
        split_points = []
        return split_points
    # If no "CustomerAccountNumber" is found, proceed to find splits
    for n, (inv_id, supplier_name) in enumerate(zip(invoice_id_list, supplier_name_list)):
        if inv_id is not None:
            if n == 0 or not first_inv_id:  # Ensure first_inv_id is set at the start
                first_inv_id = inv_id
            else:
                if inv_id != first_inv_id:
                    if len(inv_id) == len(first_inv_id) and inv_id[:2] == first_inv_id[:2]:
                        split_points.append(n)
                        first_inv_id = inv_id
                        continue
                    elif "groupm" in supplier_name_list and any(name != "groupm" for name in supplier_name_list):
                        # Checking for groupm in supplier name list along with other suppliers
                        split_points.append(n)
                        first_inv_id = inv_id
                        continue
                    elif is_credit_note[n] and not is_credit_note[n - 1]:
                        split_points.append(n)

    # if len(responses_array) > 1 and responses_array[1]['nonInvoice']:
    #     split_points.append(1)

    # This block of code will split any non-invoice also checking for credit notes present between invoices
    # for idx, is_invoice in enumerate(invoice_bool_list):
    #     if not is_invoice:
    #         if idx > 0 and is_credit_note[idx - 1]:
    #             split_points.append(idx)  # Separate preceding credit note from non-invoice
    #         elif idx < len(invoice_bool_list) - 1 and is_credit_note[idx + 1]:
    #             split_points.append(idx + 1)  # Separate following credit note from non-invoice
    #         split_points.append(idx)

    # Have to re-add this back as many invoices last page was not splitting
    if split_points:# and (responses_array[-1]['isInvoice'] is True):
        split_points.append(len(responses_array))

    return sorted(set(split_points))
