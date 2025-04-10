import os
import uuid
import fitz
import base64
import tabula
import camelot
from PIL import Image
from src.utils import azure_utils

def get_page_count(filepath):
    # pdf = PdfFileReader(open(filepath,'rb'))
    # page_count = pdf.getNumPages()
    doc = fitz.open(filepath)
    count = doc.page_count
    doc.close()
    return count


def pdf_to_image_converter(pdf_path):
    zoom = 1  # to increase the resolution
    mat = fitz.Matrix(zoom, zoom)
    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        img_path = pdf_path + ".jpg"
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat)
        pix.save(img_path)
    doc.close()

    return img_path


def convert_pdf_to_image(pdf_path):
    try:
        print("PDF path: ", pdf_path)
        return pdf_to_image_converter(pdf_path)
    except Exception as e:
        print("Ran into exception: ", e)
        compress_pdf(pdf_path)
        print("Retrying after compressing")
        return pdf_to_image_converter(pdf_path)


def compress_pdf(pdf_path, zoom=1, replace=True, file_id=None, correlation_id=None):
    # Normalize path separators for the OS
    pdf_path = os.path.normpath(pdf_path)
    temp_pdf_path = os.path.normpath(pdf_path.replace(".pdf", "_compressed.pdf"))
    # Create a truly unique temp path in same directory
    temp_dir = os.path.dirname(pdf_path)
    temp_name = f"temp_{uuid.uuid4().hex}.pdf"
    temp_pdf_path = os.path.join(temp_dir, temp_name)
    compressed_paths = {'local': None, 'azure': None}

    try:
        with fitz.open(pdf_path) as pdf_document:
            print("Successfully opened source PDF")
            with fitz.open() as new_pdf:
                print("Created new PDF object")
                for page_num in range(len(pdf_document)):
                    page = pdf_document.load_page(page_num)
                    # Create a pixmap with reduced resolution and compression
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))  # Reduce to 85% resolution
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    # Create temporary image file with compression
                    temp_img_path = os.path.join(temp_dir, f"temp_img_{uuid.uuid4().hex}.jpg")
                    img.save(temp_img_path, "JPEG", quality=85)  # Adjust quality (1-100) to balance size/quality

                    # Add compressed image to new PDF
                    new_page = new_pdf.new_page(width=pix.width, height=pix.height)
                    new_page.insert_image(new_page.rect, filename=temp_img_path)

                    # Clean up temporary image
                    os.remove(temp_img_path)
                    print(f"Processed page {page_num + 1}")

                print(f"Attempting to save to {temp_pdf_path}")
                # Save with compression
                new_pdf.save(temp_pdf_path, garbage=3, deflate=True, clean=True)
                print("Successfully saved temp PDF")

        print("All PDF objects closed")
        if replace is True:
            # Replace original with temp file
            if os.path.exists(temp_pdf_path):
                try:
                    os.replace(temp_pdf_path, pdf_path)
                    print("Successfully replaced file")
                except Exception as e:
                    print(f"Failed to replace file: {e}")
                    os.remove(temp_pdf_path)  # Clean up temp file
                    raise
        else:
            if file_id is not None:
                azure_file_url, azure_path = azure_utils.upload_file_on_azure(temp_pdf_path, file_id,
                                                                              correlation_id, "compressed_output")
                compressed_paths['azure'] = azure_path
            compressed_paths['local'] = temp_pdf_path
            return compressed_paths
    except Exception as e:
        print(f"Error during compression: {str(e)}")
        if os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
                print("Cleaned up temp file")
            except Exception as cleanup_e:
                print(f"Failed to clean up temp file: {cleanup_e}")
        raise e


def split_pdfs(filepath, output_folder, split_points):
    print("Split points: ", split_points)
    split_pdfs_paths = []
    filename = filepath.split("/")[-1].split("\\")[-1]
    start = 0
    doc = fitz.open(filepath)
    for i, sp in enumerate(split_points):
        if "pdf" in filename:
            split_filename = filename.replace(".pdf", "_" + str(i + 1) + ".pdf")
        elif "PDF" in filename:
            split_filename = filename.replace(".PDF", "_" + str(i + 1) + ".PDF")
        else:
            # If the filename doesn't have pdf, assign a default split_filename
            split_filename = filename + "_" + str(i + 1) + ".pdf"
        split_filepath = os.path.join(output_folder, split_filename)
        end = sp
        new_doc = fitz.open()
        for page in (range(start, end)):
            new_doc.insert_pdf(doc, from_page=page, to_page=page)
        if new_doc.page_count > 0:
            new_doc.save(split_filepath, no_new_id=True)
            split_pdfs_paths.append(split_filepath)
        new_doc.close()
        start = end
    return split_pdfs_paths


def base64_encode(pdf, final_processing, file_id=None, correlation_id=None):
    compressed_file_path = None
    if pdf[-4:].lower() == ".pdf" and final_processing is True:
        compressed_pdf = compress_pdf(pdf, replace=False, file_id=file_id, correlation_id=correlation_id)
        pdf = compressed_pdf['local']
        if file_id is not None:
            compressed_file_path = compressed_pdf['azure']
    with open(pdf, "rb") as pdf_file:
        encoded_string = base64.b64encode(pdf_file.read()).decode('utf-8')
    if "temp_" in pdf:
        os.remove(pdf)

    return encoded_string, compressed_file_path


def extract_adj_no(filename):
    area = (82, 690, 82+82, 690+130)
    tables = tabula.read_pdf(filename, pages=1, area=area, guess=False)
    if tables:
        if "ADJ No." in tables[0].columns:
            return tables[0][tables[0].columns[1]][0]
    return None


def extract_employee_ids(filename):
    try:
        tables = camelot.read_pdf(filename, multiple_tables=True, flavor='lattice', pages='all')
        employee_ids = []
        employee_id_index = None
        for i, table in enumerate(tables):
            df = table.df
            print(f"Table {i + 1} Extracted DataFrame:\n", df)
            # Searching for employee ID index
            header_found = False
            if employee_id_index is None:
                for row_index, row in df.iterrows():
                    if 'Employee ID' in row.values:
                        employee_id_index = row.tolist().index('Employee ID')
                        print(f"'Employee ID' found in row {row_index + 1}, column {employee_id_index + 1}")
                        ids = df.iloc[row_index + 1:, employee_id_index].dropna().tolist()
                        ids = [id_ for id_ in ids if id_ != 'Employee ID']  # Remove column header
                        print(f"Extracted Employee IDs from table {i + 1}: {ids}")
                        employee_ids.extend(ids)
                        header_found = True  # Mark that header was found and processed
                        break

            # If no header is found, or it's a different table, extract column by index
            if employee_id_index is not None and not header_found:
                ids = df.iloc[:, employee_id_index].dropna().tolist()
                ids = [id_ for id_ in ids if id_ != 'Employee ID']
                print(f"Extracted Employee IDs from table {i + 1} using column index {employee_id_index}: {ids}")
                employee_ids.extend(ids)

        # employee_ids = list(dict.fromkeys(employee_ids))  # Remove Duplicates
        if not employee_ids:
            print("No 'Employee ID' values were found in the extracted tables.")
        return employee_ids

    except FileNotFoundError:
        print(f"File '{filename}' was not found.")
        return []
    except Exception as e:
        print(f"An error occurred while extracting data: {e}")
        return []


def get_fonts(pdf_path):
    doc = fitz.open(pdf_path)
    fonts = [page.get_fonts() for page in doc]
    print("Fonts: ", fonts)
    return fonts[0]


def check_scanned(pdf_path):
    fonts = get_fonts(pdf_path)
    if fonts:
        print("Likely a machine-generated PDF")
        return False
    else:
        print("Likely a scanned PDF (no fonts detected).")
        return True
    # else:
    #     print("Mixed content PDF (some pages contain images).")
