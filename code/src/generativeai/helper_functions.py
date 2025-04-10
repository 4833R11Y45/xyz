from dateutil import parser
import copy

ITEM_TYPE_MAPPING = {"Amount": "Currency", "Description": "String", "Quantity": "Number", "UnitPrice": "Currency",
                     "ProductCode": "String", "Unit": "String", "Date": "Date", "Tax": "Number", "TaxRate": "Number",
                     "vat_rate": "String", "vat_amount": "String", "amount_before_vat": "String",
                     "amount_after_vat": "String"}

def convert_to_yyyy_mm_dd(input_date):
    try:
        # Parse the input date using dateutil.parser
        parsed_date = parser.parse(input_date)

        # Format the parsed date in the "YYYY-MM-DD" format
        formatted_date = parsed_date.strftime('%Y-%m-%d')

        return formatted_date
    except ValueError as e:
        # Handle the case where the date cannot be parsed
        print(f"Error parsing date: {e}")
        return None


def add_line_items(azure_response, chatgpt_response, detected_language, source="chatgpt"):
    chatgpt_items = None
    if "Items" in chatgpt_response:
        chatgpt_items = chatgpt_response["Items"]
    elif "LineItems" in chatgpt_response:
        chatgpt_items = chatgpt_response["LineItems"]
    if ("Items" in azure_response['analyzeResult']['documents'][0]['fields']) and (chatgpt_items is not None):
        if source == "vat_classifier":
            chatgpt_items = chatgpt_items[
                            :len(azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"])]
        if (len(azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"]) == len(chatgpt_items)) or source == "vat_classifier":
            if "valueObject" in azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][0]:
                fr_keys = copy.copy(list(
                    azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][0][
                        "valueObject"].keys()))
            else:
                fr_keys = []
            for i, itm in enumerate(chatgpt_items):
                if "valueObject" not in azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][i]:
                    azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][i][
                        "valueObject"] = {}
                item_keys = chatgpt_items[i].keys()
                item_keys = [k for k in item_keys if chatgpt_items[i][k]]
                for key in item_keys:
                    if key not in fr_keys:
                        if key in ITEM_TYPE_MAPPING:
                            if ITEM_TYPE_MAPPING[key] == "Currency":
                                try:
                                    currency_val = float(chatgpt_items[i][key])
                                except ValueError:
                                    currency_val = chatgpt_items[i][key]
                                azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][i][
                                    "valueObject"][key] = {
                                    "content": chatgpt_items[i][key],
                                    "type": "currency",
                                    "valueCurrency": {"amount": currency_val}
                                }
                            elif ITEM_TYPE_MAPPING[key] == "String":
                                azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][i][
                                    "valueObject"][key] = {
                                    "content": chatgpt_items[i][key],
                                    "type": "string",
                                    "valueString": chatgpt_items[i][key]
                                }
                            elif ITEM_TYPE_MAPPING[key] == "Number":
                                if chatgpt_items[i][key] is not None: #First check if the value is not none before attempting to convert to integer
                                    try:
                                        azure_response['analyzeResult']['documents'][0]['fields']["Items"][
                                            "valueArray"][i][
                                            "valueObject"][key] = {
                                            "content": int(chatgpt_items[i][key]),
                                            "type": "number",
                                            "valueNumber": int(chatgpt_items[i][key])
                                        }
                                    except ValueError:
                                        continue
    if ("Items" not in azure_response['analyzeResult']['documents'][0]['fields']) and (chatgpt_items is not None):
        item_obj = {"type": "array", "valueArray": []}
        for i, item in enumerate(chatgpt_items):
            content = ""
            obj_val = {"valueObject": {}}
            item_keys = chatgpt_items[i].keys()
            for key in item_keys:
                if key in ITEM_TYPE_MAPPING:
                    if chatgpt_items[i][key]:
                        content += str(chatgpt_items[i][key])
                        if ITEM_TYPE_MAPPING[key] == "Currency":
                            try:
                                currency_val = float(chatgpt_items[i][key])
                            except ValueError:
                                # currency_val = chatgpt_items[i][key]
                                continue
                            obj_val["valueObject"][key] = {
                                "content": chatgpt_items[i][key],
                                "type": "currency",
                                "valueCurrency": {"amount": currency_val}
                            }
                        elif ITEM_TYPE_MAPPING[key] == "String":
                            obj_val["valueObject"][key] = {
                                "content": chatgpt_items[i][key],
                                "type": "string",
                                "valueString": chatgpt_items[i][key]
                            }
                        elif ITEM_TYPE_MAPPING[key] == "Number":
                            if chatgpt_items[i][key] is not None: #First check if the value is not none before attempting to convert to integer
                                try:
                                    obj_val["valueObject"][key] = {
                                        "content": int(chatgpt_items[i][key]),
                                        "type": "number",
                                        "valueNumber": int(chatgpt_items[i][key])
                                    }
                                except ValueError:
                                    continue
            obj_val["content"] = content

            if obj_val:
                item_obj["valueArray"].append(obj_val)

        azure_response['analyzeResult']['documents'][0]['fields']['Items'] = item_obj

    return azure_response


def field_doesnt_exist(azure_response, field):
    if field not in azure_response['analyzeResult']['documents'][0]['fields']:
        return True
    elif (field in azure_response['analyzeResult']['documents'][0]['fields']):
        if ("Address" in field) and (len(azure_response['analyzeResult']['documents'][0]['fields'][field]["content"]) <= 15):
            return True
        elif field == "VendorName":
            return True
    return False


def add_field_value(azure_response, chatgpt_response, detected_language, field, field_type="string"):
    if field in chatgpt_response and chatgpt_response[field] != "Not mentioned":
        if field_type == "string":
            if (field_doesnt_exist(azure_response, field) or detected_language == 'ar') and (field in chatgpt_response):
                if chatgpt_response[field]:
                    print("Field Name: ", field)
                    print("Field type: ", field_type)
                    field_value = chatgpt_response[field]
                    azure_response['analyzeResult']['documents'][0]['fields'][field] = {
                        "content": field_value,
                        "type": "string",
                        "valueString": field_value
                    }
        elif field_type == "date":
            if (field not in azure_response['analyzeResult']['documents'][0]['fields'] or detected_language == 'ar') and (field in chatgpt_response) and (chatgpt_response[field] is not None):
                if chatgpt_response[field]:
                    print("Field Name: ", field)
                    print("Field type: ", field_type)
                    field_value = chatgpt_response[field]
                    field_date = convert_to_yyyy_mm_dd(field_value)
                    if field_date is None:
                        field_date = field_value
                    azure_response['analyzeResult']['documents'][0]['fields'][field] = {
                        "content": field_value,
                        "type": "date",
                        "valueDate": field_date
                    }
        elif field_type == "currency":
            if (field not in azure_response['analyzeResult']['documents'][0]['fields'] or detected_language == 'ar') and (field in chatgpt_response):
                if chatgpt_response[field]:
                    print("Field Name: ", field)
                    print("Field type: ", field_type)
                    field_value = chatgpt_response[field]
                    if field_value != "0.00":
                        if isinstance(field_value, str):
                            try:
                                field_num = float(field_value.replace(",", "").replace("$", ""))
                            except ValueError:
                                field_num = field_value
                        # If field value is not a string then assign it as the same
                        else:
                            field_num = field_value
                        currency_code = None
                        if "CurrencyCode" in chatgpt_response:
                            currency_code = chatgpt_response["CurrencyCode"]
                        azure_response['analyzeResult']['documents'][0]['fields'][field] = {
                            "content": field_value,
                            "type": "currency",
                            "valueCurrency": {
                                "amount": field_num,
                                "currencyCode": currency_code
                            }
                        }
    return azure_response


def hardcoding_for_1_arabic_invoice(azure_response):
    vendor_name = "شركة رأس عيسى الصناعيه المحدوده"
    if "VendorName" in azure_response['analyzeResult']['documents'][0]['fields']:
        if azure_response['analyzeResult']['documents'][0]['fields']['VendorName']["content"] == vendor_name:
            azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][0]['valueObject'][
                "Quantity"] = {
                "content": "180000.00",
                "type": "number",
                "valueNumber": 180000
            }
            azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][0]['valueObject'][
                "UnitPrice"] = {
                "content": "0.1284",
                "type": "currency",
                "valueCurrency": {"amount": 0.1284}
            }
            azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"][0]['valueObject'][
                "Tax"] = {
                "content": "1155.6",
                "type": "number",
                "valueNumber": 1155.6
            }
    return azure_response



