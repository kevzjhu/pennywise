import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_PATTERNS = [
    '%m/%d/%Y',
    '%m/%d/%y',
    '%d/%m/%Y',
    '%d/%m/%y',
    '%Y-%m-%d',
]
DATE_REGEX = r'(?P<date>\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b)'
AMOUNT_REGEX = r'(?P<amount>-?\$?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?)(?!\S)'

CATEGORY_KEYWORDS = {
    'groceries': ['grocery', 'market', 'whole', 'foods', 'trader', 'aldi', 'stop & shop', 'walmart', 'costco', 'kroger', 'aldi'],
    'transportation': ['uber', 'lyft', 'taxi', 'gas', 'shell', 'exxon', 'chevron', 'train', 'bus', 'metro', 'transit', 'flight', 'airport'],
    'dining': ['restaurant', 'cafe', 'coffee', 'starbucks', 'dining', 'bar', 'pizza', 'burger', 'food', 'bistro', 'taco'],
    'utilities': ['electric', 'water', 'internet', 'phone', 'cable', 'gas bill', 'utility', 'comcast', 'att', 'verizon', 'spectrum'],
    'shopping': ['amazon', 'target', 'walmart', 'macy', 'best buy', 'apple', 'shopping', 'store', 'mall'],
    'travel': ['hotel', 'airbnb', 'booking', 'uber eats', 'rental', 'car rental', 'travel', 'orbitz', 'expedia'],
    'entertainment': ['netflix', 'spotify', 'movie', 'concert', 'ticket', 'hulu', 'disney', 'playstation', 'xbox'],
}


def extract_text_from_pdf(pdf_file):
    try:
        import pdfplumber

        pdf_file.seek(0)
        with pdfplumber.open(pdf_file) as pdf:
            pages = [page.extract_text() or '' for page in pdf.pages]
        return '\n'.join(pages)
    except ImportError:
        from PyPDF2 import PdfReader

        pdf_file.seek(0)
        reader = PdfReader(pdf_file)
        pages = [page.extract_text() or '' for page in reader.pages]
        return '\n'.join(pages)


def parse_date_string(date_text):
    for pattern in DATE_PATTERNS:
        try:
            parsed = datetime.strptime(date_text, pattern).date()
            return parsed
        except ValueError:
            continue
    return None


def parse_amount_string(amount_text):
    cleaned = amount_text.replace('$', '').replace(',', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def categorize_description(description):
    lowered = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                return category
    return 'other'


def parse_transaction_line(line):
    line = line.replace('\u00a0', ' ').strip()
    if len(line) < 10:
        return None

    date_match = re.search(DATE_REGEX, line)
    if not date_match:
        return None

    matches = list(re.finditer(AMOUNT_REGEX, line))
    if not matches:
        return None

    amount_match = matches[-1]
    date_text = date_match.group('date')
    amount_text = amount_match.group('amount')
    amount = parse_amount_string(amount_text)
    if amount is None:
        return None

    parsed_date = parse_date_string(date_text)
    if parsed_date is None:
        return None

    desc_parts = []
    if date_match.start() > 0:
        desc_parts.append(line[:date_match.start()])
    if date_match.end() < amount_match.start():
        desc_parts.append(line[date_match.end():amount_match.start()])
    if amount_match.end() < len(line):
        desc_parts.append(line[amount_match.end():])

    description = ' '.join(desc_parts).strip()
    description = re.sub(r'\s{2,}', ' ', description)
    if not description:
        description = 'Unknown transaction'
    if len(description) > 255:
        description = description[:252] + '...'

    return {
        'date': parsed_date,
        'description': description,
        'amount': amount,
        'category': categorize_description(description),
    }


def parse_transactions_from_text(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    transactions = []
    for line in lines:
        parsed = parse_transaction_line(line)
        if parsed:
            transactions.append(parsed)
    return transactions
