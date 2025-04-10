import sys
import os
import json
sys.path.append("../../")

from src import forms_recognizer
from src.utils import pdf_utils


def get_pdf_response(pdf, pdf_path):
    print("PDF file exists: ", os.path.isfile(os.path.join(pdf_path, pdf)))
    try:
        page_count = pdf_utils.get_page_count(os.path.join(pdf_path, pdf))
    except Exception as e:
        print("Skipping page count..")
        azure_response = forms_recognizer.get_response(os.path.join(pdf_path, pdf))
        return azure_response
    if page_count <= 3:
        azure_response = forms_recognizer.get_response(os.path.join(pdf_path, pdf))
        return azure_response
    else:
        print("PDF contains %s pages. Analysing PDF to identify if it contains multiple invoices" % page_count)
        responses = []
        split_points = pdf_utils.extract_text_and_find_split_points(os.path.join(pdf_path, pdf))
        print("Found %s invoices in the pdf document" % len(split_points))
        if split_points:
            split_pdfs_paths = pdf_utils.split_pdfs(pdf, pdf_path, split_points)
            print(split_pdfs_paths)
            for individual_pdf in split_pdfs_paths:
                print("Sending %s to Form Recognizer+AI Engine" % individual_pdf.split("/")[-1])
                azure_response = forms_recognizer.get_response(individual_pdf)
                responses.append(azure_response)
        else:
            azure_response = forms_recognizer.get_response(os.path.join(pdf_path, pdf))
            return azure_response

        return responses


def bulk_convert_pdf_to_azure_json(input_dir, output_dir):
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    input_files = sorted(os.listdir(input_dir))
    # input_files = [os.path.join(input_dir, ifile) for ifile in input_files]

    for input_file in input_files:
        print(input_file)
        if input_file[-4:]==".pdf":
            if not os.path.isfile(os.path.join(output_dir, input_file.replace(".pdf",".json"))):
                azure_response = get_pdf_response(input_file, input_dir)
                if isinstance(azure_response, dict):
                    with open(os.path.join(output_dir, input_file.replace(".pdf",".json")), "w") as f:
                        json.dump(azure_response, f)
                elif isinstance(azure_response, list):
                    for i, response in enumerate(azure_response):
                        with open(os.path.join(output_dir, input_file.replace(".pdf", str(i)+".json")), "w") as f:
                            json.dump(response, f)



def json_data(file_name):
    with open(file_name, "r") as f:
        data = json.load(f)
    return data


def json_raw_text(input_file):
    lines = []
    data = json_data(input_file)
    print(type(data))
    for page in data["analyzeResult"]["readResults"]:
        for line in page["lines"]:
            lines.append(line["text"]+ "\n")
    return lines


def bulk_convert_json_to_txt(input_dir, output_dir):
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    input_files = sorted(os.listdir(input_dir))
    input_files = [os.path.join(input_dir, ifile) for ifile in input_files]

    for input_file in input_files:
        print(input_file)
        lines = json_raw_text(input_file)
        with open(os.path.join(output_dir, input_file.split("\\")[-1].replace(".json", ".txt")), "w", encoding='utf-8') as f:
            f.writelines(lines)




# input_dir = "../../data/invoices/IPA"
# output_dir = "../../data/invoices/IPA_azure_text"
# raw_output_dir = "../../data/invoices/IPA_raw_text"


input_dir = "../../data/invoices/all old"
output_dir = "../../data/invoices/all_old_azure_text"
raw_output_dir = "../../data/invoices/all_old_raw_text"

bulk_convert_pdf_to_azure_json(input_dir, output_dir)
bulk_convert_json_to_txt(output_dir, raw_output_dir)



