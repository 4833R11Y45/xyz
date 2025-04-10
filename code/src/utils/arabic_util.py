import os
import re
import unicodedata

# edit this to add more characters
_filename_ascii_strip_re = re.compile(r"[^A-Za-z0-9\u0600-\u06FF_.-]")
_windows_device_files = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(10)),
    *(f"LPT{i}" for i in range(10)),
}

def secure_filename(filename: str) -> str:
    # Normalize the filename to handle UTF-8 characters
    filename = unicodedata.normalize("NFKC", filename)

    # Replace path separators with spaces
    for sep in os.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")

    # Remove unsafe characters
    filename = str(_filename_ascii_strip_re.sub("", "_".join(filename.split()))).strip("._")

    # Ensure the filename is not a reserved device name on Windows
    if os.name == "nt" and filename and filename.split(".")[0].upper() in _windows_device_files:
        filename = f"_{filename}"

    return filename