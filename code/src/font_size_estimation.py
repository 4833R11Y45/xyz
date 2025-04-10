""""As mentioned it will take two inputs 1. no of words and 2. bounding box"""
import numpy as np
from PIL import Image, ImageDraw


def estimate_font_size(bounding_box, num_words):
    # Get coordinates of the bounding box
    x1, y1, x2, y2, x3, y3, x4, y4 = bounding_box

    # Calculate height of bounding box (vertical height)
    box_height = y3 - y1

    # Calculate width of the bounding box (horizontal width)
    box_width = x2 - x1

    # Divide width by the number of words to get the approximate width of each character
    avg_char_width = box_width / num_words

    # Assume that the height of the bounding box corresponds to the font height (form recognizer ensures that)
    avg_font_size = box_height
    return avg_font_size, avg_char_width


