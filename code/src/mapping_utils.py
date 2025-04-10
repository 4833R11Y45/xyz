import re

def get_version_structure(version='v2.1'):
    if version == 'v2.1':
        return 'documentResults', 'text', 'valueNumber'
    elif version == 'v3.1':
        return 'documents', 'content', 'valueCurrency'
    else:
        raise ValueError(f"Unsupported version: {version}")


def get_response_structure(version='v2.1'):
    if version == 'v2.1':
        return 'readResults', 'text', 'boundingBox'
    elif version == 'v3.1':
        return 'pages', 'content', 'polygon'
    else:
        raise ValueError(f"Unsupported version: {version}")


def get_currency(azure_response, raw_text, version, currency_field):
    currency_val = None
    currency_content = None
    container_key, text_or_content, value_type = get_version_structure(version)
    if currency_field in azure_response['analyzeResult'][container_key][0]['fields']:
        if value_type in azure_response['analyzeResult'][container_key][0]['fields'][currency_field]:
            if value_type == "valueNumber":
                currency_val = azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
                    value_type]
            else:
                currency_value = azure_response['analyzeResult'][container_key][0]['fields'][currency_field][value_type]
                if isinstance(currency_value, (list, dict)):
                    currency_val = currency_value["amount"]
                else: # For case where type of currency value is not dict or list
                    currency_value = None

        currency_content = azure_response['analyzeResult'][container_key][0]['fields'][currency_field][text_or_content]

        if value_type not in azure_response['analyzeResult'][container_key][0]['fields'][currency_field]:
            if text_or_content == "text":
                currency_content_cleaned = currency_content.replace("$", "").strip()
                # Using regex to find all valid numbers, considering thousand separators and decimal points
                number_matches = re.findall(r'(\d{1,3}(?:[\s,]\d{3})*(?:\.\d+)?)', currency_content_cleaned)
                values = [float(num.replace(" ", "").replace(",", "")) for num in number_matches]
                if values:
                    # If more than one value is present, select the maximum one
                    max_value = max(values)
                    azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
                        "valueNumber"] = max_value
                    azure_response['analyzeResult'][container_key][0]['fields'][currency_field]["type"] = "number"
                    azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
                        text_or_content] = currency_content
    if currency_field == "AmountDue" and currency_content is not None:
        if str(currency_content) not in raw_text:
            currency_val = None
            currency_content = None
    return currency_val, currency_content


def set_currency(azure_response, version, currency_field, value, content):
    container_key, text_or_content, value_type = get_version_structure(version)
    azure_response['analyzeResult'][container_key][0]['fields'][currency_field] = {}
    if value_type == "valueCurrency":
        azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
            value_type] = {"amount": value}
        azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
            "type"] = "currency"
        azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
            text_or_content] = content
    else:
        azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
            value_type] = value
        azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
            "type"] = "number"
        azure_response['analyzeResult'][container_key][0]['fields'][currency_field][
            text_or_content] = content


    return azure_response

