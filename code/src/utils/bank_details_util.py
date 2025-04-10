from abn import validate as validate_abn
from fuzzywuzzy import fuzz, process
import re
import string
from src import mapping_utils, font_size_estimation
from src.ner import spacy_inference


def clean_bank_det_entities(bank_det_entities):
    digit_ents = ["ABN", "AccountNum", "BSB"]
    for ent in bank_det_entities:
        if ent in digit_ents:
            bank_det_entities[ent] = [val.replace(" ", "").replace("-", "").replace("\n", "") for val in
                                      bank_det_entities[ent]]
            bank_det_entities[ent] = [val for val in bank_det_entities[ent] if val.isnumeric()]
            if ent == "ABN":
                if "ABN" in bank_det_entities and bank_det_entities["ABN"]:
                    abn_with_digits = [abn for abn in bank_det_entities["ABN"] if
                                       any(char.isdigit() for char in abn)]  # Selecting values having digits
                    if abn_with_digits:
                        cleaned_abn_values = [''.join(filter(str.isdigit, abn)) for abn in abn_with_digits]
                        cleaned_abn_values = [abn.replace('gstno', '').replace('gst no', '').strip() for abn in
                                              cleaned_abn_values]
                        cleaned_abn_values = [abn for abn in cleaned_abn_values if validate_abn(abn)]
                        bank_det_entities["ABN"] = cleaned_abn_values

            bank_det_entities[ent] = list(set(bank_det_entities[ent]))

            if ent == "AccountNum":
                bank_det_entities[ent].sort(key=len, reverse=True)
        #     bank_det_entities[ent] = [text.translate(translator) for text in bank_det_entities[ent]]
    return bank_det_entities


def add_val_from_other_fields(other_fields, other_fields_key, bank_det_entities, bde_key):
    for val in other_fields[other_fields_key]:
        similar_existing_ent = process.extractOne(val, bank_det_entities[bde_key], scorer=fuzz.ratio, score_cutoff=80)
        if not similar_existing_ent:
            bank_det_entities[bde_key].append(val)
        else:
            if len(val) > len(similar_existing_ent[0]):
                bank_det_entities[bde_key].append(val)
    return False


def extract_abn_from_raw_text(raw_text, bank_det_entities):
    abn_regex = re.compile(r'ABN(?:/GST No.)?\s*(\d{7}\s*\d{4})') #Changed regex pattern to optionally include GST No. in the pattern
    matches = abn_regex.findall(raw_text)
    #Extend the ABN list with the extracted values from the regex pattern
    bank_det_entities['ABN'].extend(matches)
    if not matches:  # If no matches found, use different pattern to extract ABN
        abn_regex_patterns = [
            r'ABN:\s*(\d{2}\s*\d{3}\s*\d{3}\s*\d{3})',  # Pattern for ABN: 12 345 678 910
            r'ABN(\d{2})\s*(\d{3})\s*(\d{3})\s*(\d{3})', # Pattern for ABN12 345 678 910
            r'(A\.B\.N\.|ABN)\s*(\d{2})-(\d{3})-(\d{3})-(\d{3})', # Pattern for ABN 90-088-123-067 or A.B.N. 30-604-211-225
            r'ARN\s*(\d{2})\s*(\d{3})\s*(\d{2})\s*:\s*(\d{3})', # Pattern for ARN 82 268 19: 478
            r'A\.B\.N\.\s*(\d{11})',
            r'\b(\d{11})\b',
            r'(?:A\.B\.N\.:)\s*(\d{2})\s*(\d{3})\s*(\d{3})\s*(\d{3})\b'
        ]
        for pattern in abn_regex_patterns:
            matches = re.findall(pattern, raw_text)
            if matches:
                for match in matches:
                    abn = ''.join(match).replace(" ", "").replace("\n", "")
                    if len(abn) == 10:
                        # Checking raw text for a misread colon (:) and try to correct it
                        possible_abn_match = re.search(r'ARN\s*(\d{2})\s*(\d{3})\s*(\d{2})\s*[:]\s*(\d{3})', raw_text)
                        if possible_abn_match:
                            # Correct the ABN by inserting '1' AFTER the colon (Mindrill case)
                            corrected_abn = possible_abn_match.group(1) + possible_abn_match.group(
                                2) + possible_abn_match.group(3) + "1" + possible_abn_match.group(4)
                            abn = corrected_abn

                    bank_det_entities['ABN'].append(abn)
                break
    raw_abns = [''.join(filter(str.isdigit, line)) for line in raw_text.split('\n') if
                len(''.join(filter(str.isdigit, line))) == 11]
    bank_det_entities["ABN"].extend(raw_abns)
    print(f"Extracted ABN: {bank_det_entities['ABN']}")
    return bank_det_entities


def combine_bank_dets(entities, bank_dets_entities):
    if "ABN" in entities:
        bank_dets_entities["ABN"].append(entities["ABN"]["text"])
        del entities["ABN"]

    return entities, bank_dets_entities


def bank_details_from_other_fields(other_fields, bank_det_entities):
    if "account number" in other_fields:
        add_val_from_other_fields(other_fields, "account number", bank_det_entities, "AccountNum")
    if "account" in other_fields:
        add_val_from_other_fields(other_fields, "account", bank_det_entities, "AccountNum")
    if "a/c no" in other_fields:
        add_val_from_other_fields(other_fields, "a/c no", bank_det_entities, "AccountNum")
    if "a/c" in other_fields:
        add_val_from_other_fields(other_fields, "a/c", bank_det_entities, "AccountNum")
    if "account no" in other_fields:
        add_val_from_other_fields(other_fields, "account no", bank_det_entities, "AccountNum")
    if "acc" in other_fields:
        add_val_from_other_fields(other_fields, "acc", bank_det_entities, "AccountNum")
    if "abn" in other_fields:
        add_val_from_other_fields(other_fields, "abn", bank_det_entities, "ABN")
    if "a b n" in other_fields:
        add_val_from_other_fields(other_fields, "a b n", bank_det_entities, "ABN")
    if "abn no" in other_fields:
        add_val_from_other_fields(other_fields, "abn no", bank_det_entities, "ABN")
    if "a.b.n" in other_fields:
        add_val_from_other_fields(other_fields, "a.b.n", bank_det_entities, "ABN")
    if "a.b.n." in other_fields:
        add_val_from_other_fields(other_fields, "a.b.n.", bank_det_entities, "ABN")
    if "abn number" in other_fields:
        add_val_from_other_fields(other_fields, "abn number", bank_det_entities, "ABN")
    if "bsb" in other_fields:
        add_val_from_other_fields(other_fields, "bsb", bank_det_entities, "BSB")
    if "bsb number" in other_fields:
        add_val_from_other_fields(other_fields, "bsb number", bank_det_entities, "BSB")
    if "account name" in other_fields:
        add_val_from_other_fields(other_fields, "account name", bank_det_entities, "AccountName")
    if "cheque to" in str(other_fields.keys()):
        for index, key in enumerate(other_fields.keys()):
            if "cheque to" in str(key):
                add_val_from_other_fields(other_fields, key, bank_det_entities, "AccountName")
                break

    if "bank name" in other_fields:
        add_val_from_other_fields(other_fields, "bank name", bank_det_entities, "BankName")
    if "bank" in other_fields:
        add_val_from_other_fields(other_fields, "bank", bank_det_entities, "BankName")
    if "swift" in other_fields:
        add_val_from_other_fields(other_fields, "swift", bank_det_entities, "SwiftCode")
    if "swift code" in other_fields:
        add_val_from_other_fields(other_fields, "swift code", bank_det_entities, "SwiftCode")
    return bank_det_entities


def account_number_bank_entities(raw_text, bank_det_entities):
    account_num_match = re.search(r'Account:\s*((?:\d+\s*)+)', raw_text)
    if account_num_match:
        account_num = re.sub(r'\s+', '', account_num_match.group(1))
        if len(account_num)  > 4:
            bank_det_entities["AccountNum"].append(account_num)
    return bank_det_entities


def associate_bank_entities(raw_text, bank_det_entities):
    entities_sets = []
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    raw_text = raw_text.translate(translator)
    updated_bank_det_entities = {"ABN": [], "AccountNum": [], "AccountName": [], "BSB": [], "SwiftCode": [],
                                 "BankName": []}

    for ent in bank_det_entities:
        for item in bank_det_entities[ent]:
            updated_bank_det_entities[ent].append((item, raw_text.find(item)))

    for bsb in updated_bank_det_entities["BSB"]:
        bsb_text, bsb_start = bsb
        ent_set = {"BSB": bsb_text}
        dist_thresh = 250
        for ent in updated_bank_det_entities:
            if ent != "BSB":
                if updated_bank_det_entities[ent]:
                    closest_item = min(updated_bank_det_entities[ent], key=lambda item: abs(bsb_start - item[1]))
                    if closest_item and abs(closest_item[1] - bsb_start) < dist_thresh:
                        ent_set[ent] = closest_item[0]
        entities_sets.append(ent_set)

    return entities_sets


def extract_bank_details(entities,raw_text,other_fields):
    bank_details_placeholder = {"ABN": [], "AccountNum": [], "AccountName": [], "BSB": [], "SwiftCode": [],
                                "BankName": []}
    bank_dets_entities = spacy_inference.predict_bank_details(raw_text, bank_details_placeholder)
    print("ABN after inference: ", bank_dets_entities["ABN"])
    bank_dets_entities = bank_details_from_other_fields(other_fields, bank_dets_entities)
    print("ABN after other fields: ", bank_dets_entities["ABN"])
    bank_dets_entities = extract_abn_from_raw_text(raw_text, bank_dets_entities)
    print("ABN after raw text: ", bank_dets_entities["ABN"])
    # bank_dets_entities = process_info_blocks(raw_text, bank_dets_entities)
    entities, bank_dets_entities = combine_bank_dets(entities, bank_dets_entities)
    print("ABN after combining: ", bank_dets_entities["ABN"])
    bank_dets_entities = clean_bank_det_entities(bank_dets_entities)
    print("ABN after cleaning: ", bank_dets_entities["ABN"])
    bank_dets_entities = account_number_bank_entities(raw_text, bank_dets_entities)
    print("ABN after account number extraction: ", bank_dets_entities["ABN"])
    associated_bank_dets = associate_bank_entities(raw_text, bank_dets_entities)
    return bank_dets_entities,associated_bank_dets