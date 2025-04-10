import openai
import os

openai.api_type = "azure"
openai.api_base = os.getenv('GPT_ENDPOINT')
openai.api_key = os.getenv('GPT_KEY')
openai.api_version = os.getenv('GPT_VERSION')


def llm_response(ocr_text, exceptions,extracted_values):
    response = openai.ChatCompletion.create(
        engine="exception-resolution",
        # messages=[
        #     {"role": "system", "content": "Given invoice text, extracted values and extraction exceptions (such as "
        #                                   "inaccurately extracted line items, discrepancies in total amount, "
        #                                   "or other extraction issues), analyze the Invoice Text and extracted values and"
        #                                   "identify the incorrectly extracted values. Extract the correct values from Invoice Text to resolve exceptions."
        #                                   "Return updated values and updated line items in case of previous incorrect extractions, in Updated Values field."
        #                                   "Most of the exceptions occur because lineitems were inaccurately extracted"
        #                                   " resulting in discrepancy in associated values e.g tax and total."
        #                                   # "To resolve the exceptions extract all line items accurately "
        #                                   # "and calculate other elements (e.g tax, total amount etc.) only using them. Return all the extracted line"
        #                                   # "items (with exception or without exceptions) and their associated information in Updated Values."
        #                                   "An invoice can have multiple exceptions which are seperated by semicolon."
        #                                   "The format of response should in JSON and must follow below structure, donot"
        #                                   " send anything else in response:"
        #                                   "{Total Exceptions: value"
        #                                   "Exceptions Resolved: value"
        #                                   "Updated Values : values"
        #                                   "Description for resolved exceptions: how you resolved the exceptions,list all the values used in resolving exceptions."
        #                                   "Errors Encountered: value}."},
        #     {"role": "user", "content": "Resolve below encountered exceptions in invoice processing: "
        #                                 f"Exceptions:{exceptions} \n Invoice Text: {ocr_text} \n Extracted Values: {extracted_values}."
        #                                 f"Return valid json as a response."},
        # ]
        messages=[
            {"role": "system", "content": "You are an AI Assistant that helps extract information from invoices and help fix already extracted information. The response should be a valid JSON and not contain anything outside the JSON"},
            {"role": "user", "content": f"Here is the raw text from an invoice: {ocr_text} \n"
                                        f"Here are the values that were previously extracted: {extracted_values} \n"
                                        f"We have a system that gave the following exceptions: {exceptions} \n"
                                        "Can you extract information from the invoice raw text and use that extracted information to rectify some of the "
                                        "exceptions?"
                                        "For more context on the exceptions, please note that usually the items field in the response has inaccurate values"
                                        "Either some of the items are missed or some times incorrectly additional i.e. non-existent items are extracted."
                                        "Therefore, extracting the correct line items (descriptions, amount, quantity, unit price, tax) resolves issues "
                                        "with orginial vs calculated total mismatch and original vs calculated tax mismatch. "
                                        "The format of response should strictly be a valid JSON and must follow below structure and not send anything else in response"
                                        "{Total Exceptions: value"
                                        "Exceptions Resolved: value"
                                        "Previous Values: value"
                                        "Updated Values : values"
                                        "Description for resolved exceptions: Your reasoning in a string behind updating or not updating values and detailed overview"
                                        "Errors Encountered: value"
                                        "Value Type: The value which was changed such as the CustomerName, ABN etc"
                                        "Change Type: What type of change has occurred such as create, update or delete."},
        ],
        temperature=0.2
    )
    return response['choices'][0]['message']['content']



