from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from .forms import TransactionForm, PaycheckTransactionForm, PaycheckTemplateForm
from .models import Transaction, PaycheckTransaction, PaycheckTemplate, Category
from django.db.models import Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth
from decimal import Decimal
import calendar

def home(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')
        delete_id = request.POST.get('delete_id')
        transaction_id = request.POST.get('transaction_id')

        # 1. Handle Bulk Delete[cite: 10]
        if action_type == 'bulk_delete' or request.POST.get('bulk_delete'):
            transaction_ids = request.POST.getlist('transaction_ids')
            if transaction_ids:
                Transaction.objects.filter(id__in=transaction_ids).delete()

        # 2. Handle Single Row Delete[cite: 10]
        elif action_type == 'single_delete' or delete_id:
            target_id = delete_id or request.POST.get('delete_id')
            if target_id:
                transaction = get_object_or_404(Transaction, pk=target_id)
                transaction.delete()

        # 3. Handle Add / Edit Transaction[cite: 10]
        else:
            if transaction_id:
                instance = get_object_or_404(Transaction, pk=transaction_id)
                form = TransactionForm(request.POST, instance=instance)
            else:
                form = TransactionForm(request.POST)

            if form.is_valid():
                form.save()

        # HTMX Check: Return re-rendered partial template[cite: 10]
        if request.headers.get('HX-Request'):
            form = TransactionForm()
            transactions = Transaction.objects.all().order_by('-date')
            
            # 💡 Paginate POST re-renders (25 items per page)[cite: 10]
            paginator = Paginator(transactions, 25)
            page_obj = paginator.get_page(1)

            context = {
                'form': form,
                'transactions': page_obj,  # Pass page_obj[cite: 10]
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
            
    # --- GET REQUEST: ADVANCED FILTERING & SORTING ---[cite: 10]
    form = TransactionForm()
    transactions = Transaction.objects.all()

    # 1. Multi-Select Categories[cite: 10]
    selected_categories = request.GET.getlist('category')
    if selected_categories:
        transactions = transactions.filter(category__in=selected_categories)

    # 2. Date Range[cite: 10]
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)

    # 3. Description Search[cite: 10]
    search_query = request.GET.get('search', '')
    if search_query:
        transactions = transactions.filter(description__icontains=search_query)

    # 4. Amount Filter[cite: 10]
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')

    if min_amount:
        transactions = transactions.filter(amount__gte=float(min_amount))
        
    if max_amount:
        transactions = transactions.filter(amount__lte=float(max_amount))

    # 5. Sorting[cite: 10]
    sort_by = request.GET.get('sort_by', 'date')
    direction = request.GET.get('direction', 'desc')

    allowed_sort = {'date': 'date', 'description': 'description', 'category': 'category', 'amount': 'amount'}
    db_field = allowed_sort.get(sort_by, 'date')
    
    if direction == 'desc':
        transactions = transactions.order_by(f'-{db_field}')
    else:
        transactions = transactions.order_by(db_field)

    next_direction = 'asc' if direction == 'desc' else 'desc'

    # 💡 6. Server-Side Pagination (25 items per page)[cite: 10]
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'transactions': page_obj,  # 💡 Pass page_obj[cite: 10]
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
                    PaycheckTransaction.objects.filter(template=template).delete()
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

        # HTMX Check on POST re-render
        if request.headers.get('HX-Request'):
            paychecks = PaycheckTransaction.objects.all().order_by('-date')
            paginator = Paginator(paychecks, 25)
            page_obj = paginator.get_page(1)
            return render(request, "transactions/_income_table.html", {'paychecks': page_obj, 'current_filters': {}})

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

    # 💡 6. Server-Side Pagination (25 paychecks per page)
    paginator = Paginator(paychecks, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'paycheck_form': paycheck_form,
        'template_form': template_form,
        'paychecks': page_obj,  # Pass page_obj
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
    # 1. Multi-Select Filters
    selected_years = request.GET.getlist('year')
    selected_months = request.GET.getlist('month')
    selected_categories = request.GET.getlist('category')

    # Convert month, year, and category ID string values to integers if provided
    selected_months = [int(m) for m in selected_months if m.isdigit()]
    selected_years = [int(y) for y in selected_years if y.isdigit()]
    selected_category_ids = [int(c) for c in selected_categories if c.isdigit()]

    # QuerySets
    expense_qs = Transaction.objects.all()
    income_qs = PaycheckTransaction.objects.all()

    # Apply Expense Category Filter
    if selected_category_ids:
        expense_qs = expense_qs.filter(category__id__in=selected_category_ids)

    # Apply Year Filters
    if selected_years:
        expense_qs = expense_qs.filter(date__year__in=selected_years)
        income_qs = income_qs.filter(date__year__in=selected_years)

    # Apply Month Filters
    if selected_months:
        expense_qs = expense_qs.filter(date__month__in=selected_months)
        income_qs = income_qs.filter(date__month__in=selected_months)

    # 2. KPI Calculations
    total_spend = expense_qs.aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']

    total_income = income_qs.aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']

    net_savings = total_income - total_spend
    savings_rate = (net_savings / total_income * 100) if total_income > 0 else 0

    # 3. Graph Data: Total Spend by Category (Horizontal Bar Chart)
    cat_breakdown = (
        expense_qs.values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    cat_labels = [c['category__name'] if c['category__name'] else 'Uncategorized' for c in cat_breakdown]
    cat_data = [float(c['total']) for c in cat_breakdown]

    # 4. Graph Data: Spend vs Income by Month (Combo Bar + Line Chart)
    monthly_expense = (
        expense_qs.annotate(year=ExtractYear('date'), month=ExtractMonth('date'))
        .values('year', 'month')
        .annotate(total=Sum('amount'))
    )
    monthly_income = (
        income_qs.annotate(year=ExtractYear('date'), month=ExtractMonth('date'))
        .values('year', 'month')
        .annotate(total=Sum('amount'))
    )

    exp_map = {(m['year'], m['month']): float(m['total']) for m in monthly_expense}
    inc_map = {(m['year'], m['month']): float(m['total']) for m in monthly_income}

    all_keys = sorted(list(set(exp_map.keys()) | set(inc_map.keys())))
    
    trend_labels = [f"{calendar.month_abbr[m]} {y}" for y, m in all_keys]
    trend_spend = [exp_map.get(k, 0.0) for k in all_keys]
    trend_income = [inc_map.get(k, 0.0) for k in all_keys]

    # 5. Populate Filter Dropdown Options
    all_years = sorted(list(set(
        list(Transaction.objects.dates('date', 'year').values_list('date__year', flat=True)) +
        list(PaycheckTransaction.objects.dates('date', 'year').values_list('date__year', flat=True))
    )), reverse=True)

    month_choices = [(i, calendar.month_abbr[i]) for i in range(1, 13)]
    category_options = Category.objects.all()

    # 6. Table List & Server-Side Pagination (15 items per page for analytics layout)
    transactions_list = expense_qs.order_by('-date')
    paginator = Paginator(transactions_list, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        # KPIs
        'total_income': total_income,
        'total_spend': total_spend,
        'net_savings': net_savings,
        'savings_rate': savings_rate,

        # Chart JSON arrays
        'cat_labels': cat_labels,
        'cat_data': cat_data,
        'trend_labels': trend_labels,
        'trend_spend': trend_spend,
        'trend_income': trend_income,

        # Filter Options & Selections
        'selected_years': selected_years,
        'selected_months': selected_months,
        'selected_categories': selected_category_ids,
        'available_years': all_years,
        'month_choices': month_choices,
        'category_options': category_options,

        # Table Data (Paginated Object)
        'transactions': page_obj,
    }

    if request.headers.get('HX-Request'):
        return render(request, "transactions/_analytics_content.html", context)

    return render(request, "transactions/analytics.html", context)

def settings(request):
    if request.method == "POST":
        action = request.POST.get('action')

        # 1. Add New Category
        if action == 'add_category':
            category_name = request.POST.get('name', '').strip()
            if category_name:
                Category.objects.get_or_create(name=category_name)

        # 2. Edit Existing Category
        elif action == 'edit_category':
            category_id = request.POST.get('category_id')
            new_name = request.POST.get('name', '').strip()
            if category_id and new_name:
                cat = get_object_or_404(Category, pk=category_id)
                cat.name = new_name
                cat.save()

        # 3. Delete Category
        elif action == 'delete_category':
            category_id = request.POST.get('category_id')
            if category_id:
                cat = get_object_or_404(Category, pk=category_id)
                cat.delete()  # Foreign key set_null leaves transactions uncategorized

        return redirect('settings')

    # GET Request: Fetch categories (sorted alphabetically by Category Meta ordering)
    categories = Category.objects.all()
    return render(request, 'transactions/settings.html', {'categories': categories})