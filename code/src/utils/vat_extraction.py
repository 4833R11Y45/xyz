from src.utils import table_extraction
from src.ML import vat_classifier
from src.generativeai import helper_functions


def extract_vat_info(azure_response):
    invoice_tables, relevant_table_col_mapping = extract_relevant_tables(azure_response)
    if "Items" in azure_response['analyzeResult']['documents'][0]['fields']:
        items_len = len(azure_response['analyzeResult']['documents'][0]['fields']["Items"]["valueArray"])
        relevant_table_col_mapping = dict(sorted(relevant_table_col_mapping.items(), key=lambda x: sum(v is not None for v in x[1].values()), reverse=True))
        for table in relevant_table_col_mapping:
            if any(relevant_table_col_mapping[table].values()):
                if len(invoice_tables[table]) == 1 and items_len > 1:
                    azure_response = feed_vat_data_at_header_level(azure_response, relevant_table_col_mapping, invoice_tables)
                    break
                else:
                    new_col_names = dict(
                        zip(relevant_table_col_mapping[table].values(), relevant_table_col_mapping[table].keys()))
                    new_table = invoice_tables[table].rename(columns=new_col_names)
                    line_items_data = {"Items": new_table.to_dict("records")}
                    line_items_data = postprocess_vat_classifications(line_items_data)
                    azure_response = helper_functions.add_line_items(azure_response, line_items_data,
                                                                     detected_language="en", source="vat_classifier")
                    break
    else:
        azure_response = feed_vat_data_at_header_level(azure_response, relevant_table_col_mapping, invoice_tables)
    return azure_response


def extract_relevant_tables(azure_response):
    invoice_tables = table_extraction.extract_multipage_tables(azure_response)
    relevant_table_col_mapping = {}

    for table in invoice_tables:
        table_columns = invoice_tables[table].columns
        relevant_table_col_mapping[table] = vat_classifier.predict(table_columns)

    return invoice_tables, relevant_table_col_mapping



def feed_vat_data_at_header_level(azure_response, relevant_table_col_mapping, invoice_tables):
    print("Feeding vat data at header level..")
    for table in relevant_table_col_mapping:
        if any(relevant_table_col_mapping[table].values()):
            if len(table) == 1:
                for col in relevant_table_col_mapping:
                    azure_response[0]['analyzeResult']['documents'][0]['fields'][col] = {
                        "content": invoice_tables[table][col].iloc[0],
                        "type": "string",
                        "valueString": invoice_tables[table][col].iloc[0]
                    }
                break
    return azure_response


def postprocess_vat_fields(item):
    """
    Post-process VAT field classifications to handle common issues:
    - Swap vat_rate and vat_amount if they're mixed up
    - Verify amount_before_vat is less than amount_after_vat
    - Check VAT rate is within reasonable range

    Args:
        item (dict): Dictionary containing vat_rate, vat_amount, amount_before_vat, amount_after_vat

    Returns:
        dict: Corrected item dictionary
    """
    # Make a copy of the item to avoid modifying the original
    corrected = item.copy()

    # Handle missing values
    for field in ['vat_rate', 'vat_amount', 'amount_before_vat', 'amount_after_vat']:
        if field not in corrected:
            corrected[field] = None

    # Skip if both vat_rate and vat_amount are None
    if corrected['vat_rate'] is None and corrected['vat_amount'] is None:
        return corrected

    # Try to convert values to floats for comparison
    val_rate = try_parse_float(corrected['vat_rate'])
    val_amount = try_parse_float(corrected['vat_amount'])
    val_before = try_parse_float(corrected['amount_before_vat'])
    val_after = try_parse_float(corrected['amount_after_vat'])

    # 1. Check if vat_rate and vat_amount need to be swapped
    if val_rate is not None and val_amount is not None:
        # If vat_rate is larger than 20, it's probably the amount
        if val_rate > 20 and val_amount <= 20:
            corrected['vat_rate'], corrected['vat_amount'] = corrected['vat_amount'], corrected['vat_rate']
            val_rate, val_amount = val_amount, val_rate

        # If vat_amount has a % sign, it's probably the rate
        elif isinstance(corrected['vat_amount'], str) and '%' in corrected['vat_amount']:
            corrected['vat_rate'], corrected['vat_amount'] = corrected['vat_amount'], corrected['vat_rate']
            # Recalculate the values
            val_rate = try_parse_float(corrected['vat_rate'])
            val_amount = try_parse_float(corrected['vat_amount'])

    # 2. Check if vat_rate has proper % format (if it's a string)
    if isinstance(corrected['vat_rate'], str) and '%' not in corrected[
        'vat_rate'] and val_rate is not None and val_rate <= 20:
        corrected['vat_rate'] = f"{val_rate}%"

    # 3. Check for VAT rate reasonableness
    if val_rate is not None and val_rate > 20:
        # If we have a reasonable vat_amount value, swap them
        if val_amount is not None and val_amount <= 20:
            corrected['vat_rate'], corrected['vat_amount'] = corrected['vat_amount'], corrected['vat_rate']
            # Update our parsed values
            val_rate, val_amount = val_amount, val_rate
        else:
            # Otherwise, assume it's a misclassification - vat_rate should be around 5%
            corrected['vat_rate'] = "5%"

    # 4. Check if amount_before_vat and amount_after_vat need to be swapped
    if val_before is not None and val_after is not None and val_before > val_after:
        corrected['amount_before_vat'], corrected['amount_after_vat'] = corrected['amount_after_vat'], corrected[
            'amount_before_vat']

    # 5. Validate that amount_after_vat = amount_before_vat + vat_amount (approximately)
    if val_before is not None and val_after is not None and val_amount is not None and val_after > 0:
        expected_after = val_before + val_amount
        # If the difference is significant (more than 10%), something might be wrong
        if abs(expected_after - val_after) / val_after > 0.1:
            # Check if vat_amount could actually be a vat rate (like 5%)
            if val_amount <= 20 and val_rate is None:
                # Calculate what vat_amount should be based on rate
                calculated_vat = val_before * (val_amount / 100)
                expected_after = val_before + calculated_vat
                # If this explanation works better, vat_amount was actually a rate
                if abs(expected_after - val_after) / val_after <= 0.1:
                    corrected['vat_rate'] = f"{val_amount}%"
                    corrected['vat_amount'] = calculated_vat

    return corrected


def try_parse_float(value):
    """
    Try to convert a value to a float, handling common formatting issues.

    Args:
        value: The value to convert (string, number, or None)

    Returns:
        float or None: The parsed float value, or None if parsing failed
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    # Remove % sign if present
    clean_value = value.replace('%', '')

    # Remove currency symbols and other non-numeric characters
    clean_value = ''.join(c for c in clean_value if c.isdigit() or c in ['.', ',', '-'])

    # Replace commas with dots as decimal separators
    clean_value = clean_value.replace(',', '.')

    # Remove any space and ensure we have only one decimal point
    clean_value = clean_value.replace(' ', '')
    if clean_value.count('.') > 1:
        # Keep only the last decimal point
        parts = clean_value.split('.')
        clean_value = ''.join(parts[:-1]) + '.' + parts[-1]

    try:
        return float(clean_value)
    except (ValueError, TypeError):
        return None


def postprocess_vat_classifications(data):
    """
    Apply post-processing to a list of dictionaries with VAT classifications.

    Args:
        data (dict): Dictionary with an 'Items' list containing VAT classifications

    Returns:
        dict: Corrected data dictionary
    """
    if 'Items' not in data:
        return data

    corrected_data = data.copy()
    corrected_data['Items'] = [postprocess_vat_fields(item) for item in data['Items']]

    return corrected_data

