import os
import json
import openai
import re

from src.generativeai import helper_functions

openai.api_type = "azure"
openai.api_base = os.getenv('GPT_ENDPOINT')
openai.api_key = os.getenv('GPT_KEY')
openai.api_version = os.getenv('GPT_VERSION')

FIELDS = {"CustomerName": "string", "CustomerId": "string", "InvoiceId": "string",
          "InvoiceDate": "date", "DueDate": "date", "VendorName": "string", "VendorTaxId": "string",
          "VendorAddress": "string", "VendorAddressRecipient": "string", "CustomerAddress": "string",
          "CustomerTaxId": "string", "CustomerAddressRecipient": "string", "BillingAddress": "string",
          "BillingAddressRecipient": "string", "ShippingAddress": "string", "ShippingAddressRecipient": "string",
          "PaymentTerm": "string", "SubTotal": "currency", "InvoiceTotal": "currency",
          "AmountDue": "currency", "ServiceAddress": "string", "ServiceAddressRecipient": "string",
          "RemittanceAddress": "string", "RemittanceAddressRecipient": "string", "ServiceStartDate": "date",
          "ServiceEndDate": "date", "PreviousUnpaidBalance": "currency", "CurrencyCode": "string",
          "NTN": "string", "STRN": "string", "TotalTax": "currency", "PurchaseOrder": "string"} #temporarily took out total tax for arabic demo, also took out PO

ARABIC_CURRENCY_MAPPING = {"دولار أمريكى": "USD", "ريال": "YER", "دولار أمريكي": "USD", "دولار": "USD", "ريال يمني": "YER"}


def preprocess_chatgpt_response(chatgpt_response):
    if "CurrencyCode" in chatgpt_response:
        if chatgpt_response["CurrencyCode"] in ARABIC_CURRENCY_MAPPING:
            chatgpt_response["CurrencyCode"] = ARABIC_CURRENCY_MAPPING[chatgpt_response["CurrencyCode"]]

    if "VendorName" in chatgpt_response:
        if chatgpt_response["VendorName"] is not None:
            chatgpt_response["VendorName"] = chatgpt_response["VendorName"].split("\n")[0]

    return chatgpt_response


def extract_invoice_data(ocr_text, detected_language):
    lang = ""
    if detected_language == "ar":
        lang = " Arabic"
    try:
        response = openai.ChatCompletion.create(
            engine="ocr-extraction-model",
            messages=[
                {"role": "system",
                 "content": """You are an AI assistant that is tasked with extracting invoice data from raw text of invoice 
                        in different languages. It should try and extract the following fields from the invoice raw text:
                        VendorName, CustomerName, CustomerId, PurchaseOrder, InvoiceId, InvoiceDate, DueDate, CurrencyCode,
                        VendorAddress, VendorAddressRecipient, CustomerAddress, CustomerTaxId, CustomerAddressRecipient,
                         ShippingAddress, ShippingAddressRecipient, PaymentTerm, SubTotal,
                        TotalTax, InvoiceTotal, AmountDue, ServiceAddress, ServiceAddressRecipient, RemittanceAddress,
                        RemittanceAddressRecipient, ServiceStartDate, ServiceEndDate, PreviousUnpaidBalance, 
                        KVKNumber(NL-only), PaymentDetails, TotalDiscount, TaxItems (en-IN only).
                        It should also extract Items including Description, Amount, Quantity, Unit Price, ProductCode, Unit, Date, 
                        Tax and TaxRate along with extraction confidence. 
                        In case CustomerAddress isn't directly mentioned, use Ship To as CustomerAddress along with country.
                        Pick the first instance of the Vendor Name (usually at the begining of the invoice).
                        Don't put periods at the end of the field value.
                        The format of response should JSON containing the fields that it was able to extract.
                        """},
                {"role": "user",
                 "content": f"Please extract invoice data fields from the raw text of an{lang} invoice: '{ocr_text}'"}
            ], seed=1234, top_p=0.1)

        return response['choices'][0]['message']['content']
    except openai.error.InvalidRequestError:
        return None


def extract_po(ocr_text):
    try:
        response = openai.ChatCompletion.create(
            engine="ocr-extraction-model",
            messages=[
                {"role": "system",
                 "content": """You are an AI assistant tasked with extracting Purchase Order numbers from raw text of invoices.
                        These could be labelled as purchase order or purchase order numbers. If that isn't found then
                        you can look for some kind of order number.
                        The response should be in JSON format containing the extracted PurchaseOrder value.
                        """},
                {"role": "user",
                 "content": f"Please extract the PurchaseOrder number from the raw text of the invoice: '{ocr_text}'"}
            ],
            seed=4321,
            temperature=0.0
        )

        # Check if the response contains valid data
        if response and 'choices' in response and response['choices']:
            content = response['choices'][0]['message']['content']
            # Check if the content is not empty
            if content.strip():
                print("Raw PO num response: ", content)
                return json.loads(content)
    except openai.error.InvalidRequestError as e:
        print("OpenAI API Error:", e)

    return None



def extract_dc_no(ocr_text):
    try:
        response = openai.ChatCompletion.create(
            engine="ocr-extraction-model",
            messages=[
                {"role": "system",
                 "content": """You are an AI assistant tasked with extracting delivery challan numbers or dispatch numbers from raw invoice text.
                                 Extraction Criteria:
                                 - Extract a number only if it is explicitly labeled with one of the following terms:
                                 - "delivery challan number", "dc number", "d.c. no", "dc#", "DC #", "Delivery Challan #", "dispatch number" (case insensitive).
                                 - The label must appear near the number, ensuring it is clearly associated.
                                 - Do not extract numbers that are unlabeled or only inferred based on their format.
                                 - If multiple valid labels are found in the invoice, extract and append the associated numbers in a list.
                                 Output Format:
                                 Return a JSON object with the extracted values:
                                 {
                                  "delivery_challan_numbers": ["123456", "789012"]
                                 }
                                 If no valid delivery challan labels are found, return:
                                 {
                                  "delivery_challan_numbers": []
                                 }"""}
                ,
                {"role": "user",
                 "content": f"Please extract the delivery challan number from the raw text of the invoice: '{ocr_text}'"}
            ],
            seed=4321,
            temperature=0.0
        )

        # Check if the response contains valid data
        if response and 'choices' in response and response['choices']:
            content = response['choices'][0]['message']['content']
            # Check if the content is not empty
            if content.strip():
                print("Raw DC num response: ", content)
                return json.loads(content)
    except openai.error.InvalidRequestError as e:
        print("OpenAI API Error:", e)

    return None

def extract_withholding_tax_amount(ocr_text):
    try:
        response = openai.ChatCompletion.create(
            engine="ocr-extraction-model",
            messages=[
                {"role": "system",
                 "content": """You are an AI assistant tasked with extracting withholding tax amounts from raw text of invoices.
                        These could be labelled as withholding tax, WH Tax, tax amount, etc.
                        The response should be in JSON format containing the extracted withholding tax amount.
                        """},
                {"role": "user",
                 "content": f"Please extract the withholding tax amount from the raw text of the invoice: '{ocr_text}'"}
            ],
            seed=4321,
            temperature=0.0
        )

        # Check if the response contains valid data
        if response and 'choices' in response and response['choices']:
            content = response['choices'][0]['message']['content']
            # Check if the content is not empty
            if content.strip():
                print("Raw WHT response: ", content)
                # semicolon_idx = content.find(":")
                # closing_bracket_idx = content.find("}")
                # if len(content) > semicolon_idx:
                #     if content[semicolon_idx+2] != '"' and content[closing_bracket_idx-2] != '"':
                #         updated_content = content[:(semicolon_idx+2)]+'"'+content[(semicolon_idx+2):(closing_bracket_idx-1)]+'"'+content[(closing_bracket_idx-1):]
                #         content = updated_content
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    # Attempting to correct the formatting issues before parsing
                    content = re.sub(r"([a-zA-Z0-9_]+):", r'"\1":', content)
                    content = re.sub(r":\s*([a-zA-Z0-9_]+)", r': "\1"', content)
                    print("JSON Decoding Error after correction:", e)
                    print("Corrected WHT content:", content)
    except openai.error.InvalidRequestError as e:
        print("OpenAI API Error:", e)

    return None


def extract_trn(ocr_text):
    try:
        response = openai.ChatCompletion.create(
            engine="ocr-extraction-model",
            messages=[
                {"role": "system",
                 "content": """You are an AI assistant tasked with extracting Tax Registration Number for the vendor 
                        as well as the customer from raw text of invoices.
                        These are usually labelled as Tax Registration Number, TRN, TRN No, VAT Registration Number or
                        Tax TD No. or رقم التسجیل الضریبي
                        The response should be in JSON format containing the extracted TRN Number.
                        """},
                {"role": "user",
                 "content": f"Please extract the tax registration number for the customer as well as the vendor from the raw text of the invoice: '{ocr_text}'"}
            ],
            seed=4321,
            temperature=0.0
        )

        # Check if the response contains valid data
        if response and 'choices' in response and response['choices']:
            content = response['choices'][0]['message']['content']
            # Check if the content is not empty
            if content.strip():
                print("Raw TRN response: ", content)
                # semicolon_idx = content.find(":")
                # closing_bracket_idx = content.find("}")
                # if len(content) > semicolon_idx:
                #     if content[semicolon_idx+2] != '"' and content[closing_bracket_idx-2] != '"':
                #         updated_content = content[:(semicolon_idx+2)]+'"'+content[(semicolon_idx+2):(closing_bracket_idx-1)]+'"'+content[(closing_bracket_idx-1):]
                #         content = updated_content
                return json.loads(content)
    except openai.error.InvalidRequestError as e:
        print("OpenAI API Error:", e)

    return None


def update_fields_using_genai(azure_response, detected_language):
    ocr_text = azure_response['analyzeResult']['content']
    chatgpt_response = extract_invoice_data(ocr_text, detected_language)
    if chatgpt_response is not None:
        chatgpt_response = chatgpt_response.replace("\\n", " ")
    print ("Raw chatgpt response: ", chatgpt_response)
    if chatgpt_response is not None:
        try:
            chatgpt_response_json = json.loads(chatgpt_response)
        except json.decoder.JSONDecodeError:
            print ("Inside json exception handling")
            # try:
            #     start_of_json = [m.start() for m in re.finditer('{', chatgpt_response)][0]
            #     end_of_json = [m.start() for m in re.finditer('}', chatgpt_response)][0]
            #     chatgpt_response_json = json.loads(chatgpt_response[start_of_json:end_of_json + 1])
            # except json.decoder.JSONDecodeError:
            return azure_response
        print("Chat gpt extraction response: ", chatgpt_response_json)
        chatgpt_response_json = preprocess_chatgpt_response(chatgpt_response_json)
        # if "PurchaseOrder" not in chatgpt_response_json:
        #     po_num_response = extract_po(ocr_text)
        print("Updated Chat gpt extraction response: ", chatgpt_response_json)
        for field in FIELDS:
            azure_response = helper_functions.add_field_value(azure_response, chatgpt_response_json, detected_language, field, FIELDS[field])
        azure_response = helper_functions.add_line_items(azure_response, chatgpt_response_json, detected_language)
        azure_response = helper_functions.hardcoding_for_1_arabic_invoice(azure_response)

    if "tapal" in ocr_text.lower():
        dc_num_response = extract_dc_no(ocr_text)
        dc_num_fields = ["dc_number", "delivery_challan_number", "delivery_challan_numbers"]
        if dc_num_response is not None:
            for field in dc_num_fields:
                if field in dc_num_response:
                    azure_response['analyzeResult']['documents'][0]['fields']['ShipmentNumber'] = {
                        "type": "string",
                        "valueString": dc_num_response[field],
                        "content": dc_num_response[field]
                    }

    if "tapal" in ocr_text.lower() or "ptcl" in ocr_text.lower():
        withholding_tax_response = extract_withholding_tax_amount(ocr_text)
        print("Withholding Tax Amount:", withholding_tax_response)
        if withholding_tax_response is not None:
            if "withholding_tax_amount" in withholding_tax_response:
                withholding_tax_amount = withholding_tax_response['withholding_tax_amount']

                # Assuming line items are in azure_response['analyzeResult']['documents'][0]['fields']['Items']
                if 'Items' in azure_response['analyzeResult']['documents'][0]['fields']:
                    for item in azure_response['analyzeResult']['documents'][0]['fields']['Items']['valueArray']:
                        if 'content' in item and "W.H. Tax" in item['content']:
                            if 'Tax' in item['valueObject']:
                                item['valueObject']['Tax'] = {
                                    "type": "string",
                                    "valueString": withholding_tax_amount,
                                    "content": withholding_tax_amount
                                }
                            else:
                                item['valueObject']['Tax'] = {
                                    "type": "string",
                                    "valueString": withholding_tax_amount,
                                    "content": withholding_tax_amount
                                }

    if "abu dhabi" in ocr_text.lower() or "uae" in ocr_text.lower() or "united arab emirates" in ocr_text.lower() or "adcb" in ocr_text.lower():
        trn_num_response = extract_trn(ocr_text)
        if trn_num_response is not None:
            if "customer_TRN" in trn_num_response:
                azure_response['analyzeResult']['documents'][0]['fields']['customer_TRN'] = {
                "type": "string",
                "valueString": trn_num_response['customer_TRN'],
                "content": trn_num_response['customer_TRN']}
            if "vendor_TRN" in trn_num_response:
                azure_response['analyzeResult']['documents'][0]['fields']['vendor_TRN'] = {
                "type": "string",
                "valueString": trn_num_response['vendor_TRN'],
                "content": trn_num_response['vendor_TRN']}

    return azure_response
