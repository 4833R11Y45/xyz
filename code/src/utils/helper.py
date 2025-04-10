import os
import hashlib


def check_md5sum(file_path):
    md5sum = hashlib.md5(open(file_path,'rb').read()).hexdigest()
    return md5sum

def get_path(target_dir, file_name):
    target_dir = os.path.abspath(target_dir)
    return os.path.join(target_dir, file_name)


def is_not_float_string(value):
    # Check if a string represents a float
    try:
        num = float(value.replace(",", "")) # First replace any commas present
        return num.is_integer()
    except ValueError:
        return True
