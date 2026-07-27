# transactions/services.py
import csv
import datetime
from decimal import Decimal, InvalidOperation
from .models import Transaction

REQUIRED_WEALTHSIMPLE_COLUMNS = {'transaction_date', 'details', 'amount'}
REQUIRED_RBC_COLUMNS = {'account type', 'transaction date', 'description 1', 'cad$'}


# ---------------------------------------------------------------------------
# Shared Helper Functions
# ---------------------------------------------------------------------------

def get_user_transaction_lookup_sets(user):
    """
    Fetches the user's existing transactions and builds lookup sets 
    for exact and potential (date + amount) duplicate detection.
    """
    user_txs = Transaction.objects.filter(user=user).values('date', 'amount', 'description')
    
    exact_matches = set()
    date_amount_matches = set()

    for tx in user_txs:
        d = tx['date']
        a = tx['amount']
        desc = tx['description'].strip().lower()
        exact_matches.add((d, a, desc))
        date_amount_matches.add((d, a))

    return exact_matches, date_amount_matches


def check_duplicate_status(tx_date, amount, description, exact_matches, date_amount_matches):
    """
    Checks a single transaction against lookup sets to determine duplicate status.
    Returns (status_label, is_duplicate_bool, selected_by_default_bool).
    """
    clean_desc = description.strip().lower()

    if (tx_date, amount, clean_desc) in exact_matches:
        return 'Duplicate', True, False
    elif (tx_date, amount) in date_amount_matches:
        return 'Possible Duplicate', True, False
    
    return 'New', False, True


# ---------------------------------------------------------------------------
# Bank Parsers
# ---------------------------------------------------------------------------

def validate_and_parse_rbc_csv(csv_file, user):
    """Validates RBC CSVs and extracts candidate transactions."""
    if not csv_file or not csv_file.name.lower().endswith('.csv'):
        raise ValueError("The uploaded file must be a .csv file.")

    decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
    reader = csv.DictReader(decoded_file)

    if not reader.fieldnames:
        raise ValueError("The uploaded CSV is empty or invalid.")

    # 1. Header Validation
    fieldnames_set = {f.strip().lower() for f in reader.fieldnames if f}
    if not REQUIRED_RBC_COLUMNS.issubset(fieldnames_set):
        raise ValueError(
            "The uploaded CSV does not conform to the RBC template. "
            "Required columns: 'Account Type', 'Transaction Date', 'Description 1', 'CAD$'."
        )

    # 2. Get shared duplicate lookup sets
    exact_matches, date_amount_matches = get_user_transaction_lookup_sets(user)
    candidate_rows = []

    # 3. Parse and filter rows
    for idx, row in enumerate(reader):
        clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}
        if not clean_row:
            continue

        # Filter for MasterCard / Visa
        acct_type = clean_row.get('account type', '').lower()
        if 'mastercard' not in acct_type and 'visa' not in acct_type:
            continue

        # Filter out credit card payments
        description = clean_row.get('description 1', 'RBC Import')
        desc_lower = description.lower()
        if any(term in desc_lower for term in ['payment - thank you', 'paiement - merci', 'pai ement - merci']):
            continue

        raw_date = clean_row.get('transaction date')
        raw_amount = clean_row.get('cad$')
        if not raw_date or not raw_amount:
            continue

        try:
            tx_date = datetime.datetime.strptime(raw_date, '%m/%d/%Y').date()
            amount = abs(Decimal(raw_amount))
            if amount == 0:
                continue
        except (ValueError, InvalidOperation):
            continue

        # 4. Shared Duplicate Detection
        status, is_duplicate, selected = check_duplicate_status(
            tx_date, amount, description, exact_matches, date_amount_matches
        )

        candidate_rows.append({
            'index': idx,
            'date': tx_date.strftime('%Y-%m-%d'),
            'description': description,
            'amount': f"{amount:.2f}",
            'status': status,
            'is_duplicate': is_duplicate,
            'selected': selected
        })

    return candidate_rows

def validate_and_parse_td_csv(csv_file, user):
    """
    Validates TD CSV exports (no headers) and extracts candidate transactions.
    - Column A (index 0): Date (Format M/D/YYYY)
    - Column B (index 1): Description / Transaction Type
    - Column C (index 2): Amount (Outflow / Expense)
    Filters out 'PAYMENT - THANK YOU' rows and duplicate entries.
    """
    if not csv_file or not csv_file.name.lower().endswith('.csv'):
        raise ValueError("The uploaded file must be a .csv file.")

    # Use 'utf-8-sig' to automatically handle UTF-8 Byte Order Marks (BOM)
    decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
    reader = csv.reader(decoded_file)

    # Fetch existing transactions for duplicate detection
    exact_matches, date_amount_matches = get_user_transaction_lookup_sets(user)
    candidate_rows = []

    for idx, row in enumerate(reader):
        # Ignore empty rows or rows that don't have at least Date, Description, and Amount
        if not row or len(row) < 3:
            continue

        raw_date = row[0].strip()
        description = row[1].strip()
        raw_amount = row[2].strip()

        if not raw_date or not description:
            continue

        # Filter out credit card payments
        desc_lower = description.lower()
        if 'payment - thank you' in desc_lower or 'paiement - merci' in desc_lower:
            continue

        # If Column C is empty (e.g. for payments or credits logged in Column D), skip row
        if not raw_amount:
            continue

        try:
            # TD uses M/D/YYYY date format (e.g. 7/24/2026)
            tx_date = datetime.datetime.strptime(raw_date, '%m/%d/%Y').date()
            amount = abs(Decimal(raw_amount))
            if amount == 0:
                continue
        except (ValueError, InvalidOperation):
            continue

        # Shared duplicate detection logic
        status, is_duplicate, selected = check_duplicate_status(
            tx_date, amount, description, exact_matches, date_amount_matches
        )

        candidate_rows.append({
            'index': idx,
            'date': tx_date.strftime('%Y-%m-%d'),
            'description': description,
            'amount': f"{amount:.2f}",
            'status': status,
            'is_duplicate': is_duplicate,
            'selected': selected
        })

    if not candidate_rows:
        raise ValueError("No valid expense transactions were found in the uploaded TD CSV file.")

    return candidate_rows

def validate_and_parse_wealthsimple_csv(csv_file, user):
    """Validates Wealthsimple CSVs and extracts candidate transactions."""
    if not csv_file or not csv_file.name.lower().endswith('.csv'):
        raise ValueError("The uploaded file must be a .csv file.")

    decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
    reader = csv.DictReader(decoded_file)

    if not reader.fieldnames:
        raise ValueError("The uploaded CSV is empty or invalid.")

    # 1. Header Validation
    fieldnames_set = {f.strip().lower() for f in reader.fieldnames if f}
    if not REQUIRED_WEALTHSIMPLE_COLUMNS.issubset(fieldnames_set):
        raise ValueError(
            "The uploaded CSV does not conform to the expected template. "
            "Required columns: 'transaction_date', 'details', 'amount'."
        )

    # 2. Get shared duplicate lookup sets
    exact_matches, date_amount_matches = get_user_transaction_lookup_sets(user)
    candidate_rows = []

    # 3. Parse and filter rows
    for idx, row in enumerate(reader):
        clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}
        if not clean_row or not clean_row.get('transaction_date') or not clean_row.get('amount'):
            continue

        # Filter out payments
        tx_type = clean_row.get('type', '').lower()
        if 'payment' in tx_type:
            continue

        raw_date = clean_row.get('transaction_date')
        description = clean_row.get('details', 'Wealthsimple Import')
        raw_amount = clean_row.get('amount')

        try:
            tx_date = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
            amount = abs(Decimal(raw_amount))
            if amount == 0:
                continue
        except (ValueError, InvalidOperation):
            continue

        # 4. Shared Duplicate Detection
        status, is_duplicate, selected = check_duplicate_status(
            tx_date, amount, description, exact_matches, date_amount_matches
        )

        candidate_rows.append({
            'index': idx,
            'date': tx_date.strftime('%Y-%m-%d'),
            'description': description,
            'amount': f"{amount:.2f}",
            'status': status,
            'is_duplicate': is_duplicate,
            'selected': selected
        })

    return candidate_rows