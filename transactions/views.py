from django.shortcuts import render
from django.http import HttpResponse
from .forms import StatementUploadForm
from .models import Transaction
from .utils import extract_text_from_pdf, parse_transactions_from_text


def home(request):
    form = StatementUploadForm()
    errors = []
    parsed_transactions = []
    messages = []

    if request.method == 'POST':
        form = StatementUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = request.FILES['statement']
            try:
                text = extract_text_from_pdf(pdf_file)
            except Exception:
                errors.append('Unable to read the PDF. Please upload a valid credit card statement PDF.')
            else:
                parsed_transactions = parse_transactions_from_text(text)
                if not parsed_transactions:
                    errors.append('No transactions were detected in the uploaded statement. Please try another PDF or verify the file format.')
                else:
                    created = []
                    for txn_data in parsed_transactions:
                        transaction, created_flag = Transaction.objects.get_or_create(
                            date=txn_data['date'],
                            description=txn_data['description'],
                            amount=txn_data['amount'],
                            defaults={'category': txn_data['category']},
                        )
                        if created_flag:
                            created.append(transaction)

                    messages.append(f'Successfully saved {len(created)} new transaction(s).')
                    if len(parsed_transactions) - len(created) > 0:
                        messages.append(f'{len(parsed_transactions) - len(created)} duplicate transaction(s) were skipped.')

    recent_transactions = Transaction.objects.all()[:20]
    return render(request, 'transactions/upload.html', {
        'form': form,
        'errors': errors,
        'messages': messages,
        'parsed_transactions': parsed_transactions,
        'recent_transactions': recent_transactions,
    })
