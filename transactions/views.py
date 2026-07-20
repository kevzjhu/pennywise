from django.shortcuts import render, redirect, get_object_or_404
from .forms import TransactionForm, PaycheckTransactionForm, PaycheckTemplateForm
from .models import Transaction, PaycheckTransaction, PaycheckTemplate

def home(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')
        delete_id = request.POST.get('delete_id')
        transaction_id = request.POST.get('transaction_id')

        # 1. Handle Bulk Delete
        if action_type == 'bulk_delete' or request.POST.get('bulk_delete'):
            transaction_ids = request.POST.getlist('transaction_ids')
            if transaction_ids:
                Transaction.objects.filter(id__in=transaction_ids).delete()

        # 2. Handle Single Row Delete
        elif action_type == 'single_delete' or delete_id:
            target_id = delete_id or request.POST.get('delete_id')
            if target_id:
                transaction = get_object_or_404(Transaction, pk=target_id)
                transaction.delete()

        # 3. Handle Add / Edit Transaction
        else:
            if transaction_id:
                instance = get_object_or_404(Transaction, pk=transaction_id)
                form = TransactionForm(request.POST, instance=instance)
            else:
                form = TransactionForm(request.POST)

            if form.is_valid():
                form.save()

        # HTMX Check: Return re-rendered partial template if requested via HTMX
        if request.headers.get('HX-Request'):
            form = TransactionForm()
            transactions = Transaction.objects.all().order_by('-date')
            context = {
                'form': form,
                'transactions': transactions,
                'current_filters': {
                    'search': '',
                    'categories': [],
                    'start_date': '',
                    'end_date': '',
                    'min_amount': '',
                    'max_amount': '',
                    'sort_by': 'date',
                    'direction': 'desc',
                    'next_direction': 'asc',
                }
            }
            return render(request, "transactions/_table.html", context)

        return redirect('home')
            
    # --- GET REQUEST: ADVANCED FILTERING & SORTING ---
    form = TransactionForm()
    transactions = Transaction.objects.all()

    # 1. Multi-Select Categories
    selected_categories = request.GET.getlist('category')
    if selected_categories:
        transactions = transactions.filter(category__in=selected_categories)

    # 2. Date Range
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)

    # 3. Description Search
    search_query = request.GET.get('search', '')
    if search_query:
        transactions = transactions.filter(description__icontains=search_query)

    # 4. Amount Filter (Flexible Range)
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')

    if min_amount:
        transactions = transactions.filter(amount__gte=float(min_amount))
        
    if max_amount:
        transactions = transactions.filter(amount__lte=float(max_amount))

    # 5. Sorting
    sort_by = request.GET.get('sort_by', 'date')
    direction = request.GET.get('direction', 'desc')

    allowed_sort = {'date': 'date', 'description': 'description', 'category': 'category', 'amount': 'amount'}
    db_field = allowed_sort.get(sort_by, 'date')
    
    if direction == 'desc':
        transactions = transactions.order_by(f'-{db_field}')
    else:
        transactions = transactions.order_by(db_field)

    next_direction = 'asc' if direction == 'desc' else 'desc'

    context = {
        'form': form,
        'transactions': transactions,
        'current_filters': {
            'search': search_query,
            'categories': selected_categories,
            'start_date': start_date,
            'end_date': end_date,
            'min_amount': min_amount,
            'max_amount': max_amount,
            'sort_by': sort_by,
            'direction': direction,
            'next_direction': next_direction,
        }
    }

    if request.headers.get('HX-Request'):
        return render(request, "transactions/_table.html", context)

    return render(request, "transactions/home.html", context)

def income(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')

        # 1. Single Row Delete
        if action_type == 'single_delete' or request.POST.get('delete_id'):
            delete_id = request.POST.get('delete_id')
            if delete_id:
                paycheck = get_object_or_404(PaycheckTransaction, pk=delete_id)
                if paycheck.template:
                    template = paycheck.template
                    date_str = paycheck.date.strftime('%Y-%m-%d')
                    if date_str not in template.skipped_dates:
                        template.skipped_dates.append(date_str)
                        template.save()
                paycheck.delete()

        # 2. Bulk Delete
        elif action_type == 'bulk_delete' or request.POST.get('bulk_delete'):
            paycheck_ids = request.POST.getlist('paycheck_ids')
            if paycheck_ids:
                paychecks = PaycheckTransaction.objects.filter(id__in=paycheck_ids)
                for paycheck in paychecks:
                    if paycheck.template:
                        template = paycheck.template
                        date_str = paycheck.date.strftime('%Y-%m-%d')
                        if date_str not in template.skipped_dates:
                            template.skipped_dates.append(date_str)
                            template.save()
                paychecks.delete()

        # 3. Delete Recurring Rule Card
        elif request.POST.get('delete_rule_id'):
            rule = get_object_or_404(PaycheckTemplate, pk=request.POST.get('delete_rule_id'))
            rule.delete()

        # 4. Create or Edit Recurring Rule Template
        elif request.POST.get('form_type') == 'recurring':
            rule_id = request.POST.get('rule_id')
            if rule_id:
                instance = get_object_or_404(PaycheckTemplate, pk=rule_id)
                template_form = PaycheckTemplateForm(request.POST, instance=instance)
                if template_form.is_valid():
                    template = template_form.save()
                    
                    # 💡 Delete existing rows linked to this template
                    PaycheckTransaction.objects.filter(template=template).delete()
                    
                    # 💡 Regenerate historical rows (will now skip dates saved in template.skipped_dates!)
                    template.generate_historical_paychecks()
            else:
                template_form = PaycheckTemplateForm(request.POST)
                if template_form.is_valid():
                    template = template_form.save()
                    template.generate_historical_paychecks()

            return redirect('income')

        # 5. Create or Edit Single Paycheck
        else:
            paycheck_id = request.POST.get('paycheck_id')
            if paycheck_id:
                instance = get_object_or_404(PaycheckTransaction, pk=paycheck_id)
                form = PaycheckTransactionForm(request.POST, instance=instance)
            else:
                form = PaycheckTransactionForm(request.POST)

            if form.is_valid():
                form.save()

        if request.headers.get('HX-Request'):
            paychecks = PaycheckTransaction.objects.all()
            return render(request, "transactions/_income_table.html", {'paychecks': paychecks, 'current_filters': {}})

        return redirect('income')

    # --- GET REQUEST ---
    active_templates = PaycheckTemplate.objects.all()
    for template in active_templates:
        template.sync_missing_paychecks()

    paycheck_form = PaycheckTransactionForm()
    template_form = PaycheckTemplateForm()
    paychecks = PaycheckTransaction.objects.all()

    # Filters
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if start_date:
        paychecks = paychecks.filter(date__gte=start_date)
    if end_date:
        paychecks = paychecks.filter(date__lte=end_date)

    search_query = request.GET.get('search', '')
    if search_query:
        paychecks = paychecks.filter(source_name__icontains=search_query)

    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    if min_amount:
        paychecks = paychecks.filter(amount__gte=float(min_amount))
    if max_amount:
        paychecks = paychecks.filter(amount__lte=float(max_amount))

    # Sorting
    sort_by = request.GET.get('sort_by', 'date')
    direction = request.GET.get('direction', 'desc')
    allowed_sort = {'date': 'date', 'source_name': 'source_name', 'amount': 'amount'}
    db_field = allowed_sort.get(sort_by, 'date')

    if direction == 'desc':
        paychecks = paychecks.order_by(f'-{db_field}')
    else:
        paychecks = paychecks.order_by(db_field)

    next_direction = 'asc' if direction == 'desc' else 'desc'

    context = {
        'paycheck_form': paycheck_form,
        'template_form': template_form,
        'paychecks': paychecks,
        'active_templates': active_templates,
        'current_filters': {
            'search': search_query,
            'start_date': start_date,
            'end_date': end_date,
            'min_amount': min_amount,
            'max_amount': max_amount,
            'sort_by': sort_by,
            'direction': direction,
            'next_direction': next_direction,
        }
    }

    if request.headers.get('HX-Request'):
        return render(request, "transactions/_income_table.html", context)

    return render(request, "transactions/income.html", context)

def budget(request):
    return render(request, 'transactions/budget.html')

def analytics(request):
    return render(request, 'transactions/analytics.html')

def settings(request):
    return render(request, 'transactions/settings.html')