import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re


class VATFieldClassifier:
    """
    An enhanced classifier for matching field names to VAT categories.
    Uses rule-based matching with fallback to similarity matching.
    Handles abbreviations, special cases, and ambiguities better.

    Updated with position awareness and improved amount field handling:
    - Total (amount_after_vat) is in the last column in 85% of cases
    - "Amount" defaults to amount_before_vat unless it contains VAT/tax indicators
    """

    def __init__(self, keywords_dict, threshold=0.35):
        """
        Initialize the classifier with keyword categories.

        Args:
            keywords_dict (dict): Dictionary with categories and their keywords
            threshold (float): Similarity threshold for matching
        """
        self.keywords_dict = keywords_dict
        self.threshold = threshold

        # Define common non-VAT fields to explicitly exclude
        self.non_vat_fields = [
            'service', 'description', 'item', 'product', 'requested by', 'date',
            'submitted', 'detail', 'location', 'name', 'address', 'contact',
            'email', 'phone', 'unit', 'qty', 'quantity', 'reference', 'invoice',
            'order', 'po', 'id', 'number', 'serial', 'sl', 'sr', 'no', 'page', 'price'
        ]

        # Expand keywords with common variations
        self.expanded_keywords = self._expand_keywords(keywords_dict)

        # Create abbreviation mappings
        self.abbreviations = {
            'amt': 'amount',
            'excl': 'excluding',
            'incl': 'including',
            'w/': 'with',
            'w/o': 'without',
            'w.o.': 'without',
            'w.': 'with',
            'tot': 'total',
            'ttl': 'total',
            'val': 'value',
            'ex': 'excluding',
            'inc': 'including',
            'tx': 'tax',
            'gr': 'gross',
            'net': 'net',
            'sub': 'subtotal',
            'disc': 'discount',
            've': 'vat excluded',
            'vi': 'vat included',
            'qty': 'quantity',
            'sl': 'serial',
            'no': 'number',
            'sr': 'serial',
            'desc': 'description',
            'pcs': 'pieces',
            'ea': 'each'
        }

        # Pattern matching rules (direct mappings)
        self.direct_patterns = {
            'vat_rate': [
                'vat %', 'vat rate', 'tax rate', 'rate of tax', 'vat(%)',
                '% vat', 'tax %', 'vat rate%', 'rate vat', 'vat code'
            ],
            'vat_amount': [
                'vat amount', 'tax amount', 'vat amt', 'tax amt', 'vat value',
                '% vat amount', 'vat @', 'tax @', 'vat (', 'tax (', 'vat in',
                'tax in', 'vat payable', 'tax'
            ],
            'amount_before_vat': [
                'excluding vat', 'excl vat', 'excl. vat', 'before vat', 'without vat',
                'exclusive of vat', 'amt excl', 'amount excl', 'net of vat',
                'taxable amount', 'taxable value', 'sales amount', 've', 'net payable',
                'total vatable amount', "subject to vat", 'fee amount'
            ],
            'amount_after_vat': [
                'including vat', 'incl vat', 'incl. vat', 'with vat', 'inclusive of vat',
                'gross amount', 'gross', 'grand total', 'total payable', 'gross payable',
                'net amount', 'net', 'incl. 5%vat', 'incl.5%vat', 'incl 5%vat',
                '(incl. 5%vat)', '(incl 5%vat)', 'vi', 'total amt', 'total amount',
                'amount with', 'with 5%', 'with 5% vat', 'with tax', 'total due'
            ]
        }

        # Updated priority rules with new defaults for amount fields
        self.priority_rules = {
            'total': ['amount_after_vat', 'amount_before_vat', 'vat_amount'],
            'amount': ['amount_before_vat', 'amount_after_vat', 'vat_amount'],  # Updated priority
            'net': ['amount_before_vat', 'amount_after_vat'],
            'gross': ['amount_after_vat'],
            'payable': ['amount_after_vat', 'vat_amount', 'amount_before_vat'],
            'vatable': ['amount_before_vat']
        }

        # Specific fields that should always be mapped to certain categories
        self.forced_mappings = {
            'net payable': 'amount_before_vat',
            'net amt': 'amount_before_vat',
            'gross payable': 'amount_after_vat',
            'vat payable': 'vat_amount',
            'vat code': 'vat_rate',
            'fee amount': 'amount_before_vat',
            'total amt': 'amount_after_vat',
            'total amount': 'amount_after_vat',
            'total': 'amount_after_vat',
            'tax amount': 'vat_amount',
            'amount': 'amount_before_vat'  # New default for "amount"
        }

        # Special case patterns (overrides other rules)
        self.special_cases = {
            'vat_rate': ['%', 'code'],
            'amount_before_vat': ['subtotal', 'base amount', 'net'],
            'amount_after_vat': ['total', 'final amount', 'gross']
        }

        # Add explicit full field patterns
        self.explicit_field_patterns = {
            'vat_rate': ['vat %', 'vat code'],
            'vat_amount': ['vat amount', 'vat payable', '5% vat amount'],
            'amount_before_vat': ['amount before vat', 'net payable', 'subject to vat'],
            'amount_after_vat': ['amount (incl. 5%vat)', 'amount incl 5%vat', 'gross payable']
        }

        # Field type patterns - used to identify the semantic type of a field
        self.field_type_patterns = {
            'vat_rate': ['rate', 'code', '%'],
            'vat_amount': ['value', 'vat payable', 'tax amt'],
            'amount_before_vat': ['before', 'excluding', 'net', 'without'],
            'amount_after_vat': ['after', 'including', 'with', 'gross', 'total']
        }

        # Indicators for different amount types
        self.amount_indicators = {
            'vat_amount': ['vat', 'tax'],
            'amount_after_vat': ['total', 'gross', 'grand', 'with', 'incl', 'including', 'after'],
            'amount_before_vat': ['net', 'excl', 'excluding', 'before', 'without']
        }

    def _expand_keywords(self, keywords_dict):
        """
        Expand keywords with common variations.

        Args:
            keywords_dict (dict): Original keywords dictionary

        Returns:
            dict: Expanded keywords dictionary
        """
        expanded = {}

        for category, keywords in keywords_dict.items():
            expanded[category] = list(keywords)  # Copy the original list

            # Add variations for each keyword
            for keyword in keywords:
                # Add uppercase and title case versions
                expanded[category].append(keyword.upper())
                expanded[category].append(keyword.title())

                # Replace spaces with underscores and dashes
                expanded[category].append(keyword.replace(' ', '_'))
                expanded[category].append(keyword.replace(' ', '-'))

                # Add abbreviated versions for longer terms
                words = keyword.split()
                if len(words) > 1:
                    abbr = ''.join(w[0] for w in words)
                    expanded[category].append(abbr)
                    expanded[category].append(abbr.upper())

        return expanded

    def is_non_vat_field(self, field):
        """
        Check if a field is a common non-VAT field that should be excluded.

        Args:
            field (str): Field name to check

        Returns:
            bool: True if it's a non-VAT field
        """
        field_lower = field.lower()

        # If field contains VAT or tax, it's probably VAT-related
        if 'vat' in field_lower or 'tax' in field_lower:
            return False

        # Check if the field exactly matches any non-VAT field
        for non_vat in self.non_vat_fields:
            if non_vat == field_lower:
                return True

        # If the field is a single word, check if it's in the non-VAT list
        if len(field_lower.split()) == 1:
            if field_lower in self.non_vat_fields:
                return True

        # If the field contains any VAT-related terms, it's probably not a non-VAT field
        vat_indicators = ['vat', 'tax', 'excl', 'incl', 'before', 'after', 'with', 'without']
        for indicator in vat_indicators:
            if indicator in field_lower:
                return False

        # Additional checks for common non-VAT fields
        common_prefixes = ['service', 'item', 'product', 'desc']
        for prefix in common_prefixes:
            if field_lower.startswith(prefix):
                return True

        return False

    def normalize_field(self, field):
        """
        Normalize field name for comparison.

        Args:
            field (str): Field name to normalize

        Returns:
            tuple: (normalized field, expanded field with abbreviations replaced)
        """
        if not field:
            return "", "", ""

        # Convert to lowercase
        normalized = field.lower()

        # Save original for exact pattern matching
        original_lower = normalized

        # Replace special characters with spaces
        normalized = re.sub(r'[_\-\.\(\)]', ' ', normalized)

        # Remove duplicate spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Create expanded version with abbreviations replaced
        expanded = normalized

        # Replace abbreviations
        for abbr, full in self.abbreviations.items():
            # Only replace if it's a whole word
            expanded = re.sub(r'\b' + abbr + r'\b', full, expanded)

        return normalized, expanded, original_lower

    def check_forced_mapping(self, field):
        """
        Check if field has a forced mapping to a specific category.

        Args:
            field (str): Field name to check

        Returns:
            str or None: Forced category or None
        """
        field_lower = field.lower()

        # Check for exact matches in forced mappings
        if field_lower in self.forced_mappings:
            return self.forced_mappings[field_lower]

        # Also check normalized versions
        normalized, expanded, _ = self.normalize_field(field)
        if normalized in self.forced_mappings:
            return self.forced_mappings[normalized]
        if expanded in self.forced_mappings:
            return self.forced_mappings[expanded]

        return None

    def check_exact_field_match(self, field):
        """
        Check if field exactly matches any explicit field patterns.

        Args:
            field (str): Field name to check

        Returns:
            str or None: Matching category or None
        """
        field_lower = field.lower()

        # Check if the field exactly matches any explicit patterns
        for category, patterns in self.explicit_field_patterns.items():
            for pattern in patterns:
                # Case insensitive exact match
                if field_lower == pattern.lower():
                    return category

        return None

    def check_direct_match(self, normalized, expanded, original_lower):
        """
        Check for direct pattern matches.

        Args:
            normalized (str): Normalized field name
            expanded (str): Expanded field name with abbreviations replaced
            original_lower (str): Original field in lowercase without character replacement

        Returns:
            str or None: Matching category or None
        """
        matches = {}

        # Check for direct matches
        for category, patterns in self.direct_patterns.items():
            for pattern in patterns:
                if (pattern in normalized or
                        pattern in expanded or
                        pattern in original_lower):
                    matches[category] = True

        # Special case handling for single-word fields
        if len(normalized.split()) == 1:
            for category, special_patterns in self.special_cases.items():
                for pattern in special_patterns:
                    if normalized == pattern or expanded == pattern:
                        return category

        # Handle ambiguous matches
        if len(matches) > 1:
            # Check priority rules for common ambiguous terms
            for term, priority_list in self.priority_rules.items():
                if term in normalized or term in expanded:
                    for category in priority_list:
                        if category in matches:
                            return category

        # Return the single match if there is one
        if len(matches) == 1:
            return list(matches.keys())[0]

        return None

    def compute_similarity(self, field, category):
        """
        Compute similarity between field and category keywords.

        Args:
            field (str): Field name
            category (str): Category name

        Returns:
            float: Similarity score (0 to 1)
        """
        normalized, expanded, original_lower = self.normalize_field(field)

        if not normalized:
            return 0.0

        max_score = 0.0

        # Check keyword similarity
        for keyword in self.expanded_keywords[category]:
            # Simple substring matching
            keyword_norm = keyword.lower()

            # Exact match
            if normalized == keyword_norm or expanded == keyword_norm:
                return 1.0

            # Substring match
            if keyword_norm in normalized or keyword_norm in expanded or keyword_norm in original_lower:
                score = len(keyword_norm) / max(len(normalized), len(expanded))
                max_score = max(max_score, score)

            # Word overlap
            norm_words = set(normalized.split())
            exp_words = set(expanded.split())
            keyword_words = set(keyword_norm.split())

            if keyword_words and (norm_words or exp_words):
                norm_overlap = len(norm_words.intersection(keyword_words)) / max(len(norm_words), len(keyword_words))
                exp_overlap = len(exp_words.intersection(keyword_words)) / max(len(exp_words), len(keyword_words))
                max_score = max(max_score, norm_overlap, exp_overlap)

        return max_score

    def field_semantic_type(self, field):
        """
        Determine the semantic type of a field based on key identifiers.

        Args:
            field (str): Field name to analyze

        Returns:
            str or None: Best matching category or None
        """
        normalized, expanded, _ = self.normalize_field(field)

        scores = {}

        for category, patterns in self.field_type_patterns.items():
            score = 0
            for pattern in patterns:
                if pattern in normalized or pattern in expanded:
                    score += 1

            if score > 0:
                scores[category] = score

        if not scores:
            return None

        # Find category with highest score
        best_category = max(scores.items(), key=lambda x: x[1])[0]
        return best_category

    def classify_single_field(self, field, is_last_column=False):
        """
        Classify a single field into a VAT category.

        Args:
            field (str): Field name to classify
            is_last_column (bool): Whether this field is in the last column

        Returns:
            tuple: (category or None, similarity score)
        """
        if not field:
            return None, 0.0

        # First, check if it's a non-VAT field that should be excluded
        if self.is_non_vat_field(field):
            return None, 0.0

        # For last column, prioritize amount_after_vat if the field contains "total" or "amount"
        field_lower = field.lower()
        normalized, expanded, original_lower = self.normalize_field(field)

        if is_last_column:
            # If the last column contains "total" or has a generic "amount" term, it's likely amount_after_vat
            if ("total" in normalized or
                    (("amount" in normalized or "amt" in normalized) and
                     not any(x in normalized for x in ["vat", "tax"]))):
                return "amount_after_vat", 0.95

        # Next, check for forced mappings
        forced_mapping = self.check_forced_mapping(field)
        if forced_mapping:
            return forced_mapping, 1.0

        # Next, check for exact field matches
        exact_match = self.check_exact_field_match(field)
        if exact_match:
            return exact_match, 1.0

        # Check for direct pattern matches
        direct_match = self.check_direct_match(normalized, expanded, original_lower)
        if direct_match:
            return direct_match, 1.0

        # Handle "amount" field according to new rules
        if "amount" in normalized and not any(x in normalized for x in ["vat", "tax"]):
            # Check for indicators that would make it amount_after_vat
            after_indicators = ["total", "with", "incl", "including", "after", "gross"]
            if any(indicator in normalized for indicator in after_indicators):
                return "amount_after_vat", 0.9
            # Default to amount_before_vat for plain "amount"
            return "amount_before_vat", 0.85

        # Check semantic type if no direct match
        semantic_type = self.field_semantic_type(field)
        if semantic_type:
            return semantic_type, 0.8

        # Fall back to similarity-based matching
        best_score = 0.0
        best_category = None

        for category in self.keywords_dict:
            similarity = self.compute_similarity(field, category)
            if similarity > best_score:
                best_score = similarity
                best_category = category

        if best_score >= self.threshold:
            return best_category, best_score

        return None, best_score

    def classify_fields(self, fields):
        """
        Classify a list of field names into VAT categories.

        Args:
            fields (list): List of field names to classify

        Returns:
            dict: Dictionary mapping categories to field names
        """
        results = {category: None for category in self.keywords_dict}
        scores = {category: 0.0 for category in self.keywords_dict}

        # Identify the last column as a potential amount_after_vat field
        # Handle both list and pandas Series/Index objects
        try:
            # For pandas Series/Index
            if hasattr(fields, 'empty'):
                last_column_index = len(fields) - 1 if not fields.empty else -1
            # For standard Python lists/tuples
            else:
                last_column_index = len(fields) - 1 if fields else -1
        except Exception:
            # Fallback
            last_column_index = -1

        # First pass: Apply the 85% rule for last column
        if last_column_index >= 0:
            last_field = fields[last_column_index]
            last_field_lower = last_field.lower()

            # Check if last field contains total-like or amount-like words and no VAT indicators
            if (("total" in last_field_lower or
                 "amount" in last_field_lower or
                 "amt" in last_field_lower or
                 "sum" in last_field_lower or
                 "grand" in last_field_lower) and
                    not self.is_non_vat_field(last_field)):

                # Check if it doesn't have explicit VAT amount indicators
                if not ("vat amount" in last_field_lower or
                        "tax amount" in last_field_lower):
                    results['amount_after_vat'] = last_field
                    scores['amount_after_vat'] = 0.95

        # Second pass: check for specific field patterns
        for i, field in enumerate(fields):
            is_last_column = (i == last_column_index)
            field_lower = field.lower()

            # Skip the last field if it's already assigned to amount_after_vat
            if is_last_column and results['amount_after_vat'] == field:
                continue

            # VAT Code -> vat_rate
            if 'vat' in field_lower and 'code' in field_lower:
                results['vat_rate'] = field
                scores['vat_rate'] = 1.0

            # VAT Payable -> vat_amount
            elif 'vat' in field_lower and 'payable' in field_lower:
                results['vat_amount'] = field
                scores['vat_amount'] = 1.0

            # Net Payable -> amount_before_vat
            elif 'net' in field_lower and 'payable' in field_lower:
                results['amount_before_vat'] = field
                scores['amount_before_vat'] = 1.0

            # Gross Payable -> amount_after_vat
            elif 'gross' in field_lower and 'payable' in field_lower:
                results['amount_after_vat'] = field
                scores['amount_after_vat'] = 1.0

            # Amount field handling - default to amount_before_vat
            elif ('amount' in field_lower or 'amt' in field_lower) and not any(
                    x in field_lower for x in ['vat', 'tax']):
                # Check for indicators that would make it amount_after_vat
                if any(x in field_lower for x in ['total', 'with', 'incl', 'including', 'after', 'gross']):
                    if not results['amount_after_vat']:
                        results['amount_after_vat'] = field
                        scores['amount_after_vat'] = 0.9
                # Otherwise, it's amount_before_vat by default
                elif not results['amount_before_vat']:
                    results['amount_before_vat'] = field
                    scores['amount_before_vat'] = 0.85

            # Total Amount with VAT pattern variations
            elif ('total' in field_lower or 'grand' in field_lower) and not results['amount_after_vat']:
                results['amount_after_vat'] = field
                scores['amount_after_vat'] = 1.0

            # Simple "Total" or "Total Amt"
            elif (field_lower == 'total' or field_lower == 'total amt' or field_lower == 'total amount') and not \
            results['amount_after_vat']:
                results['amount_after_vat'] = field
                scores['amount_after_vat'] = 1.0

            # VAT amount or Tax amount
            elif (('vat' in field_lower or 'tax' in field_lower) and
                  ('amount' in field_lower or 'amt' in field_lower)) and not results['vat_amount']:
                results['vat_amount'] = field
                scores['vat_amount'] = 1.0

        # Third pass: process remaining fields
        field_results = {}
        for i, field in enumerate(fields):
            is_last_column = (i == last_column_index)

            # Skip fields that have already been assigned
            if any(field == results[cat] for cat in results if results[cat] is not None):
                continue

            category, score = self.classify_single_field(field, is_last_column)
            if category:
                if category not in field_results or score > field_results[category][1]:
                    field_results[category] = (field, score)

        # Assign the best field for each category
        for category, (field, score) in field_results.items():
            # Only update if we don't already have a result for this category
            if results[category] is None:
                results[category] = field
                scores[category] = score

        return results, scores

    def explain_classification(self, fields):
        """
        Classify fields and provide detailed explanation.

        Args:
            fields (list): List of field names to classify

        Returns:
            tuple: (results, explanation string)
        """
        # Process each field individually
        field_details = []
        # Handle both list and pandas Series/Index objects
        try:
            # For pandas Series/Index
            if hasattr(fields, 'empty'):
                last_column_index = len(fields) - 1 if not fields.empty else -1
            # For standard Python lists/tuples
            else:
                last_column_index = len(fields) - 1 if fields else -1
        except Exception:
            # Fallback
            last_column_index = -1

        for i, field in enumerate(fields):
            is_last_column = (i == last_column_index)
            normalized, expanded, original_lower = self.normalize_field(field)

            # Check if it's a non-VAT field
            is_non_vat = self.is_non_vat_field(field)

            # Check for forced mapping
            forced_mapping = self.check_forced_mapping(field)

            # Check for exact field match
            exact_match = self.check_exact_field_match(field)

            # Get the direct match result
            direct_match = self.check_direct_match(normalized, expanded, original_lower)

            # Get semantic type
            semantic_type = self.field_semantic_type(field)

            # Get scores for each category
            scores = []
            for category in self.keywords_dict:
                similarity = self.compute_similarity(field, category)
                scores.append((category, similarity))

            # Sort by score
            scores.sort(key=lambda x: x[1], reverse=True)

            field_details.append({
                'field': field,
                'is_last_column': is_last_column,
                'normalized': normalized,
                'expanded': expanded,
                'original_lower': original_lower,
                'is_non_vat': is_non_vat,
                'forced_mapping': forced_mapping,
                'exact_match': exact_match,
                'direct_match': direct_match,
                'semantic_type': semantic_type,
                'scores': scores
            })

        # Get the overall classification
        results, result_scores = self.classify_fields(fields)

        # Create explanation
        explanation = ["Classification Results:"]

        # Show the final classification
        for category in self.keywords_dict:
            if results[category]:
                explanation.append(f"  - {category}: '{results[category]}' (score: {result_scores[category]:.3f})")
            else:
                explanation.append(f"  - {category}: No matching field found")

        # Add details for each field
        explanation.append("\nDetailed Analysis:")

        for detail in field_details:
            field = detail['field']
            explanation.append(f"\nField: '{field}'")

            if detail['is_last_column']:
                explanation.append(f"  Position: Last Column (85% rule applies)")

            explanation.append(f"  Normalized: '{detail['normalized']}'")
            explanation.append(f"  Expanded: '{detail['expanded']}'")
            explanation.append(f"  Original (lowercase): '{detail['original_lower']}'")

            if detail['is_non_vat']:
                explanation.append("  Is Non-VAT Field: Yes")

            if detail['forced_mapping']:
                explanation.append(f"  Forced Mapping: {detail['forced_mapping']}")

            if detail['exact_match']:
                explanation.append(f"  Exact Field Match: {detail['exact_match']}")

            if detail['direct_match']:
                explanation.append(f"  Direct Pattern Match: {detail['direct_match']}")

            if detail['semantic_type']:
                explanation.append(f"  Semantic Type: {detail['semantic_type']}")

            explanation.append("  Similarity Scores:")
            for category, score in detail['scores']:
                match_marker = " ← MATCH" if results[category] == field else ""
                explanation.append(f"    - {category}: {score:.3f}{match_marker}")

        return results, "\n".join(explanation)


# VAT categories and keywords
KEYWORDS = {
    'vat_rate': ['vat %', 'vat rate', 'tax rate', 'rate of tax', 'vat(%)', 'vat rate%', 'rate vat', 'tax %',
                 'vat code'],
    'vat_amount': [
        'vat amount', 'tax amount', 'vat amt', 'total vat', 'vat value', '5% vat', 'vat @ 5%',
        'vat 5%', 'tax', 'vat (aed)', '5% vat amount', 'total amount vat @ 5%', 'vat amt aed',
        'total vat value', 'vat', 'vat payable'
    ],
    'amount_before_vat': [
        'amount before vat', 'excl vat', 'excluding vat', 'before vat', 'without vat',
        'exclusive of vat', 'excl. vat', 'taxable amount', 'taxable value', 'total amount without vat',
        'amt excl vat', 'total(aed) excl. vat', 'total value excluding vat', 'sales amount', 'net payable',
        'total vatable amount', "subject to vat", "fee amount"
    ],
    'amount_after_vat': [
        'amount (incl. 5%vat)', 'incl vat', 'including vat', 'with vat', 'total amount with vat',
        'grand total', 'gross amount', 'total incl', 'total amt with vat', 'net payable',
        'total value including vat', 'total amount (aed) (including vat)', 'total', 'gross payable'
    ]
}

# Create and use the classifier
CLASSIFIER = VATFieldClassifier(KEYWORDS)


# Example usage
def predict(sample_fields):
    results, explanation = CLASSIFIER.explain_classification(sample_fields)
    print(explanation)

    # print(explanation)
    print("\nFinal classification result:")
    print(results)

    return results
