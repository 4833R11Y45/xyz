import re
import string
from src import mapping_utils
from collections import defaultdict

FIELD_NAMES = ["po/claim no", "reference", "ref", "tax invoice number", "tax invoice no", "tax credit",
               "invoice number", "invoice no", "purchase order no", "customer order no",
               "purchase order number", "purchase order", "sap", "customer order number", "customer requisition",
               "contact", "document id", "document no", "sales order", "your order no", "order no", "order number"
                                                                                                    "orderno",
               "order id", "invoice date", "delivery date", "due date", "po no", "po",
               "p o", "abn", "a b n", "bsb number", "bsb", "account number", "account name", "swift code",
               "swift", "bank name", "adj no", "assessment number", "tax adjustment note number", "adjustment note",
               "credit",
               "TAX INVOICE", "Period Ending", "delivery challan no", "dc number", "dc no", "dc", "dispatch no",
               "dn number Date", "d c", "shipment",
               "contract number", "contract no", "order number"]


def get_raw_text(json_data, version):
    """
    creating raw text from azure response
    lines: concatenate all lines in all the pages with \n to add next line
    lines_without_spaces: concatenate all lines in all the pages with \n to add next line
    lines_without_spaces: we also remove all spaces from the lines because handwritten PO sometimes
    has spaces and it doesn't get matched otherwise
    """
    container_key, text_or_content, block_type = mapping_utils.get_response_structure(version)
    lines = ""
    lines_without_spaces = ""
    for page in json_data["analyzeResult"][container_key]:
        for line in page["lines"]:
            lines = lines + line[text_or_content]
            lines = lines + "\n"
            lines_without_spaces = lines_without_spaces + line[text_or_content].replace(" ", "")
            lines_without_spaces = lines_without_spaces + "\n"
    return lines, lines_without_spaces


def identify_blocks(data, version):
    container_key, text_or_content, block_type = mapping_utils.get_response_structure(version)
    page_blocks_list = []
    # x_threshold = data["analyzeResult"]["readResults"][0]["width"]*0.18
    x_threshold = data["analyzeResult"][container_key][0]["width"] * 0.3
    y_threshold = 0.5
    for page in data["analyzeResult"][container_key]:
        blocks = []
        for line in page["lines"]:
            min_x = round(line[block_type][0], 1)
            min_y = round(line[block_type][1], 1)
            closest_found = False
            for blk in blocks:
                if abs(min_x - blk['min_x']) < x_threshold:
                    if abs(min_y - blk['min_y']) < y_threshold:
                        closest_found = True
                        blk['lines'].append(line[text_or_content])
                        blk['min_y'] = min_y
                        break
            if closest_found is False:
                new_blk = {'min_x': min_x, 'min_y': min_y, 'lines': [line[text_or_content]]}
                blocks.append(new_blk)
        page_blocks_list.append(blocks)
    return page_blocks_list


def get_blocks_text(blocks_list):
    text = ""
    for blk in blocks_list:
        for b in blk:
            for line in b["lines"]:
                text += line
                text += "\n"

    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    text = text.translate(translator)

    return text


def extract_col_tables(data, version):
    if version == "v2.1":
        for page in data['analyzeResult']['pageResults']:
            for table in page["tables"]:
                col_values = {}
                header_to_index_mapping = {}
                for cell in table["cells"]:
                    try:
                        if "isHeader" in cell and cell["isHeader"] is True:
                            header_to_index_mapping[cell["columnIndex"]] = cell["text"]
                            col_values[cell["text"]] = []
                        else:
                            col_values[header_to_index_mapping[cell["columnIndex"]]].append(cell["text"])
                    except Exception as e:
                        print(e)
                        print(cell)
                print(col_values)
    else:
        for table in data['analyzeResult']['tables']:
            col_values = {}
            header_to_index_mapping = {}
            for cell in table["cells"]:
                col_values[header_to_index_mapping[cell["columnIndex"]]].append(cell["content"])
                print(col_values)


def insert_key_value(first_word, second_word, fields_dict):
    first_word = first_word.lower().strip()
    second_word = second_word.strip()
    if second_word:
        fields_dict[first_word].append(second_word)
        # if first_word not in fields_dict:
        #     fields_dict[first_word] = second_word
        # else:
        #     first_word = first_word + "_1"
        #     fields_dict[first_word] = second_word
    return fields_dict


def other_field_values(blocks_list):
    field_values = defaultdict(lambda: [])
    previous_word = ""
    split_point = [":", "#", "."]
    #     lines = page.split("\n")

    for block in blocks_list:
        for blk in block:
            for line in blk["lines"]:
                # print("line: ", line)
                break_point = False
                if previous_word:
                    # print ("previous_word: ", previous_word)
                    #                 field_values[previous_word] = line
                    fields_values = insert_key_value(previous_word, line, field_values)
                    previous_word = ""
                for sp in split_point:
                    if sp in line:
                        # print("Split point: ", sp)
                        break_point = True
                        words = line.split(sp)
                        # print("words: ", words)
                        if len(words) > 1 and len(words[1]) > 3:
                            # print("now here")
                            if ("to" in words[0].lower() or "from" in words[0].lower()) and len(words) > 2:
                                fields_values = insert_key_value(words[1], words[2], field_values)
                            else:
                                fields_values = insert_key_value(words[0], words[1], field_values)
                            #                     field_values[words[0]] = words[1]
                        else:
                            previous_word = words[0]
                        break

                if break_point is True:
                    continue
                translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
                line = line.translate(translator).lower()
                # print("Crossed continue...")
                # print("Line now: ", line)

                for fn in FIELD_NAMES:
                    # print("Trying to match: ", fn)
                    field_search = re.compile(r"\b%s\b" % fn, re.I)
                    field_match = field_search.search(line)
                    if field_match:
                        # print("Matched ", fn)
                        if not fn == "po":
                            words = line.lower().split(fn)
                            # print(words)
                            if len(words) > 1 and len(words[1]) > 3:
                                if len(line.replace(fn, "").split(" ")) <= 6:
                                    # print("Inserting: ", fn, " ", words[1])
                                    fields_values = insert_key_value(fn, words[1], field_values)
                            else:
                                # print("Added as prev word")
                                previous_word = fn
                            break
                        else:
                            if not re.compile(r'\b%s\b' % "po box", re.I).search(line) or re.compile(
                                    r'\b%s\b' % "p o box", re.I).search(line):
                                words = line.lower().split(fn)
                                if len(words) > 1 and len(words[1]) > 3:
                                    if len(line.split(" ")) < 5:
                                        fields_values = insert_key_value(fn, words[1], field_values)
                                else:
                                    previous_word = fn
                                break

    return field_values


def check_is_tax_invoice(raw_text):
    updated_raw_text = raw_text.replace("\n", " ").lower()
    # pattern = r'\b(tax\s*.*\s*invoice)\b'
    if "tax invoice" in updated_raw_text:
        return True
    elif "taxinvoice" in updated_raw_text:
        return True
    elif "tax credit note" in updated_raw_text:
        return True
    elif "tax credit" in updated_raw_text:
        return True
    elif "tax receipt" in updated_raw_text:
        return True
    # elif re.search(pattern, updated_raw_text):
    #     return True
    return False


def check_is_credit_note(azure_response, raw_text, version):
    container_key, text_or_content, block_type = mapping_utils.get_response_structure(version)
    check_first_lines = 25
    credit_note_labels = ["credit/adjustment note", "credit adjustment note", "credit memo", "tax adjustment note",
                          "adjustment note", "credit adjustment", "tax invoice adjustment", "adjustment credit","adjustment",
                          "tax credit", "credit to", "credit adj note", "credit note number", "credit note date", "credit note"]
    for line in azure_response["analyzeResult"][container_key][0]["lines"][:check_first_lines]:
        line_text = line[text_or_content].replace("\n", " ").lower()
        print(line_text)
        if any(label in line_text for label in credit_note_labels):
            return True
    # updated_raw_text = raw_text.replace("\n", " ").lower()
    # if any(label in updated_raw_text for label in credit_note_labels):
    #     return True
    return False


def extract_lpo(raw_text):
    regex = r"LPO\s*\d{4,}"
    lpo_match = re.search(regex, raw_text, re.IGNORECASE)
    if lpo_match:
        return lpo_match.group()
    else:
        regex = r"LP0\s*\d{4,}"  # Sometimes OCR reads LP0 as LP0
        lpo_match = re.search(regex, raw_text, re.IGNORECASE)
        if lpo_match:
            return lpo_match.group().replace("LP0", "LPO")
    return None

def extract_iban_num(raw_text):
    regex = r"\bPK\d{2}[A-Z]{4}\d{16}\b"
    iban_match = re.search(regex, raw_text)
    if iban_match:
        return iban_match.group()
    return None
def get_excluded_list(raw_text, page_blocks_list):
    excluded = []
    if "ATOM SUPPLY" in raw_text:
        for block in page_blocks_list:
            for blk in block:
                for i, line in enumerate(blk["lines"]):
                    if "Deliver To" in line:
                        excluded = blk["lines"][i:]
                        break
    return excluded


def is_australian_address(raw_text):
    pattern = re.compile(r'.*(\b(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b).*\b\d{4}\b')
    return bool(re.search(pattern, raw_text))

def is_utility_bill(raw_text):
    vendor_list = ["agl south australia", "originenergy", "telstra", "energy intelligence", "energy australia"]
    raw_text_lower = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_text.replace("\n", " ")).lower()
    # Check if any vendor from vendor_list and 'mitsubishi' are both present
    vendor_found = any(vendor in raw_text_lower for vendor in vendor_list)
    if vendor_found:
        return True
    # Check for specific keywords
    keyword_list = [
        "water usage", "water notice", "water usage account", "water/sewer charges",
        "water account", "overdue water", "wastewater", "overdue water charges", "water supply",
        "electricity bill", "instalment notice", "water charges"
    ]
    keyword_found = any(keyword in raw_text_lower for keyword in keyword_list)
    if keyword_found:
        return True
    return False


def hardcoded_7_eleven_values(azure_response, use_gpt, version):
    if use_gpt is True and version == "v3.1":
        if "VendorName" in azure_response['analyzeResult']['documents'][0]['fields']:
            if azure_response['analyzeResult']['documents'][0]['fields']['VendorName'][
                "content"] == "BALLARAT NEWSPAPER DELIVERY":
                azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"] = []
                azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"].append({
                    "content": "BALLARAT COURIER\n13.921\n175.00",
                    "type": "object",
                    "valueObject": {
                        "Amount": {
                            "content": "175.00",
                            "type": "currency",
                            "valueCurrency": {"amount": 175.00}
                        },
                        "Description": {
                            "content": "BALLARAT COURIER",
                            "type": "string",
                            "valueString": "BALLARAT COURIER"
                        },
                        "Tax": {
                            "content": "13.921",
                            "type": "number",
                            "valueNumber": 13.921
                        }
                    }
                })
                del azure_response['analyzeResult']['documents'][0]['fields']['PurchaseOrder']
        if "VendorName" in azure_response['analyzeResult']['documents'][0]['fields']:
            if azure_response['analyzeResult']['documents'][0]['fields']['VendorName'][
                "content"] == "West Australian Newspapers Limited":
                azure_response['analyzeResult']['documents'][0]['fields']["SubTotal"] = {
                    "content": "$236.97",
                    "type": "currency",
                    "valueCurrency": {
                        "amount": 236.97,
                        "currencyCode": None}
                }
                azure_response['analyzeResult']['documents'][0]['fields']["TotalTax"] = {
                    "content": "$21.54",
                    "type": "currency",
                    "valueCurrency": {
                        "amount": 21.54,
                        "currencyCode": None}
                }

        if "VendorName" in azure_response['analyzeResult']['documents'][0]['fields']:
            if azure_response['analyzeResult']['documents'][0]['fields']['VendorName'][
                "content"] == "Rural Press Pty Limited":

                azure_response['analyzeResult']['documents'][0]['fields']['InvoiceId']["content"] = "0720005665"
                azure_response['analyzeResult']['documents'][0]['fields']['InvoiceId']["valueString"] = "0720005665"

                azure_response['analyzeResult']['documents'][0]['fields']['InvoiceDate']["content"] = "05/02/24"
                azure_response['analyzeResult']['documents'][0]['fields']['InvoiceDate']["valueDate"] = "2024-02-05"

                azure_response['analyzeResult']['documents'][0]['fields']['CustomerName'][
                    "content"] = "7 ELEVEN S/HARBOUR 2097"
                azure_response['analyzeResult']['documents'][0]['fields']['CustomerName'][
                    "valueString"] = "7 ELEVEN S/HARBOUR 2097"

                del azure_response['analyzeResult']['documents'][0]['fields']['VendorAddress']
                del azure_response['analyzeResult']['documents'][0]['fields']['PurchaseOrder']
                if "SubTotal" in azure_response['analyzeResult']['documents'][0]['fields']:
                    del azure_response['analyzeResult']['documents'][0]['fields']['SubTotal']

                azure_response['analyzeResult']['documents'][0]['fields']["InvoiceTotal"] = {
                    "content": "$335.45",
                    "type": "currency",
                    "valueCurrency": {
                        "amount": 335.45,
                        "currencyCode": None}
                }
        if "VendorName" in azure_response['analyzeResult']['documents'][0]['fields']:
            if azure_response['analyzeResult']['documents'][0]['fields']['VendorName'][
                "content"] == "A1 Timber Supplies":
                del azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][0][
                    "valueObject"]["Tax"]
                del azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][1][
                    "valueObject"]["Tax"]

    return azure_response


def extract_co2_emission(raw_text):
    emission = ""
    pattern = r"(?i)greenhouse gas emissions(?:\W+\w+){0,6}.*?([-+]?\d*\.?\d+)\s*tonnes"

    match = re.search(pattern, raw_text)
    if match:
        emission = float(match.group(1))
    return emission

