#!/usr/bin/env python3
"""
Invoice Table Processor

This script extracts tables from invoice data, especially handling multi-page tables.
It works with various input formats including JSON and text files containing embedded tables.
It now supports both vertical tables (traditional) and horizontal tables (key-value format).

Usage:
    python invoice_table_processor.py input_file [output_dir]

Arguments:
    input_file: Path to the input file containing invoice data
    output_dir: (Optional) Directory to save output files (default: current directory)
"""

import json
import re
import pandas as pd
import os
import sys
from typing import List, Dict, Union


def is_horizontal_table(table: dict) -> bool:
    """
    Determine if a table is likely a horizontal key-value table.

    Args:
        table: Table dictionary with 'cells' property

    Returns:
        bool: True if the table appears to be a horizontal key-value table
    """
    if 'cells' not in table or not table['cells']:
        return False

    # Group cells by column
    columns = {}
    for cell in table['cells']:
        col_idx = cell.get('columnIndex', 0)
        if col_idx not in columns:
            columns[col_idx] = []
        columns[col_idx].append(cell)

    # Check characteristics of a horizontal table:
    # 1. First column has distinct values (potential keys)
    # 2. Content in first column looks like labels
    if 0 not in columns or len(columns) < 2:
        return False

    first_col = columns[0]

    # Check if first column has reasonable number of potential keys
    if len(first_col) < 3 or len(first_col) > 20:
        return False

    # Count potential key-like texts in first column
    label_keywords = ['invoice', 'date', 'number', 'total', 'amount', 'customer',
                      'reference', 'payment', 'due', 'bill', 'ship', 'address']

    key_like_count = 0
    for cell in first_col:
        content = cell.get('content', '').lower().strip()
        if any(keyword in content for keyword in label_keywords) or content.endswith(':'):
            key_like_count += 1

    # If a significant portion looks like keys, it's likely a horizontal table
    return key_like_count >= min(3, len(first_col) / 2)


def extract_horizontal_table(table: dict) -> pd.DataFrame:
    """
    Process a horizontal table (key-value format) where keys are in the left column
    and values are in the right column(s).

    Args:
        table: Table dictionary with 'cells' property

    Returns:
        DataFrame with keys as column names and values as a single row
    """
    if 'cells' not in table or not table['cells']:
        return pd.DataFrame()

    # Group cells by row
    rows_data = {}
    for cell in table['cells']:
        row_idx = cell.get('rowIndex', 0)
        col_idx = cell.get('columnIndex', 0)
        content = cell.get('content', '').strip()

        if row_idx not in rows_data:
            rows_data[row_idx] = {}

        rows_data[row_idx][col_idx] = content

    # Check if this is likely a horizontal table
    # Characteristic: First column contains label-like text, other columns have values
    key_candidates = []
    for row_idx, row in rows_data.items():
        if 0 in row:  # Check first column
            # Labels often contain keywords like 'number', 'date', 'total', etc.
            label_keywords = ['invoice', 'date', 'number', 'total', 'amount', 'customer',
                              'reference', 'payment', 'due', 'bill', 'ship', 'address']
            text = row[0].lower()
            if any(keyword in text for keyword in label_keywords):
                key_candidates.append(row_idx)

    # If few key candidates found, it's probably not a horizontal table
    if len(key_candidates) < 3 and len(rows_data) > 5:
        return pd.DataFrame()

    # Extract data as key-value pairs
    kv_pairs = {}
    for row_idx, row in rows_data.items():
        if 0 in row:  # Key in first column
            key = row[0].strip()
            # Skip empty keys or numeric-only keys
            if not key or key.isdigit():
                continue

            # Get values from other columns
            values = [row.get(col_idx, '') for col_idx in range(1, max(row.keys()) + 1)]

            # Join multiple values if needed
            value = ' '.join(filter(None, values)).strip()

            # Clean the key (remove colons, etc.)
            clean_key = key.rstrip(':').strip()

            kv_pairs[clean_key] = value

    if not kv_pairs:
        return pd.DataFrame()

    # Convert to DataFrame (transposed format - keys as columns)
    df = pd.DataFrame([kv_pairs])

    return df


def extract_multipage_tables(response_json: Union[str, dict, list]) -> Dict[str, pd.DataFrame]:
    """
    Extract table data from an invoice response, handling tables that span multiple pages,
    and convert them to pandas DataFrames. Now also handles horizontal key-value tables.

    Args:
        response_json: The response from the invoice processing API

    Returns:
        dict: A dictionary of DataFrames: {table_id: dataframe}
    """
    # Handle different input types
    tables = extract_tables_from_input(response_json)

    if not tables:
        print("No tables found in the response")
        return {}

    # Separate horizontal and vertical tables
    horizontal_tables = []
    vertical_tables = []

    for table in tables:
        if is_horizontal_table(table):
            horizontal_tables.append(table)
        else:
            vertical_tables.append(table)

    # Process results
    results = {}

    # Process horizontal tables (key-value pairs)
    for i, table in enumerate(horizontal_tables):
        df = extract_horizontal_table(table)
        if not df.empty:
            results[f"horizontal_table_{i}"] = df

    # Group vertical tables by structure (columns count and headers)
    table_groups = group_related_tables(vertical_tables)

    # Process each group of related vertical tables
    for group_id, table_group in table_groups.items():
        # Sort tables by page number if available
        table_group.sort(key=lambda t: t.get('boundingRegions', [{}])[0].get('pageNumber', 0)
        if 'boundingRegions' in t and t['boundingRegions'] else 0)

        # Bug fix: Handle None return value
        combined_df = merge_table_group(table_group)

        # Check for None before checking if empty
        if combined_df is not None and not combined_df.empty:
            results[f"vertical_table_{group_id}"] = combined_df

    return results


def extract_tables_from_input(input_data: Union[str, dict, list]) -> List[dict]:
    """Extract table objects from various input formats."""
    tables = []

    # If input is already a list of tables
    if isinstance(input_data, list):
        # Check if it's a list of table objects
        for item in input_data:
            if isinstance(item, dict):
                if 'cells' in item and 'columnCount' in item:
                    tables.append(item)
        if tables:
            return tables

    # If input is a dict
    if isinstance(input_data, dict):
        # Single table case
        if 'cells' in input_data and 'columnCount' in input_data:
            return [input_data]
        # Nested tables
        if 'tables' in input_data and isinstance(input_data['tables'], list):
            return input_data['tables']
        if 'analyzeResult' in input_data and 'tables' in input_data.get('analyzeResult', {}):
            return input_data['analyzeResult']['tables']

    # If input is a string, try to parse it
    if isinstance(input_data, str):
        # Try to find tables directly in the string
        table_objects = find_table_objects(input_data)
        if table_objects:
            return table_objects

        # Try to parse as JSON
        try:
            parsed_data = json.loads(input_data)
            return extract_tables_from_input(parsed_data)
        except json.JSONDecodeError:
            # If JSON parsing fails, try other extraction methods
            pass

    return tables


def find_table_objects(text: str) -> List[dict]:
    """Find and extract table objects from text content."""
    tables = []

    # Look for table candidate patterns
    table_candidates = []

    # Pattern to find objects with 'cells' array
    cells_pattern = r'("cells"\s*:\s*\[.*?\])'
    cells_matches = re.findall(cells_pattern, text, re.DOTALL)

    if cells_matches:
        # For each cells match, try to find the surrounding JSON object
        for match in cells_matches:
            # Find the start of the object before this cells array
            start_idx = text.find(match)
            if start_idx > 0:
                # Look backwards for the start of the object
                open_brace_idx = text.rfind('{', 0, start_idx)
                if open_brace_idx >= 0:
                    # Find the matching close brace
                    brace_count = 1
                    for i in range(start_idx + len(match), len(text)):
                        if text[i] == '{':
                            brace_count += 1
                        elif text[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                # Found the matching close brace
                                table_json = text[open_brace_idx:i + 1]
                                table_candidates.append(table_json)
                                break

    # Try to parse each candidate
    for candidate in table_candidates:
        try:
            table_obj = json.loads(candidate)
            if 'cells' in table_obj and isinstance(table_obj['cells'], list):
                tables.append(table_obj)
        except json.JSONDecodeError:
            continue

    return tables


def group_related_tables(tables: List[dict]) -> Dict[int, List[dict]]:
    """
    Group tables that appear to be continuations of each other across pages.

    Tables are considered related if they have the same column count and similar headers.

    Args:
        tables: List of table objects with 'cells' property

    Returns:
        Dictionary mapping group IDs to lists of related tables
    """
    table_groups = {}

    for table in tables:
        if 'cells' not in table or not table['cells']:
            continue

        # Get column count - either from table property or by finding max column index
        col_count = table.get('columnCount', 0)
        if col_count == 0:
            # Try to infer from the cells
            col_count = max([cell.get('columnIndex', 0) + 1 for cell in table['cells']], default=0)
            if col_count == 0:
                continue

        # Extract header cells
        header_cells = [cell for cell in table['cells']
                        if cell.get('rowIndex', 0) == 0 and
                        (cell.get('kind', '') == 'columnHeader' or 'kind' not in cell)]

        if not header_cells:
            # Try to infer headers from first row if not explicitly marked
            header_cells = [cell for cell in table['cells']
                            if cell.get('rowIndex', 0) == 0]

        # Sort header cells by column index
        header_cells.sort(key=lambda cell: cell.get('columnIndex', 0))

        # Extract header texts
        headers = [cell.get('content', '').strip() for cell in header_cells]

        # Create a signature for this table structure
        # Use both column count and header content to match tables
        # Create a simplified signature without special characters
        cleaned_headers = [re.sub(r'[^\w\s]', '', h.lower()) for h in headers]
        signature = f"{col_count}_{','.join(cleaned_headers)}"

        # Group tables with the same structure
        if signature not in table_groups:
            table_groups[signature] = []

        table_groups[signature].append(table)

    # Renumber the groups with simple integers
    return {i: group for i, group in enumerate(table_groups.values())}


def merge_table_group(tables: List[dict]) -> pd.DataFrame:
    """
    Merge a group of related tables into a single DataFrame.

    Args:
        tables: List of table objects from the same group (same structure)

    Returns:
        Combined DataFrame with data from all tables
    """
    try:
        if not tables:
            return pd.DataFrame()

        # Find the common headers across all tables in the group
        all_headers = []
        header_indices = {}

        # Process the first table to get the headers
        first_table = tables[0]

        # First try to find cells explicitly marked as columnHeader
        header_cells = [cell for cell in first_table['cells']
                        if cell.get('rowIndex', 0) == 0 and
                        cell.get('kind', '') == 'columnHeader']

        # If no explicit headers, just use the first row
        if not header_cells:
            header_cells = [cell for cell in first_table['cells']
                            if cell.get('rowIndex', 0) == 0]

        # Sort header cells by column index
        header_cells.sort(key=lambda cell: cell.get('columnIndex', 0))

        # Extract header texts and map column indices to header names
        for cell in header_cells:
            col_idx = cell.get('columnIndex', 0)
            header_text = cell.get('content', f'Column_{col_idx}').strip()
            all_headers.append(header_text)
            header_indices[col_idx] = header_text

        # Process all tables and extract data rows
        all_data = []

        for table_idx, table in enumerate(tables):
            # Detect page number for diagnostic purposes
            page_num = None
            if 'boundingRegions' in table and table['boundingRegions']:
                page_num = table['boundingRegions'][0].get('pageNumber', None)

            # Group cells by row index (skip header row)
            rows = {}
            max_row_index = 0

            for cell in table['cells']:
                row_idx = cell.get('rowIndex', 0)
                if row_idx > 0:  # Skip header row
                    if row_idx > max_row_index:
                        max_row_index = row_idx
                    if row_idx not in rows:
                        rows[row_idx] = {}
                    col_idx = cell.get('columnIndex', 0)
                    content = cell.get('content', '').strip()
                    rows[row_idx][col_idx] = content

            # Convert rows to a list of dictionaries
            for row_idx in range(1, max_row_index + 1):
                if row_idx in rows:
                    row_data = {}

                    # Add page number if available (for debugging)
                    if page_num:
                        row_data['_page'] = page_num

                    # Add table index within the group (for debugging)
                    row_data['_table_idx'] = table_idx

                    # Add data from each column
                    for col_idx, value in rows[row_idx].items():
                        # Map column index to header name if possible
                        if col_idx in header_indices:
                            header = header_indices[col_idx]
                        else:
                            # Use positional header if available, otherwise use column index
                            try:
                                header_pos = list(header_indices.keys()).index(
                                    col_idx) if col_idx in header_indices else col_idx
                                header = all_headers[header_pos] if header_pos < len(
                                    all_headers) else f'Column_{col_idx}'
                            except ValueError:
                                header = f'Column_{col_idx}'

                        row_data[header] = value

                    all_data.append(row_data)

        # Return empty DataFrame if no data rows found
        if not all_data:
            return pd.DataFrame()

        # Create DataFrame
        df = pd.DataFrame(all_data)

        column_names = df.columns
        column_invalidity = any(col for col in column_names if "Column" in col)
        if column_invalidity is True:
            # Check if there's a first row before trying to use it as headers
            if not df.empty:
                df.columns = df.iloc[0]
                df.drop(df.index[0], inplace=True)
                # Make sure there are at least 2 columns before trying to drop
                if df.shape[1] >= 3:
                    df.drop(df.columns[[0, 1]], axis=1, inplace=True)
                df = df.reset_index(drop=True)

        # Clean up column names
        # Remove special characters and 'unselected' from column names
        clean_columns = {}
        for col in df.columns:
            if str(col).startswith('_'):  # Keep debug columns as is
                continue
            clean_name = str(col).replace("\n", " ").strip()
            if clean_name != col:
                clean_columns[col] = clean_name

        # Rename columns
        if clean_columns:
            df = df.rename(columns=clean_columns)

        # Remove debug columns
        debug_cols = [col for col in df.columns if str(col).startswith('_')]
        if debug_cols:
            df = df.drop(debug_cols, axis=1)

        df = df.replace(":unselected:", "")
        df = df.replace("\n", " ", regex=True)

        return df

    except Exception as e:
        print(f"Error merging table group: {e}")
        # Always return a DataFrame, even on error
        return pd.DataFrame()
