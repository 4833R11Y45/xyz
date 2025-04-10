import pyodbc


def connect_db():
    conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};'
                          'SERVER=database.gslsolutions.com.au;'
                          'DATABASE=SpendConsoleTestDb;'
                          'UID=spendconsole-login;'
                          'PWD=jg!pff$ePtRR8D?4;')
    return conn


def get_json_filename(invoice_id, conn):
    cursor = conn.cursor()

    query = f"SELECT AnalyzeResultFileName FROM [dbo].[ProcessedInvoices] WHERE Id = '{invoice_id}'"
    cursor.execute(query)

    result = cursor.fetchone()

    cursor.close()

    if result and result.AnalyzeResultFileName:
        analyze_result_file_name = result.AnalyzeResultFileName
        analyze_result_file_name = analyze_result_file_name.split('.')[0] + '.json'
        return analyze_result_file_name
    else:
        return None


def get_processed_invoice_data(invoice_id, fields, conn):
    data = None
    cursor = conn.cursor()
    # fields = ['AnalyzeResultFileName', 'BillingAddress', 'BillingAddressRecipient', 'CustomerAbn', 'CustomerAddress',
    #           'CustomerAddressRecipient', 'CustomerName', 'DueDate', 'InvoiceDate', 'InvoiceNumber', 'InvoiceType',
    #           'OriginalInvoiceTotal', 'PurchaseOrder', 'RemittanceAddress', 'RemittanceAddressRecipient', 'SubTotal',
    #           'SupplierAbn', 'Tax', 'Total', 'VendorAddress', 'VendorAddressRecipient', 'VendorName', 'Version']
    item_flag = False
    if "Items" in fields:
        item_flag = True
        fields.remove("Items")
    fields.append('AnalyzeResultFileName')
    fields = ", ".join(fields)

    query = f"SELECT {fields} FROM [dbo].[ProcessedInvoices] WHERE Id = '{invoice_id}'"
    cursor.execute(query)

    result = cursor.fetchone()

    # cursor.close()

    if result and result.AnalyzeResultFileName:
        data = dict(zip([column[0] for column in cursor.description], result))
        # analyze_result_file_name = result.AnalyzeResultFileName
        # analyze_result_file_name = analyze_result_file_name.split('.')[0] + '.json'
        if item_flag is True:
            items_query = f"SELECT Amount, Description, Quantity, UnitPrice, Unit, TaxCategory, TaxPercentage FROM [dbo].[ProcessedInvoiceLineItems] WHERE ProcessedInvoiceId = '{invoice_id}'"
            cursor.execute(items_query)
            items_result = cursor.fetchall()
            items_data = [dict(zip([column[0] for column in cursor.description], row)) for row in items_result]
            data['Items'] = items_data
    cursor.close()
    return data
