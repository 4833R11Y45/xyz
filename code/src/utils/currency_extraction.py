import re


def find_currency_in_response(azure_response, container_key, text_or_content):
    if "CurrencyCode" in azure_response['analyzeResult'][container_key][0]['fields']:
        return azure_response['analyzeResult'][container_key][0]['fields']["CurrencyCode"][text_or_content]
    return ""


def find_currency(azure_response, raw_text, container_key, text_or_content):
    currencies = ['AUD','USD','GBP','EUR','JPY','SGD','HKD','QAR','CNY','TWD','PLN','NZD', 'DKK', 'CAD', 'PKR', 'AED', 'EURO']
    currency_val = ""
    for currency in currencies:
        matches = re.search(r'\b' + re.escape(currency) + r'\b', raw_text, re.IGNORECASE) # Ensure uppercase is returned
        if matches:
            currency_val = matches.group(0).upper()  # Ensure uppercase return
            if currency_val == 'EURO':
                currency_val = "EUR"
            break
        else:
            currency_val = find_currency_in_response(azure_response, container_key, text_or_content)
            if currency_val == "US Dollar":
                currency_val = 'USD'
            elif currency_val == "yen":
                currency_val = 'JPY'
            elif currency_val == "R.Y":
                currency_val = "SAR"

    if not currency_val:
        if "tapal" in raw_text.lower():
            currency_val = "PKR"
    return currency_val

