import os
import json
import traceback

from processor import process_invoice, process_single_invoice

inv_dir = "old_data/old/invoices/IPA/Invoices for Bloom 10 June 2022 batch 2"
output_dir = "data/Invoices for Bloom 10 June 2022 batch 2 API output"
if not os.path.isdir(output_dir):
    os.mkdir(output_dir)

invoices = os.listdir(inv_dir)
# invoices = [os.path.join(inv_dir, inv) for inv in invoices]
failed_files_path = "failed_files.txt"
failed_files = []

for inv in invoices:
    if inv[-4:].lower() == ".pdf":
        print("Processing: ", inv)
        try:
            output = process_invoice(os.path.join(inv_dir, inv), inv_dir)
            with open(os.path.join(output_dir, inv+".json"), "w") as f:
                json.dump(output, f)
        except Exception:
            failed_files.append(inv)
            print(traceback.format_exc())

with open(failed_files_path, "a") as f:
    f.writelines(failed_files)



