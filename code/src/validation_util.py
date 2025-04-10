import os
import datetime
import re
from src import mapping_utils, font_size_estimation
from src.ner import spacy_inference
from src.utils import validation_populater
from datetime import datetime
from dateutil.parser import parse
from collections import defaultdict

log_folder = "logs"
log_filename = os.path.join(log_folder, "sc_app.log")
# log_writer = open(log_filename, 'a', encoding='utf-8')
# sys.stdout = log_writer

MANDATORY_FIELDS = ["PurchaseOrder", "ABN"]
NOT_AN_INVOICE_LABELS = [["gb electrical contractors pty ltd", "gas maintenance sheet", "equipment details",
                          "inspection details"],
                         ["timesheet", "week ending sunday", "minutes", "monday", "tuesday", "wednesday", "thursday",
                          "friday","consultant"],
                         ["order form – support services"],
                         ["statement of certification", "certification"], ["safe handl", "this product was prepar"],
                         ['copy of legal services order'],
                         ['company statement'], ['delivery docket','job','order'], ['financial terms'],
                         ['delivery docket','material'],
                         ['timesheet','day','night','time on', 'time off'],
                         ['timesheet','start work','finish work'],
                         ['timesheet','actual hours','start','finish','day worked'],
                         ['rental agreement','rental','return address','return hours'],
                         ['statement of hazardous nature','emergency overview'],
                         ['timesheet','start', 'finish','total hrs'],
                         ['delivery challan'],
                         ['timesheet','dayshift','nightshift'],
                         ['transmission certificate'],
                         ['service report', 'work order number', 'job complete'],
                         ['guest folio','name','room'],
                         ['terms and conditions for purchase orders'],
                         ['debit note'],
                         ['quotation', 'repair advice form', 'description of components to be repaired'],
                         ['email cover sheet', 'email address'],
                         ['statement of account','std terms', 'dsb terms'],
                         ['agency agreement', "between", "pact"],
                         ['order confirmation', 'order no', 'order date', 'order line']]

CREDIT_NOTE_NUM_LABELS = ['tax adjustment note number', 'credit no', 'credit note no','adjustment number','tax credit','adjustment note','credit memo', 'invoice number','invoice no','tax invoice number', 'credit note']


def get_missing_fields(json_data,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    fields_found = {}
    for page in json_data['analyzeResult'][container_key]:
        #     print(page['fields'].keys())
        for field in page['fields']:
            if field in MANDATORY_FIELDS:
                fields_found[field] = page['fields'][field][text_or_content]

    missing_fields = [field for field in MANDATORY_FIELDS if field not in fields_found]

    return missing_fields


def get_invoice_num_index(text):
    invoice_num_synonyms = ["tax invoice number", "tax invoice no", "invoice number", "invoice no", "document id",
                            "document no"]
    for syn in invoice_num_synonyms:
        try:
            index = text.lower().index(syn)
            # print(syn)
            return index
        except ValueError:
            pass
    return -1


def get_purchase_order_index(text):
    po_synonyms = ["purchase order", "po", "order id", "reference", "ref"]
    for syn in po_synonyms:
        try:
            index = text.lower().index(syn)
            # print(syn)
            return index
        except ValueError:
            pass
    return -1


def get_dates_index(text):
    invoice_date_index = -1
    due_date_index = -1
    try:
        invoice_date_index = text.lower().index("invoice date")
    except:
        pass
    try:
        due_date_index = text.lower().index("due date")
    except:
        pass
    return invoice_date_index, due_date_index


def validate_ner_fields(text, entities, logger):
    if "InvoiceNum" in entities:
        invoice_num_index = get_invoice_num_index(text)
        # print("Invoice num index: ", invoice_num_index)
        if invoice_num_index > -1:
            if abs((invoice_num_index - int(entities["InvoiceNum"]["start"]))) > 20:
                logger.info("Deleting entity: invoice number")
            del entities["InvoiceNum"]
    if "PO" in entities:
        po_index = get_purchase_order_index(text)
        # print("PO index: ", po_index)
        # print("PO entity index: ", entities["PO"]["start"])
        if po_index > -1:
            if abs((po_index - int(entities["PO"]["start"]))) > 20:
                logger.info("Deleting entity: PO")
                del entities["PO"]

    invoice_date_index, due_date_index = get_dates_index(text)
    # print("Invoice date index: ", invoice_date_index)
    # print("Due date index: ", due_date_index)
    if "InvoiceDate" in entities:
        if invoice_date_index > -1:
            if abs((invoice_date_index - int(entities["InvoiceDate"]["start"]))) > 20:
                logger.info("Deleting entity: InvoiceDate")
                del entities["InvoiceDate"]

    if "DueDate" in entities:
        if due_date_index > -1:
            if abs((due_date_index - int(entities["DueDate"]["start"]))) > 20:
                logger.info("Deleting entity: DueDate")
                del entities["DueDate"]

    return entities


def populate_ntn_strn(raw_text, tapal_entities, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)

    # Define multiple NTN patterns for 0709631-3 or 34-01-0712331-7 or 071-2331-7
    ntn_patterns = [
        r'\b\d{5,7}-\d{1}\b',
        r'\b\d{1,3}-\d{4}-\d{0,1}-\d{1}\b',
        r'\b\d{1,3}-\d{4}-\d{0,1}-\d{1,}\b'
    ]

    strn_pattern = r'\b\d{2}-\d{2}-\d{4}-\d{3,}-\d{2}\b'

    ntn_numbers = set()  # Removing duplicates
    for pattern in ntn_patterns:
        matches = re.findall(pattern, raw_text)
        ntn_numbers.update(matches)

    # Remove NTN numbers without hyphens
    ntn_numbers = [number for number in ntn_numbers if '-' in number]

    strn_numbers = list(set(re.findall(strn_pattern, raw_text)))

    print("NTN:", ntn_numbers)
    print("STRN:", strn_numbers)

    # Check if NTN numbers are already present before appending
    tapal_entities["NTN"] += [number for number in ntn_numbers if number not in tapal_entities["NTN"]]

    # Check if STRN numbers are already present before appending
    tapal_entities["STRN"] += [number for number in strn_numbers if number not in tapal_entities["STRN"]]

    return tapal_entities

def populate_po(azure_response, raw_text, raw_text_without_spaces, entities, po_synonyms, other_fields, missing_fields,
                fr_field_to_entity_mapping,version):
    original_po = None
    potential_po = []
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
        original_po = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
    po_text = None
    if "PurchaseOrder" in entities:
        potential_po.append(entities["PurchaseOrder"]["text"])
    po_match_others = list(set(other_fields).intersection(set(po_synonyms)))
    print("po_match_others: ", po_match_others)
    if po_match_others:
        # Sorting based on priority
        index_list = [po_synonyms.index(x) for x in po_match_others]
        po_match_others = [x for _, x in sorted(zip(index_list, po_match_others))]
        po_match_others_values = [other_fields[po_mo][0].replace(" ", "") for po_mo in po_match_others if
                                  other_fields[po_mo][0]]
        po_text = po_match_others_values[0]
        potential_po.extend(po_match_others_values)
        if 'VendorAddress' in azure_response['analyzeResult'][container_key][0]['fields']:
            vendor_address = azure_response['analyzeResult'][container_key][0]['fields']['VendorAddress'][text_or_content].replace(" ", "")
            if po_text and po_text in vendor_address:
                #Removing the PO text if it is part of vendor address
                po_text = None
        if po_text:
            if not "PurchaseOrder" in entities:
                entities["PurchaseOrder"] = {"text": po_text, "type": "String", "valueString": po_text}

    for field in missing_fields:
        if fr_field_to_entity_mapping[field] in entities:
            if fr_field_to_entity_mapping[field] == "PurchaseOrder":
                entity_text = entities[fr_field_to_entity_mapping[field]]['text']
                if len(entity_text) > 4 and any(char.isdigit() for char in entity_text):
                    if not re.match(r'\d{2}/\d{2}/\d{4}$', entity_text): # Check for date pattern
                        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {
                        "type": "string",
                        "valueString": entities[fr_field_to_entity_mapping[field]]['text'],
                        text_or_content: entities[fr_field_to_entity_mapping[field]]['text'],
                        "potential": potential_po
                      }
            else:
                azure_response['analyzeResult'][container_key][0]['fields'][field] = {
                    "type": "string",
                    "valueString": entities[fr_field_to_entity_mapping[field]]['text'],
                    text_or_content: entities[fr_field_to_entity_mapping[field]]['text']
                }

    raw_text = raw_text.lower()
    if any(keyword in raw_text.lower() for keyword in ["tafe", "t.a.f.e", "ryde", "hunter institute of technology", "hunter inst of technology", "hunter tafe - kumi kumi", "kurri kurri campus", "technical & further education commission", "northern sydney institute", "technical and further education","coffs harbour education campus","campbelltown college of t","sydney institute of technology", "89755348137"]):
        regexes = [
            r'\b700(?:[\s-]?\d{4,7})\b',  # original pattern
            r'\b700\d{4,7}-\d{3}\b',  # new pattern to match "7000064-353"
            'PO700\d{7}' ,#new pattern to match PO7000065802
            r'\b700\d{3}/\d{3}\b', #pattern to match 700007/631
            r'\bP/O700\d{7}\b',  # Match "P/O7000078201"
            r'\b700\d{3}\s?\d{4}\b' ,#pattern to match 700008 5519
            r'\b760\d{4,7}\b',  # New pattern to match 760xxxxxxx
            r'\b70000\s?\d{5}\b', # pattern to match 70000 84057 or 70000 85361
            r'\b70000[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{1}\b', # Pattern to match "70000 85 36 1"
            r'\b700\s?\d{3}\s?\d{4}\b', # pattern to match "700 008 5528"
            r'\bBAKERY700\d{7}\b', # pattern to extract "BAKERY7000085007"
            r'\bP\.O700\d{7}\b', # pattern to extract "P.O7000066269"
            r'\b700\d{7}p/o\b'  # Match "7000085855p/o"

        ]

        seven_sth_matching_po = []
        for regex in regexes:
            seven_sth_matching_po.extend(re.findall(regex, raw_text, re.IGNORECASE))
        if not seven_sth_matching_po:
            for regex in regexes:
                seven_sth_matching_po.extend(re.findall(regex, raw_text_without_spaces))

        potential_po.extend(seven_sth_matching_po)

        potential_po = list(set(potential_po))
        potential_po = [po.replace("/", "1").replace("P1O", "").replace("PO","").replace("p1o", "").replace("po", "").replace(" ", "").replace("-", "").strip("\n").replace("p.o","").replace("no","").replace("bakery","") for po in potential_po if
                        any(char.isdigit() for char in po.strip("\n"))]
        potential_po = [
            '7000' + po[4:] if po.startswith('7600') else po
            for po in potential_po
        ]
        potential_po = [po for po in potential_po if po.isalnum()]
        if original_po is not None:
            if original_po.startswith("700"):
                if original_po in potential_po:
                    potential_po.remove(original_po)
                potential_po.insert(0, original_po)
        #Code to remove that PO which is a substring of ABN
        if "ABN" in azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]:
            ABNs = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]["ABN"]
            for abn in ABNs:
                for po_text in potential_po:
                    if po_text in abn:
                        potential_po.remove(po_text)
                        break

        if potential_po:
            #Create a new list with no duplicate values
            unique_potential_po = list(dict.fromkeys(potential_po))
            #Select the P) from unique list which starts with 700
            po_text = next((po for po in unique_potential_po if po.replace(" ", "").startswith("700")), None)
            #If more than 1 PO present with 700 pattern then only select the one with 10 digits
            if po_text and len(po_text.replace(" ", "")) != 10:
                po_text = next((po for po in unique_potential_po if
                                po.replace(" ", "").startswith("700") and len(po.replace(" ", "")) == 10), po_text)
            else:
                if "supagas" in raw_text.lower():
                    po_text = next((po for po in unique_potential_po if
                                    po.replace(" ", "").startswith("700") and len(po.replace(" ", "")) == 9), po_text)
            if po_text is None:
                po_text = unique_potential_po[0]
            print("Selected PO Text:", po_text)
            if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
                if not azure_response['analyzeResult'][container_key][0]['fields']['PurchaseOrder'][text_or_content].startswith("700"):
                    azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                        "potential"] = unique_potential_po
            else:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content] = po_text
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["valueString"] = po_text,
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                "potential"] = unique_potential_po
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields'] and not \
        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content].startswith('700'):
            del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])

    updated_raw_text = raw_text.replace("\n", " ").lower()
    if "talison lithium" in updated_raw_text:
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
            po_pattern = r'PU\d+'    # pattern to match PU followed by one or more digits for Talison Lithium
            match = re.search(po_pattern, raw_text)
            if match:
                po_number = match.group()
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                    "valueString"] = po_number
            elif po_text is not None:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content] = po_text
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                    "valueString"] = po_text
    if "macmahon" in updated_raw_text or "tmm group" in updated_raw_text or " t m m group" in updated_raw_text or "strong minds strong mines" in updated_raw_text or "sandvik" in updated_raw_text:
        # if "PurchaseOrder" in azure_response['analyzeResult']['documentResults'][0]['fields']:
        po_pattern = r'\b450\d{0,3}\s?\d{6}\b'
        match = re.search(po_pattern, raw_text)
        if match:
            po_number = match.group()
            po_number = re.sub(r'\s', '', po_number)
            if len(po_number) > 10:
                if "westrac" in updated_raw_text and po_number.endswith('0'):
                    po_number = po_number.rstrip('0')
                else:
                    po_number = po_number[:10]
            if len(po_number) > 8:
                if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                    azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                "valueString"] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                    "potential"] = []
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields'] and not azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content].startswith('45'):
            del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])

    if "ip australia" in updated_raw_text:
        lot_pattern = r'\blot - \d{5}\b'
        c_pattern = r'\bc\d{4}/\d{5}\b'
        lex_pattern = r'\blex \d{4}\b'

        # Find all potential PO matches in the text
        potential_pos = re.findall(lot_pattern, raw_text) + re.findall(c_pattern, raw_text) + re.findall(lex_pattern,
                                                                                                         raw_text)

        if potential_pos:
            if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content] = potential_pos[0]
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["valueString"] = \
            potential_pos[0]

    if "tapal" in updated_raw_text:
        po_pattern = r'\b4500\d{1}\s*\d{5}\b'
        matches = re.findall(po_pattern, raw_text)
        if matches:
            num_line_items = len(azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']) \
                if 'Items' in azure_response['analyzeResult'][container_key][0]['fields'] else 0

            # Check if number of POs match the number of line items
            if len(matches) == num_line_items and num_line_items > 0:
                for idx, item in enumerate(
                        azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']):
                    po = matches[idx]
                    item['valueObject']['PurchaseOrder'] = {
                        "type": "string",
                        "valueString": po,
                        "content": po
                    }
            else:
                # If there is one PO or the number of POs doesn't match line items
                po_number = matches[0]
                print("Extracted number:", po_number)
                if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                    azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                    text_or_content] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["valueString"] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["potential"] = matches
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields'] and not \
        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content].startswith('45'):
            del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])

    if "7-eleven" in updated_raw_text:
        po_pattern = r'\b455\d{7}\b'
        match = re.search(po_pattern, raw_text)
        if match:
            po_number = match.group()
            po_number = re.sub(r'\s', '', po_number)
            if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
            text_or_content] = po_number
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
            "valueString"] = po_number

    if ("mitsubishi" in updated_raw_text or "mmal parts & accessories" in updated_raw_text) and "tafe" not in updated_raw_text:
        po_pattern = r'4500\d{6}'
        matches = re.findall(po_pattern, raw_text)
        if matches:
            po_number = matches[0]
            if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
            text_or_content] = po_number
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
            "valueString"] = po_number
            # Adding all matches to potential list
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["potential"] = matches
        else:
            other_pattern = r'00703\d{5}|703\d{5}|704\d{5}'
            match_other_pattern = re.search(other_pattern,raw_text)
            if match_other_pattern:
                po_number = match_other_pattern.group()
                if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                    azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                    text_or_content] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["valueString"] = po_number
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["potential"] = []
            else:
                if "Items" in azure_response['analyzeResult'][container_key][0]['fields'] and ('commercial invoice' not in raw_text.lower() and 'sundry' not in raw_text.lower()):
                    line_items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
                    po_numbers = []
                    for item in line_items:
                        item_text = item[text_or_content].lstrip('001')
                        po_patterns = [r'(\w{4}\d{4})\w{8}', r'\b(\w{4}\d{4})\b', r'(\d{2}[A-Z]{2}\d{4})',  r'(\d{4}[A-Z]{3}\d{4})',]
                        po_number_match = None
                        for po_pattern in po_patterns:
                            po_number_match = re.search(po_pattern, item_text)
                            if po_number_match:
                                break
                        if po_number_match:
                            po_number_part = po_number_match.group(1)
                            if po_number_part.startswith('00'):
                                po_number_part = po_number_part[3:]
                            # Checking if both alphabets and numbers are present in PO
                            if any(char.isalpha() for char in po_number_part) and any(
                                    char.isdigit() for char in po_number_part):
                                po_number_modified = 'AA' + po_number_part
                                po_numbers.append(po_number_modified)
                    po_numbers = list(set(po_numbers))
                    if po_numbers:
                        po_text = po_numbers[0]
                        print("PO Numbers:", po_numbers)
                        if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
                        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                            "potential"] = po_numbers
                        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                            text_or_content] = po_text
                        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                            "valueString"] = po_text
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
            po_number = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
            if not (po_number.startswith('45') or po_number.startswith('00703') or po_number.startswith('703') or po_number.startswith('AA') or po_number.startswith('704')):
                del azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]

    if "adcb" in updated_raw_text:
        po_pattern = r'4500\d{6}'
        matches = re.findall(po_pattern, raw_text)
        if matches:
            po_number = matches[0]
            if "PurchaseOrder" not in azure_response['analyzeResult'][container_key][0]['fields']:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
            text_or_content] = po_number
            azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
            "valueString"] = po_number

    return azure_response


def validate_po(azure_response, raw_text, version):
    non_po_keywords = ["unknown", "INV", "number", "box", "SCTASK", "Page"]
    deleted = False
    container_key, text_or_content, value_type= mapping_utils.get_version_structure(version)
    if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
        if text_or_content in azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]:
            po_text = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
            po_text = po_text.replace('\n', '')
            updated_po_text = po_text.replace("PO", "").strip()
            if len(po_text) < 5 or len(updated_po_text) < 5:
                del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])
                deleted = True
            else:
                if "ABN" in azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]:
                    ABNs = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]["ABN"]
                    for abn in ABNs:
                        if po_text == abn and len(po_text) == 11:
                            del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])
                            deleted = True
                            break
                        if po_text in abn:
                            if "potential" in azure_response['analyzeResult'][container_key][0]['fields'][
                                "PurchaseOrder"]:
                                potential_po = \
                                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                                    "potential"]
                                if potential_po:
                                    azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                                        text_or_content] = potential_po[0]
                                    azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                                        "valueString"] = potential_po[0]
                                    break
            # if "box" in po_text or "number" in po_text or "SCTASK" in po_text or "Page" in po_text or "INV" in po_text:
            if any(kw in po_text for kw in non_po_keywords):
                del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])
                deleted = True
            if "dicetek" in raw_text.lower() and po_text.startswith("IT"):
                del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])
                deleted = True
        else:
            del (azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"])
            deleted = True
        # if not po_text.replace(" ", "").isdigit():
        #     print(po_text)
        #     print("I am here")
        #     del (azure_response['analyzeResult']['documentResults'][0]['fields']["PurchaseOrder"])
            if deleted is False:
                if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
                    if "potential" in azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]:
                        potential_po = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                            "potential"]
                        # remove spaces and keep only digit
                        potential_po = [pot_po.replace(" ", "") for pot_po in potential_po if
                                        pot_po.replace(" ", "")]
                        azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                            "potential"] = potential_po

                    po_text = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
                    if not any(char.isdigit() for char in po_text):
                        if "potential" in azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]:
                            potential_po = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                                "potential"]
                            if any(potential_po) and any(char.isdigit() for pot_po in potential_po for char in pot_po):
                                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                                    text_or_content] = potential_po[0]
                                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][
                                    "valueString"] = potential_po[0]

                    # seven_zero_matching_po = [s for s in potential_po if s[:2] == "70"]
                    # if seven_zero_matching_po:
                #     po_text = seven_zero_matching_po[0]
                #     azure_response['analyzeResult']['documentResults'][0]['fields']["PurchaseOrder"][
                #         "text"] = po_text
                #     azure_response['analyzeResult']['documentResults'][0]['fields']["PurchaseOrder"][
                #         "valueString"] = po_text
            if text_or_content in azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]:
                po_text = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
                po_text = po_text.replace(" ", "")
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content] = po_text
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["valueString"] = po_text
            else:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = {}

            if "potential" in azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]:
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["potential"] = sorted(
                azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]["potential"])

    return azure_response


def validate_customer_address(azure_response, blocks_list, address_kind,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if address_kind in azure_response['analyzeResult'][container_key][0]['fields']:
        custom_addr = azure_response['analyzeResult'][container_key][0]['fields'][address_kind][text_or_content]
        if len(custom_addr) < 20 and "po box" in custom_addr.lower():
            for page in blocks_list:
                for block in page:
                    if custom_addr in block['lines']:
                        relevant_index = block['lines'].index(custom_addr)
                        rest_addr = " ".join(block['lines'][relevant_index + 1:])
                        if "woden" in rest_addr.lower() or "phillip" in rest_addr.lower() or "tuggeranong" in rest_addr.lower():
                            azure_response['analyzeResult'][container_key][0]['fields'][address_kind][
                                text_or_content] = custom_addr + " " + rest_addr
                            azure_response['analyzeResult'][container_key][0]['fields'][address_kind][
                                "valueString"] = custom_addr + " " + rest_addr
    return azure_response

def populate_employee_id(azure_response, raw_text,version,employee_ids):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if 'tapal' in raw_text.lower() and 'employee id' in raw_text.lower():
        if 'Items' in azure_response['analyzeResult'][container_key][0]['fields']:
            for item in azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']:
                items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
                for index, item in enumerate(items):
                    if index < len(employee_ids):
                        employee_id = employee_ids[index]
                        item['valueObject']['EmployeeID'] = {
                        "type": "string",
                        "valueString": employee_id,
                        "content": employee_id
                       }

    return azure_response


def validate_customer_name(azure_response, other_fields,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "CustomerAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']:
        customer_name = azure_response['analyzeResult'][container_key][0]['fields']["CustomerAddressRecipient"][
            text_or_content]
        customer_name = customer_name.split("LOCKED")[0].strip()
        customer_name = customer_name.replace("Level 15", "").strip()
        if customer_name == "PTY LTD":
            if "charge to" in other_fields:
                customer_name = other_fields["charge to"][0]
        if "VendorAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']:
            vendor_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"][
                text_or_content]
            if customer_name != vendor_name:
                if "CustomerName" not in azure_response['analyzeResult'][container_key][0]['fields']:
                    azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"] = {}
                azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"][text_or_content] = customer_name
                azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"]["valueString"] = customer_name
        else:
            if "CustomerName" not in azure_response['analyzeResult'][container_key][0]['fields']:
                azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"] = {}
            azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"][text_or_content] = customer_name
            azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"]["valueString"] = customer_name
    else:
        if "CustomerName" not in azure_response['analyzeResult'][container_key][0]['fields']:
            azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"] = {}
        if "sold to" in other_fields:
            customer_name = other_fields["sold to"][0]
            if "deliver to" in other_fields and other_fields["deliver to"] and other_fields["deliver to"][0].isdigit():
                customer_name = other_fields["deliver to"][0]
        if "ship to" in other_fields:
            customer_name = other_fields["ship to"][0]
        if "customer / bill to" in other_fields:
            customer_name = other_fields["customer / bill to"][0]
        if "charge to" in other_fields:
            customer_name = other_fields["charge to"][0]
        if "contact" in other_fields and len(other_fields["contact"]) > 1:
            customer_name = other_fields["contact"][1]
        else:
            return azure_response
        azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"][text_or_content] = customer_name
        azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"]["valueString"] = customer_name
    return azure_response


def validate_supplier_name(azure_response,version, detected_language):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "VendorName" in azure_response['analyzeResult'][container_key][0]['fields']:
        vendor_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
        if detected_language == "ar":
            vendor_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
            azure_response['analyzeResult'][container_key][0]['fields']['VendorName'][text_or_content] = \
            vendor_name.split("\n")[0]
            azure_response['analyzeResult'][container_key][0]['fields']['VendorName']["valueString"] = \
                vendor_name.split("\n")[0]
            if vendor_name == "خاله الزوم للتجارة": #fixing ocr issue
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content] = "خالد الزوم للتجارة"
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"]["valueString"] = "خالد الزوم للتجارة"
            if "سيناء للتجارة" in vendor_name:
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][
                    text_or_content] = "سيناء للتجارة والتوكيلات العامة"
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][
                    "valueString"] = "سيناء للتجارة والتوكيلات العامة"
        if vendor_name == "MACMAHON":
            if "AccountName" in azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]:
                account_names = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]["AccountName"]
                if account_names:
                    azure_response['analyzeResult'][container_key][0]['fields']['VendorName'][text_or_content] = account_names[0]
                    azure_response['analyzeResult'][container_key][0]['fields']['VendorName']["valueString"] = account_names[0]
        if "VendorAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']:
            vendor_recipient = azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"][text_or_content]
            if "MM Electrical" in vendor_recipient:
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content] = vendor_recipient
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"]["valueString"] = vendor_recipient
            if (len(vendor_recipient) > len(vendor_name)) and detected_language != "ar":
                customer_name = None
                if "CustomerName" in azure_response['analyzeResult'][container_key][0]['fields']:
                    customer_name = azure_response['analyzeResult'][container_key][0]['fields']["CustomerName"][text_or_content]
                if customer_name is None or customer_name != vendor_recipient and "abn" not in vendor_recipient.lower():
                    azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][
                        text_or_content] = vendor_recipient
                    azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][
                        "valueString"] = vendor_recipient
            if "Nobul Pty Ltd" in vendor_recipient and "nobul" \
                    not in vendor_name:
                vendor_name = vendor_recipient.split(" ABN:")[0]
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][
                    text_or_content] = vendor_name
                azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][
                    "valueString"] = vendor_name
            if vendor_recipient == "IP Australia":
                if "AccountName" in azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]:
                    account_names = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"][
                        "AccountName"]
                    if account_names:
                        azure_response['analyzeResult'][container_key][0]['fields']['VendorName'][text_or_content] = \
                        account_names[0]
                        azure_response['analyzeResult'][container_key][0]['fields']['VendorName']["valueString"] = \
                        account_names[0]
    elif "VendorAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']:
        vendor_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"][text_or_content]
        azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content] = vendor_name
        azure_response['analyzeResult'][container_key][0]['fields']["VendorName"]["valueString"] = vendor_name
    return azure_response


def validate_invoice_num(azure_response, other_fields, version, raw_text, final_processing):
    """
    Cleaning invoice number from form recognizer
    in some cases, form recognizer is sending invoice number twice e.g. 2237906 2237906
    also removing spaces
    """
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)

    if "InvoiceId" in azure_response['analyzeResult'][container_key][0]['fields']:
        invoice_id_text = azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content]
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
            po_text = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
            # Removing the invoice ID if it is a PO
            if invoice_id_text == po_text:
                print("Invoice ID is the same as Purchase Order, Removing Invoice ID.")
                del (azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"])
                return azure_response
        invoice_id_text_split = list(set(invoice_id_text.replace("\n", " ").split(" ")))
        if len(invoice_id_text_split) == 1:
            updated_invoice_text = invoice_id_text_split[0]
            updated_invoice_text = updated_invoice_text.replace(":", "")
            updated_invoice_text = re.sub(r'[\u0600-\u06FF]+', '', updated_invoice_text)
        else:
            updated_invoice_text = invoice_id_text.replace(" ", "")
            updated_invoice_text = updated_invoice_text.replace(":", "")
        # Trimming leading zeros for Macmahon only
        if ("macmahon" in raw_text.lower() or "tmm group" in raw_text.lower()) and (final_processing is True):
            updated_invoice_text = updated_invoice_text.lstrip('0')
        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content] = updated_invoice_text
        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
            "valueString"] = updated_invoice_text
        if "Number" in invoice_id_text:
            inv_num = invoice_id_text.replace("Number:", "").replace(" ", "")
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content] = inv_num
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                "valueString"] = inv_num
        if "SALES TAX INVOICE" in invoice_id_text or invoice_id_text.startswith('SNTN NO'):
            if "CustomerId" in azure_response['analyzeResult'][container_key][0]['fields']:
                customer_id_text = azure_response['analyzeResult'][container_key][0]['fields']["CustomerId"][text_or_content]
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content] = customer_id_text
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                    "valueString"] = customer_id_text

        if "S9400" in invoice_id_text and "invoice no" in other_fields:
            inv_num = other_fields["invoice no"][0]
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content] = inv_num.upper()
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                "valueString"] = inv_num.upper()

        if "tax invoice number" in other_fields:
            inv_num = other_fields["tax invoice number"][0]
            if any(char.isdigit() for char in inv_num):
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content] = inv_num
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                    "valueString"] = inv_num

        if "tax invoice no ." in other_fields:
            inv_num = other_fields["tax invoice no ."][0]
            if any(char.isdigit() for char in inv_num):
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content] = inv_num
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                    "valueString"] = inv_num

        if "page" in other_fields:
            if other_fields["page"][0] == "POS RECEIPT":
                if "InvoiceId" in azure_response['analyzeResult'][container_key][0]['fields']:
                    print("POS receipt detected. Invoice ID will be removed.")
                    del azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"]
        if "no" in other_fields and version == "v2.1":
            number = other_fields["no"][0]
            if "InvoiceId" in azure_response['analyzeResult'][container_key][0]['fields']:
                inv_id = azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][text_or_content]
                if inv_id == number:
                    del azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"]

    else:
        if "InvoiceId" not in azure_response['analyzeResult'][container_key][0]['fields']:
            if "your account with us" in other_fields:
                inv_num = other_fields["your account with us"][0]
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                        "type": "string",
                        "valueString": inv_num,
                        text_or_content: inv_num
                }


    return azure_response


def validate_invoice_for_dockerizedversion(azure_response, version, other_fields):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if version == "v2.1":
        if "InvoiceId" not in azure_response['analyzeResult'][container_key][0]['fields']:
            inv_id = None
            if "tax invoice" in other_fields:
                # Check for multiple values present in "tax invoice"
                inv_texts = other_fields["tax invoice"]

                for inv_text in inv_texts:
                    inv_text = inv_text.replace("N0. ", "").strip()
                    # Check if the invoice id contains any digits
                    if any(char.isdigit() for char in inv_text) and "ABN" not in inv_text:
                        inv_id = inv_text
                        break # If no match is found, break the loop

                if inv_id is not None:
                    azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                        "type": "string",
                        "valueString": inv_id,
                        text_or_content: inv_id
                       }
            if inv_id is None and "sales order" in other_fields:
                inv_num = other_fields["sales order"][0]
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                    "type": "string",
                    "valueString": inv_num,
                    text_or_content: inv_num
                }

    return azure_response


def validate_invoice_from_raw_text(azure_response, raw_text, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)

    if "InvoiceId" not in azure_response['analyzeResult'][container_key][0]['fields']:
        tax_invoice_match = re.search(r'Tax Invoice\s*(\d+)', raw_text)
        if tax_invoice_match:
            inv_id = tax_invoice_match.group(1)
            if len(inv_id) > 3:
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                    "type": "string",
                    "valueString": inv_id,
                    text_or_content: inv_id
                }
            return azure_response
        transport_contract_label = "Transport Contract No."

        match = re.search(rf"{re.escape(transport_contract_label)}\s*([\d\s]+)", raw_text)
        if match:
            transport_contract_text = match.group(1).strip()
            transport_contract_text = "".join(re.findall(r'\d', transport_contract_text))

            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                "type": "string",
                "valueString": transport_contract_text,
                text_or_content: transport_contract_text
            }
        else:
            match = re.search(r"\b(\d[\d\s\.\-:]+)\b", raw_text)
            if match:
                other_case_text = match.group(1).strip()
                other_case_text = "".join(re.findall(r'\d', other_case_text))
                PHONE_NUMBER_REGEX = re.compile(r'^(?:\+?61)?(?:\s?\d){8,10}$')
                if not bool(re.match(PHONE_NUMBER_REGEX, other_case_text)):
                    if len(other_case_text) > 3:
                        bank_details = azure_response['analyzeResult'][container_key][0]['fields']["BankDetails"]
                        if "ABN" in bank_details:
                            ABNs = bank_details["ABN"]
                            if other_case_text not in ABNs:
                                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                                    "type": "string",
                                     "valueString": other_case_text,
                                     text_or_content: other_case_text
                                    }

    return azure_response


def validate_invoice_date(azure_response,other_fields,version):
    """
    Cleaning invoice date from form recognizer
    in some cases, form recognizer is sending invoice date twice e.g. 21-NOV-22 21-NOV-22
    also removing spaces
    """
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "InvoiceDate" in azure_response['analyzeResult'][container_key][0]['fields']:
        invoice_date_text = azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][text_or_content]
        if invoice_date_text == "17 1 2 2": #Hard coding this value as there is issue with encoding of this particular pdf file
            corrected_date = "17/10/2024"
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][text_or_content] = corrected_date
        match = re.search(r'OG\s*-\s*\d{1,2}\s*-\s*\d{4}', invoice_date_text)
        if match:
            invoice_date_text = azure_response['analyzeResult'][container_key][0]['fields']["ServiceEndDate"][
                text_or_content]
            new_date = invoice_date_text.replace(" ", "")
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][text_or_content] = new_date

        else:
            if re.search(r'\d\s\d', invoice_date_text):
                if invoice_date_text == "12 823":
                    day_of_year = int(invoice_date_text[:2])
                    month = int(invoice_date_text[3:4])
                    year_part = invoice_date_text[4:].replace(' ', '')
                    if year_part:
                        date_string = f"{day_of_year}/{month}/20{year_part}"
                        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][
                            text_or_content] = date_string

            invoice_date_text_split = list(set(invoice_date_text.split(" ")))
            print("Date here:" ,invoice_date_text_split)
            if len(invoice_date_text_split) == 1:
                updated_invoice_date = invoice_date_text_split[0]
                try:
                    parse(updated_invoice_date, fuzzy=True)
                except ValueError:
                    # If parsing fails, add the current year
                    current_year = datetime.now().year
                    updated_invoice_date += f" {current_year}"

                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][
                    text_or_content] = updated_invoice_date

            invoice_date_text = azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][text_or_content]
            new_date = re.sub(r'2CITY$', '', invoice_date_text)
            new_date = re.sub(r'PUP$', '', new_date)
            new_date = new_date.strip()
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][text_or_content] = new_date
            if "Date" in invoice_date_text:
                inv_date = invoice_date_text.replace("Date:", "").replace(" ", "")
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][text_or_content] = inv_date
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"][
                    "valueString"] = inv_date
            if "delivery date" in other_fields:
                inv_date = other_fields["delivery date"][0]
                date_formats = ["%Y-%m-%d", "%d %b %Y"]
                valid_date = None

                for fmt in date_formats:
                    try:
                        valid_date = datetime.strptime(inv_date, fmt)
                        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"] = {
                            "type": "string",
                            "valueString": inv_date,
                            text_or_content: inv_date
                        }
                        break
                    except ValueError:
                        continue
    if "InvoiceDate" not in azure_response['analyzeResult'][container_key][0]['fields']:
        if "period ending" in other_fields:
            inv_date = other_fields["period ending"][0]
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"] = {
                    "type": "string",
                    "valueString": inv_date,
                    text_or_content: inv_date
                }
        if "delivery date" in other_fields:
            inv_date = other_fields["delivery date"][0]
            azure_response['analyzeResult'][container_key][0]['fields']["InvoiceDate"] = {
                "type": "string",
                "valueString": inv_date,
                text_or_content: inv_date
            }
    return azure_response


def validate_numeric_field(azure_response, numeric_field,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if numeric_field in azure_response['analyzeResult'][container_key][0]['fields']:
        field_text = azure_response['analyzeResult'][container_key][0]['fields'][numeric_field][text_or_content]
        if isinstance(field_text, int) or isinstance(field_text, float): # Resolved TypeError to check type before subscripting field_text variable
            field_text = str(field_text)
        if field_text and field_text[-1] == "-":
            updated_field_text = "-" + field_text[:-1].replace("$", "").replace("\n", "")
            if azure_response["isCreditNote"] is False:
                updated_field_text = updated_field_text[1:]
            updated_field_number = 0
            try:
                updated_field_number = int(updated_field_text)
            except ValueError as e:
                try:
                   updated_field_number = float(updated_field_text)
                except ValueError as e:
                    pass

            azure_response = mapping_utils.set_currency(azure_response, version, numeric_field, updated_field_number, updated_field_text)

    return azure_response


def validate_line_item_quantity(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "Items" in azure_response['analyzeResult'][container_key][0]['fields']:
        items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
        for item in items:
            if 'Amount' in item['valueObject'] and 'UnitPrice' in item['valueObject']:
                try:
                    amount = float(item['valueObject']['Amount'].split()[0])
                    unit_price = float(item['valueObject']['UnitPrice'].split()[0])
                    calculated_quantity = amount / unit_price
                    item['valueObject']['Quantity'] = int(calculated_quantity)

                except (ValueError, ZeroDivisionError) as e:
                    print(f"Error processing item: {e}")

    return azure_response


def validate_line_items(azure_response, version, final_processing):
    if final_processing is True:
        indexes_to_delete = []
        container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
        item_content_and_fields = defaultdict(lambda: {"content": "", "fields": []})
        if "Items" in azure_response['analyzeResult'][container_key][0]['fields']:
            for i, value_array in enumerate(
                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']):
                if "content" in value_array:
                    item_content_and_fields[i]["content"] = value_array["content"]
                if "valueObject" in value_array:
                    item_content_and_fields[i]["fields"] = list(value_array["valueObject"].keys())
                    if (not "Description" in value_array["valueObject"]) and (not "Quantity" in value_array["valueObject"]):
                        indexes_to_delete.append(i)

        print(item_content_and_fields)

        field_lens = [len(v["fields"]) for v in item_content_and_fields.values()]
        content_line_counts = [len(v["content"].splitlines()) for v in item_content_and_fields.values()]

        if field_lens:
            min_field_len = min(field_lens)
            max_field_len = max(field_lens)
            min_content_lines = min(content_line_counts)
            max_content_lines = max(content_line_counts)

            for k, v in item_content_and_fields.items():
                field_len = len(v["fields"])
                content_lines = len(v["content"].splitlines())

                include = False
                if min_field_len != max_field_len and field_len == min_field_len:
                    include = True
                # if min_content_lines != max_content_lines and content_lines == min_content_lines:
                #     include = True

                if include:
                    indexes_to_delete.append(k)

        indexes_to_delete = set(list(indexes_to_delete))
        for idx in sorted(indexes_to_delete, reverse=True): # Delete in reverse order so you don't throw off the subsequent indexes
            del azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][idx]

    return azure_response


def validate_line_item_amounts(azure_response,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "Items" in azure_response['analyzeResult'][container_key][0]['fields']:
        for i, value_array in enumerate(
                azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']):
            if "valueObject" in value_array:
                if "Amount" in value_array["valueObject"]:
                    # print(value_array["valueObject"]["Amount"]["text"])
                    field_text = str(value_array["valueObject"]["Amount"][text_or_content])
                    if field_text[-1] == "-" and (
                            isinstance(field_text[:-1], int) or isinstance(field_text[:-1], float)):
                        updated_field_text = "-" + field_text[:-1]
                        azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                            "valueObject"]["Amount"][text_or_content] = updated_field_text
                        try:
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                "valueObject"]["Amount"][value_type] = int(updated_field_text)
                        except ValueError as e:
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                "valueObject"]["Amount"][value_type] = float(
                                updated_field_text)

    return azure_response


def validate_quantity_for_packing_invoices(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    supplier_name = None
    if "Items" in azure_response['analyzeResult'][container_key][0]['fields'] and "VendorName" in azure_response['analyzeResult'][container_key][0]['fields']:
        items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
        supplier_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
        for item in items:
            content = item[text_or_content]
            content_split = content.split('\n')
            if supplier_name == "KASMY PACK (PRIVATE) LIMITED":
                if len(content_split) > 6:
                    quantity = content_split[6]
                    update_item_field(item, text_or_content, "Quantity", quantity)
            elif supplier_name in ["BULLEH SHAH PACKAGING (PVT) LTD", "PACKAGES CONVERTORS LIMITED"]:
                if len(content_split) > 2:
                    quantity = content_split[2]
                    update_item_field(item, text_or_content, "Quantity", quantity)
            elif "MP POWER" in supplier_name:
                # Regex pattern to match integers before PC for MP POWER supplier
                match = re.search(r'(\d+)\.0-\s*PC', content)
                if match:
                    quantity = int(match.group(1))
                    update_item_field(item, text_or_content, "Quantity", quantity)

    return azure_response

def validate_and_update_line_items(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    supplier_name = None
    if "Items" in azure_response['analyzeResult'][container_key][0]['fields'] and "VendorName" in azure_response['analyzeResult'][container_key][0]['fields']:
        items = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
        supplier_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
        for item in items:
            content = item[text_or_content]
            content_split = content.split()
            if "Diners Club" in supplier_name:
                if len(content_split) > 2:
                    unit_price = content_split[2]
                    update_item_field(item, text_or_content, "UnitPrice", unit_price)

    return azure_response

def update_item_field(item, text_or_content, field_name, value):
    if "valueObject" not in item:
        item["valueObject"] = {}
    if field_name not in item["valueObject"]:
        item["valueObject"][field_name] = {}

    item["valueObject"][field_name][text_or_content] = value

    try:
        value = str(value)
        value_number = float(value.replace(',', ''))
        item["valueObject"][field_name]["valueNumber"] = value_number
    except ValueError:
        item["valueObject"][field_name]["valueNumber"] = None


def validate_line_item_gst(azure_response,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if "Items" in azure_response['analyzeResult'][container_key][0]['fields']:
        for i, value_array in enumerate(
                azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']):
            if "valueObject" in value_array:
                if "Tax" in value_array["valueObject"]:
                    field_text = value_array["valueObject"]["Tax"][text_or_content]
                    if isinstance(field_text, str) and '%' in field_text:
                        tax = field_text.replace('%', '')
                        if value_type == "valueNumber":
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                            "valueObject"]["Tax"][text_or_content] = tax
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                            "valueObject"]["Tax"]["type"] = "number"
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                            "valueObject"]["Tax"][value_type] = tax
                        else:
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                "valueObject"]["Tax"][value_type] = {"amount": tax}
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                "valueObject"]["Tax"]["type"] = "currency"
                            azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                "valueObject"]["Tax"][text_or_content] = tax
                else:
                    if "UnitPrice" in value_array["valueObject"]:
                        field_text = value_array["valueObject"]["UnitPrice"][text_or_content]
                        amounts = field_text.split()
                        if len(amounts) == 3 and all(amount for amount in amounts):
                            tax = amounts[2]
                            if tax.isdigit():
                                azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                 'valueObject']['Tax'] = {}
                                if value_type == "valueNumber":
                                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                    "valueObject"]["Tax"][text_or_content] = tax
                                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                    "valueObject"]["Tax"]["type"] = "number"
                                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                    "valueObject"]["Tax"][value_type] = tax
                                else:
                                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                    "valueObject"]["Tax"][value_type] = {"amount": tax}
                                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                    "valueObject"]["Tax"]["type"] = "currency"
                                    azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray'][i][
                                    "valueObject"]["Tax"][text_or_content] = tax

    return azure_response


def normalize_bounding_box(bounding_box):
    # Detect if bounding box values represent small decimals and apply scaling.
    width = abs(bounding_box[2] - bounding_box[0])
    height = abs(bounding_box[5] - bounding_box[1])

    if width < 10 and height < 10:
        scale_factor = 1000
        bounding_box = [coord * scale_factor for coord in bounding_box]

    return bounding_box


def check_tax_invoice_header(azure_response, version, max_lines=15):
    # Check if 'tax invoice' or 'invoice' is present in the first `max_lines` lines of the document.
    """Added this because OCR was detecting 'invoice' keyword found anywhere
       in the document and calculating its font size leading to all pages being
       flagged as isInvoice True"""
    container_key, text_or_content, block_type = mapping_utils.get_response_structure(version)
    line_counter = 0
    keywords = ["tax invoice", "invoice", "manual payment requisition form", "cheque requisition",
                "payment request form"]
    pattern = r"\b(?:{})\b".format("|".join(re.escape(kw) for kw in keywords))

    for page in azure_response["analyzeResult"][container_key]:
        for line in page["lines"]:
            line_counter += 1
            if line_counter > max_lines:
                return False

            line_text = line[text_or_content].lower()
            for keyword in keywords:
                if re.search(pattern, line_text, re.IGNORECASE):
                    print(f"Found '{keyword}' in line {line_counter}")
                    return True

    return False


def calculate_font_size_for_tax_invoice(azure_response, version):
    # Calculate the font size and average character width for the given line text and bounding box.
    container_key, text_or_content, block_type = mapping_utils.get_response_structure(version)
    keyword = ["tax invoice", "invoice"]
    line_count = 0
    max_lines_to_check = 15

    for page in azure_response["analyzeResult"][container_key]:
        for line in page["lines"]:
            line_count += 1
            if line_count > max_lines_to_check:
                break
            for key in keyword:
                if key in line[text_or_content].lower():
                    line_bounding_box = line[block_type]
                    line_bounding_box = normalize_bounding_box(line_bounding_box)
                    num_words = len(line[text_or_content].split())

                    font_size = font_size_estimation.estimate_font_size(line_bounding_box, num_words)
                    print(f"Estimated font size: {font_size}")

                    return font_size
    return None


def final_invoice_verification(raw_text, azure_response,version, detected_language):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    azure_response['nonInvoice'] = False  # Using this to separate specifically non-invoices vs invoices with low
    # completeness score
    tax_header = check_tax_invoice_header(azure_response,version)
    if azure_response['isTaxInvoice'] is True:
        if not tax_header and azure_response['analyzeResult'][container_key][0][
        'completenessScore'] <= 0.4:
            azure_response['isTaxInvoice'] = False
    font_size = calculate_font_size_for_tax_invoice(azure_response, version)
    if isinstance(font_size, tuple):
        font_size = font_size[0]
    if azure_response['isTaxInvoice'] is False and not tax_header and (font_size is None or font_size <= 201) and azure_response['analyzeResult'][container_key][0][
        'completenessScore'] <= 0.75:
        is_invoice = False
        raw_text = raw_text.lower()
        email_keywords = ["from", "to", "subject", "cc", "attachments"]
        greeting_keywords = ["dear", "hi", "hello"]
        regards_keywords = ["regards", "best regards", "sincerely", "thanks", "thank you"]
        is_email = False

        # Check if all keywords in email_keywords are present in raw_text
        if all(keyword in raw_text for keyword in email_keywords):
            has_greetings = any(greet in raw_text for greet in greeting_keywords)
            has_regards = any(regard in raw_text for regard in regards_keywords)
            if has_greetings and has_regards:
                is_email = True

        if is_email:
            is_invoice = False
        else:
            for label_list in NOT_AN_INVOICE_LABELS:
                if all(label in raw_text for label in label_list):
                    print(f"Label causing invoice to be flagged as non invoice: {label_list}")
                    is_invoice = False
                    break

        if azure_response['isCreditNote'] is True or azure_response['isBill'] is True:
            is_invoice = True

        if is_invoice is False and detected_language != "ar":
            azure_response['isInvoice'] = False
            azure_response['nonInvoice'] = True  # Using this to separate specifically non-invoices vs invoices with low
            # completeness score
        else:
            if ("job #" in raw_text or "job id" in raw_text) and not (
                    "InvoiceTotal" in azure_response['analyzeResult'][container_key][0]['fields'] or "AmountDue" in
                    azure_response['analyzeResult'][container_key][0]['fields']):
                azure_response['isInvoice'] = False
    # # This is for case having completeness score > 0.75 and is non invoice
    # if "DEBIT NOTE" in raw_text and azure_response['analyzeResult'][container_key][0][
    #     'completenessScore'] > 0.75:
    #     azure_response['isInvoice'] = False
    #     azure_response['nonInvoice'] = True
    print("Is Invoice:", azure_response['isInvoice'])
    return azure_response


def validate_tax_amount(azure_response,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if not 'TotalTax' in azure_response['analyzeResult'][container_key][0]['fields']:
        if 'Items' in azure_response['analyzeResult'][container_key][0]['fields']:
            value_array = azure_response['analyzeResult'][container_key][0]['fields']['Items']['valueArray']
            if len(value_array) > 0:
                text = value_array[0][text_or_content]
                values = text.split()
                if len(values) > 1:
                    tax_amount_value = values[-2]
                    tax_amount_value = tax_amount_value.replace('$', '').replace(',', '')
                    try:
                        tax_amount_value = float(tax_amount_value)
                        azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"] = {}
                        azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                            text_or_content] = tax_amount_value

                        if value_type == "valueCurrency":
                            azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                                value_type] = {"amount": tax_amount_value}
                            azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                                "type"] = "currency"
                        elif value_type == "valueNumber":
                            azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                                value_type] = tax_amount_value
                            azure_response['analyzeResult'][container_key][0]['fields']["TotalTax"][
                                "type"] = "number"
                        else:
                            raise KeyError(f"Unsupported value type: {value_type}")

                        print("Tax Amount:", tax_amount_value)
                    except ValueError:
                        print("No Tax")
                else:
                    print("Tax Amount not found")
            else:
                print("Tax Amount not found")
    return azure_response


def extract_total_tax(azure_response, raw_text):
    #Extracting total tax from raw text by extracting the value coming below the Total Tax text
    pattern = r'TOTAL\s*Tax\s*\n\s*AUD\s*([0-9,]+\.[0-9]+)'
    match = re.search(pattern, raw_text)
    if match:
        total_tax_str = match.group(1).replace(',', '')
        try:
            total_tax = float(total_tax_str)
            azure_response['analyzeResult']['documentResults'][0]['fields']["TotalTax"]['text'] = total_tax
            azure_response['analyzeResult']['documentResults'][0]['fields']["TotalTax"]['valueNumber'] = total_tax
        except ValueError:
            print("Error: Unable to convert TotalTax to float")
    return azure_response


def validate_invoice_total(azure_response, raw_text, version):
    invoice_total_val, invoice_total_content = mapping_utils.get_currency(azure_response, raw_text, version,
                                                                          "InvoiceTotal")
    amount_due_val, amount_due_content = mapping_utils.get_currency(azure_response, raw_text, version, "AmountDue")

    # if invoice_total_val is not None:
    #     cleaned_invoice_total_content = invoice_total_content.strip(ascii_letters).strip()
    #     try:
    #         updated_invoice_total_val = float(cleaned_invoice_total_content.replace(",", ""))
    #         if updated_invoice_total_val != invoice_total_val:
    #             azure_response = mapping_utils.set_currency(azure_response, version, "InvoiceTotal",
    #                                                         updated_invoice_total_val, invoice_total_content)
    #     except ValueError:
    #         pass

    if invoice_total_val is None and amount_due_val is not None:
        azure_response = mapping_utils.set_currency(azure_response, version, "InvoiceTotal", amount_due_val,
                                                    amount_due_content)

    if invoice_total_val is not None and amount_due_val is not None:
        if (isinstance(amount_due_val, int) or isinstance(amount_due_val, float)) and (isinstance(invoice_total_val,
                                                                                                 int) or isinstance(
                invoice_total_val, float)):
            container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
            if 'VendorName' in azure_response['analyzeResult'][container_key][0]['fields']:
                vendor_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
                if "K-Electric" not in vendor_name:
                    if amount_due_val > invoice_total_val:
                        azure_response = mapping_utils.set_currency(azure_response, version, "InvoiceTotal", amount_due_val,
                                                            amount_due_content)

    return azure_response


def populate_credit_note_num(azure_response, other_fields, raw_text,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if azure_response['isCreditNote'] is True:
        credit_memo_num = spacy_inference.predict_credit_memo_num(raw_text)
        print("Raw text: ", raw_text)
        print("Model result for credit memo number:", credit_memo_num)
        po_num = None
        if "PurchaseOrder" in azure_response['analyzeResult'][container_key][0]['fields']:
            po_num = azure_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"][text_or_content]
        if isinstance(credit_memo_num, str) and (re.search(r'^\$\d{1,3}(,\d{3})*(\.\d{2})?$',
                          credit_memo_num) or re.search(r'[()"]', credit_memo_num)):# Resolving type error for non string type credit note number
            credit_memo_num = None
        for key in ["credit for invoice", "our ref"]:
            if key in other_fields:
                reference = other_fields[key][0]
                if key == "credit for invoice" and credit_memo_num == reference:
                    credit_memo_num = None
                elif key == "our ref" and isinstance(credit_memo_num, str) and credit_memo_num in reference:
                    credit_memo_num = None
        if credit_memo_num is not None and 4 < len(credit_memo_num) <= 14 and 'Act' not in credit_memo_num and (po_num is None or po_num not in credit_memo_num):
            if '$' in credit_memo_num:
                potential_credit_note_nums = re.findall(r'\bCN\s*[A-Z0-9]+\b', raw_text)
                if potential_credit_note_nums:
                    credit_note_num = potential_credit_note_nums[0]
                    if '/' in credit_note_num or ' ' in credit_note_num:
                        credit_note_num = credit_note_num.replace("/", "").replace(" ", "")
                        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                            "type": "string",
                            "valueString": credit_note_num,
                            text_or_content: credit_note_num
                        }
            if credit_memo_num == "PC 10":
                if 'invoice number' in other_fields:
                    invoice_number = other_fields['invoice number'][0]
                    if any(char.isdigit() for char in invoice_number):
                        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                            "content"] = "PC " + invoice_number
                        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"][
                            "valueString"] = "PC " + invoice_number

            else:
                if '/' in credit_memo_num or ' ' in credit_memo_num:
                    credit_memo_num = credit_memo_num.replace("/", "").replace(" ", "")
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                    "type": "string",
                    "valueString": credit_memo_num,
                    text_or_content: credit_memo_num
                }
        elif any([credit_num_label for credit_num_label in CREDIT_NOTE_NUM_LABELS if credit_num_label in other_fields]):
            matching_label = \
                [credit_num_label for credit_num_label in CREDIT_NOTE_NUM_LABELS if credit_num_label in other_fields][0]
            credit_note_num = other_fields[matching_label][0]
            if any(char.isdigit() for char in credit_note_num) and 'Page' not in credit_note_num:
                credit_note_num = credit_note_num.replace(" ", "")
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                    "type": "string",
                    "valueString": credit_note_num,
                    text_or_content: credit_note_num
                }

        else:
            credit_memo_num_patterns = [r'SC\d+', r'CFS-CN\d+']
            potential_credit_note_nums = []
            for pattern in credit_memo_num_patterns:
                potential_credit_note_nums.extend(re.findall(pattern, raw_text))
            if potential_credit_note_nums:
                credit_note_num = potential_credit_note_nums[0]
                if '/' in credit_note_num or ' ' in credit_note_num:
                    credit_note_num = credit_note_num.replace("/", "").replace(" ", "")
                azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {
                    "type": "string",
                    "valueString": credit_note_num,
                    text_or_content: credit_note_num
                }
    else:
        if "credit" in other_fields and "invoice" not in raw_text:
            for val in other_fields["credit"]:
                if val.isdigit():
                    if "InvoiceId" not in azure_response['analyzeResult'][container_key][0]['fields']:
                        azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"] = {"type": "string"}
                    azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"]["text"] = val
                    azure_response['analyzeResult'][container_key][0]['fields']["InvoiceId"]["valueString"] = val


    return azure_response



def convert_negative_to_positive(azure_response, numeric_field,version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if numeric_field in azure_response['analyzeResult'][container_key][0]['fields']:
        field_info = azure_response['analyzeResult'][container_key][0]['fields'][numeric_field]
        numeric_field_content = str(field_info[text_or_content])
        if version == "v2.1":
            value_number = field_info.get("valueNumber", None)
        else:
            if isinstance(field_info, dict) and value_type == 'valueCurrency':
                value_number = field_info.get('valueCurrency', {})
                if isinstance(value_number, dict):
                    value_number = value_number.get("amount", None)

        if azure_response['isCreditNote'] is True and value_number is not None:
            if isinstance(value_number, dict):
                value_number = value_number.get('value', None)
            if isinstance(value_number, str):
                # Removing currency symbols and commas
                value_number = value_number.replace("$", "").replace(",", "").strip()
            try:
                positive_value = abs(float(value_number))
                azure_response = mapping_utils.set_currency(azure_response, version, numeric_field, positive_value, numeric_field_content.lstrip("-"))
            except ValueError:
                print(f"Error converting value to float: {value_number}")

    return azure_response


def validate_responses(responses,version):
    #Created a separate function to handle the groupM scenario
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    inv_response = None
    groupm_response = None
    for resp in responses:
        if "VendorName" in resp['analyzeResult'][container_key][0]['fields']:
            supplier_name_val = resp['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
            if "groupm" in supplier_name_val.lower():
                groupm_response = resp
                print("Found groupm invoice")
            else:
                if resp['isInvoice']:
                    inv_response = resp
                    print("Found non-groupm invoice")
    if groupm_response and inv_response:
        inv_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"] = \
            groupm_response['analyzeResult'][container_key][0]['fields']["PurchaseOrder"]

        responses.remove(groupm_response)

    return responses


def validate_vendor_add_recipient(azure_response, version):
    container_key, text_or_content, value_type = mapping_utils.get_version_structure(version)
    if ("VendorName" in azure_response['analyzeResult'][container_key][0]['fields']) and ("VendorAddressRecipient" in azure_response['analyzeResult'][container_key][0]['fields']):
        vendor_name = azure_response['analyzeResult'][container_key][0]['fields']["VendorName"][text_or_content]
        vendor_add_rcpt = azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"][text_or_content]
        if len(vendor_name) > len(vendor_add_rcpt):
            azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"][text_or_content] = vendor_name
            azure_response['analyzeResult'][container_key][0]['fields']["VendorAddressRecipient"]["valueString"] = vendor_name

    return azure_response


def validate_fr_fields(azure_response, raw_text, blocks_list, other_fields,version, detected_language, final_processing):
    azure_response = validate_supplier_name(azure_response, version, detected_language)
    azure_response = validation_populater.populate_billing_info(azure_response, version)
    azure_response = validate_invoice_total(azure_response, raw_text, version)
    if detected_language != "ar":
        azure_response = validate_customer_address(azure_response, blocks_list, "CustomerAddress",version)
        azure_response = validate_customer_address(azure_response, blocks_list, "VendorAddress",version)
        azure_response = validate_customer_name(azure_response, other_fields,version)
        azure_response = validation_populater.populate_account_number(azure_response, other_fields, raw_text, version)
        azure_response = validation_populater.populate_contract_num(azure_response, raw_text, other_fields,version)
        azure_response = validate_invoice_num(azure_response, other_fields, version, raw_text,
                                                              final_processing)
        azure_response = validate_invoice_for_dockerizedversion(azure_response, version, other_fields)
        azure_response = validate_invoice_date(azure_response,other_fields,version)
        azure_response = validate_numeric_field(azure_response, "InvoiceTotal",version)
        azure_response = validate_numeric_field(azure_response, "TotalTax",version)
        azure_response = validate_line_items(azure_response, version, final_processing)
        azure_response = validate_line_item_amounts(azure_response,version)
        azure_response = validate_quantity_for_packing_invoices(azure_response, version)
        azure_response = validate_and_update_line_items(azure_response, version)
        azure_response = validate_line_item_gst(azure_response,version)
        if version == 'v2.1':
            azure_response = validation_populater.populate_invoice_total_from_items(azure_response)
        if version == 'v3.1':
            # azure_response = validate_vendor_add_recipient(azure_response, version)
            azure_response = validation_populater.populate_customer_add_recipient(azure_response, version)
        # azure_response = validate_invoice_total(azure_response, raw_text, version)
        azure_response = validation_populater.populate_total_tax(azure_response, other_fields,version)
        azure_response = validate_tax_amount(azure_response,version)
        azure_response = validation_populater.populate_shipment_number(azure_response, other_fields, raw_text, version)
        azure_response = validation_populater.populate_cost_center(azure_response, version)
        azure_response = validation_populater.populate_dc_num(azure_response, raw_text, version)
        azure_response = validation_populater.populate_unspsc_code(azure_response, version)
        azure_response = validation_populater.populate_contact_person(azure_response, version, other_fields)

    return azure_response
