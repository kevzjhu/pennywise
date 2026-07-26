from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth import login
from .forms import TransactionForm, PaycheckTransactionForm, PaycheckTemplateForm, RecurringTransactionTemplateForm
from .models import Transaction, PaycheckTransaction, PaycheckTemplate, Category, CategoryBudget, RecurringTransactionTemplate
from django.db.models import Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth
from decimal import Decimal, InvalidOperation
import calendar
import datetime
from .services import validate_and_parse_wealthsimple_csv, validate_and_parse_rbc_csv

def get_home_context(request):
    """Helper to build and return the standard context dictionary for home.html."""
    active_templates = RecurringTransactionTemplate.objects.filter(user=request.user)
    for template in active_templates:
        template.sync_missing_transactions()

    form = TransactionForm()
    form.fields['category'].queryset = Category.objects.filter(user=request.user)
    
    recurring_form = RecurringTransactionTemplateForm()
    recurring_form.fields['category'].queryset = Category.objects.filter(user=request.user)

    transactions = Transaction.objects.filter(user=request.user)

    # Filter & Sort queries...
    selected_categories = request.GET.getlist('category')
    if selected_categories:
        transactions = transactions.filter(category__in=selected_categories)

    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)

    search_query = request.GET.get('search', '')
    if search_query:
        transactions = transactions.filter(description__icontains=search_query)

    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    if min_amount:
        transactions = transactions.filter(amount__gte=float(min_amount))
    if max_amount:
        transactions = transactions.filter(amount__lte=float(max_amount))

    sort_by = request.GET.get('sort_by', 'date')
    direction = request.GET.get('direction', 'desc')
    allowed_sort = {'date': 'date', 'description': 'description', 'category': 'category', 'amount': 'amount'}
    db_field = allowed_sort.get(sort_by, 'date')

    if direction == 'desc':
        transactions = transactions.order_by(f'-{db_field}')
    else:
        transactions = transactions.order_by(db_field)

    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return {
        'form': form,
        'recurring_form': recurring_form,
        'transactions': page_obj,
        'active_templates': active_templates,
        'current_filters': {
            'search': search_query, 'categories': selected_categories, 'start_date': start_date,
            'end_date': end_date, 'min_amount': min_amount, 'max_amount': max_amount,
            'sort_by': sort_by, 'direction': direction, 'next_direction': 'asc' if direction == 'desc' else 'desc',
        }
    }

@login_required
def home(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')

        # 1. Stage CSV for Review
        if action_type == 'stage_csv':
            csv_file = request.FILES.get('csv_file')
            bank = request.POST.get('bank')

            try:
                if bank == 'wealthsimple':
                    candidate_rows = validate_and_parse_wealthsimple_csv(csv_file, request.user)
                elif bank == 'rbc':
                    candidate_rows = validate_and_parse_rbc_csv(csv_file, request.user)
                else:
                    raise ValueError(f"CSV parsing for '{bank.upper()}' is not supported yet.")

                user_categories = Category.objects.filter(user=request.user)

                context = get_home_context(request)
                context.update({
                    'show_review_modal': True,
                    'candidate_rows': candidate_rows,
                    'user_categories': user_categories,
                })
                return render(request, "transactions/home.html", context)

            except ValueError as e:
                context = get_home_context(request)
                context.update({
                    'csv_error': str(e),
                    'show_import_modal': True,
                })
                return render(request, "transactions/home.html", context)

        # 2. Confirm CSV Import (Final Save Step)
        elif action_type == 'confirm_csv_import':
            selected_indices = request.POST.getlist('selected_rows')
            transactions_to_create = []

            for idx in selected_indices:
                raw_date = request.POST.get(f'date_{idx}')
                description = request.POST.get(f'description_{idx}', '').strip()
                raw_amount = request.POST.get(f'amount_{idx}', '0.00')
                category_id = request.POST.get(f'category_{idx}')

                # Require valid date, description, amount, and category for selected rows
                if raw_date and description and raw_amount and category_id:
                    try:
                        tx_date = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
                        amount = Decimal(raw_amount)
                        category = Category.objects.filter(user=request.user, pk=category_id).first()

                        if category:
                            transactions_to_create.append(
                                Transaction(
                                    user=request.user,
                                    date=tx_date,
                                    description=description,
                                    amount=amount,
                                    category=category
                                )
                            )
                    except (ValueError, InvalidOperation):
                        continue

            if transactions_to_create:
                Transaction.objects.bulk_create(transactions_to_create)

            return redirect('home')
        
        # 1. Handle Single Row Delete
        if action_type == 'single_delete' or request.POST.get('delete_id'):
            delete_id = request.POST.get('delete_id') or request.POST.get('single_delete')
            if delete_id:
                transaction = get_object_or_404(Transaction, pk=delete_id, user=request.user)
                if transaction.recurring_template:
                    template = transaction.recurring_template
                    date_str = transaction.date.strftime('%Y-%m-%d')
                    if date_str not in template.skipped_dates:
                        template.skipped_dates.append(date_str)
                        template.save()
                transaction.delete()

        # 2. Handle Bulk Delete
        elif action_type == 'bulk_delete' or request.POST.get('bulk_delete'):
            transaction_ids = request.POST.getlist('transaction_ids')
            if transaction_ids:
                transactions = Transaction.objects.filter(user=request.user, id__in=transaction_ids)
                for tx in transactions:
                    if tx.recurring_template:
                        template = tx.recurring_template
                        date_str = tx.date.strftime('%Y-%m-%d')
                        if date_str not in template.skipped_dates:
                            template.skipped_dates.append(date_str)
                            template.save()
                transactions.delete()

        # 3. Delete Recurring Rule Card (Does NOT delete existing transactions)
        elif request.POST.get('delete_rule_id'):
            rule = get_object_or_404(RecurringTransactionTemplate, pk=request.POST.get('delete_rule_id'), user=request.user)
            rule.delete()  # On delete SET_NULL keeps existing transactions!

        # 4. Create or Edit Recurring Rule Template
        elif request.POST.get('form_type') == 'recurring':
            rule_id = request.POST.get('rule_id')
            if rule_id:
                instance = get_object_or_404(RecurringTransactionTemplate, pk=rule_id, user=request.user)
                template_form = RecurringTransactionTemplateForm(request.POST, instance=instance)
                if template_form.is_valid():
                    template = template_form.save()
                    # Keep old posted transactions intact, only sync missing/future ones
                    template.sync_missing_transactions()
            else:
                template_form = RecurringTransactionTemplateForm(request.POST)
                if template_form.is_valid():
                    template = template_form.save(commit=False)
                    template.user = request.user
                    template.save()
                    template.generate_historical_transactions()

            return redirect('home')

        # 5. Handle Add / Edit Single Transaction
        else:
            transaction_id = request.POST.get('transaction_id')
            if transaction_id:
                instance = get_object_or_404(Transaction, pk=transaction_id, user=request.user)
                form = TransactionForm(request.POST, instance=instance)
            else:
                form = TransactionForm(request.POST)

            if form.is_valid():
                transaction = form.save(commit=False)
                transaction.user = request.user
                transaction.save()

        if request.headers.get('HX-Request'):
            form = TransactionForm()
            form.fields['category'].queryset = Category.objects.filter(user=request.user)
            transactions = Transaction.objects.filter(user=request.user).order_by('-date')
            paginator = Paginator(transactions, 25)
            page_obj = paginator.get_page(1)

            context = {
                'form': form,
                'transactions': page_obj,
                'current_filters': {
                    'search': '', 'categories': [], 'start_date': '', 'end_date': '',
                    'min_amount': '', 'max_amount': '', 'sort_by': 'date', 'direction': 'desc', 'next_direction': 'asc',
                }
            }
            return render(request, "transactions/_table.html", context)

        return redirect('home')

    # --- GET REQUEST ---
    active_templates = RecurringTransactionTemplate.objects.filter(user=request.user)
    for template in active_templates:
        template.sync_missing_transactions()

    form = TransactionForm()
    form.fields['category'].queryset = Category.objects.filter(user=request.user)
    
    recurring_form = RecurringTransactionTemplateForm()
    recurring_form.fields['category'].queryset = Category.objects.filter(user=request.user)

    transactions = Transaction.objects.filter(user=request.user)

    # Filter & Sort queries...
    selected_categories = request.GET.getlist('category')
    if selected_categories:
        transactions = transactions.filter(category__in=selected_categories)

    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)

    search_query = request.GET.get('search', '')
    if search_query:
        transactions = transactions.filter(description__icontains=search_query)

    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    if min_amount:
        transactions = transactions.filter(amount__gte=float(min_amount))
    if max_amount:
        transactions = transactions.filter(amount__lte=float(max_amount))

    sort_by = request.GET.get('sort_by', 'date')
    direction = request.GET.get('direction', 'desc')
    allowed_sort = {'date': 'date', 'description': 'description', 'category': 'category', 'amount': 'amount'}
    db_field = allowed_sort.get(sort_by, 'date')

    if direction == 'desc':
        transactions = transactions.order_by(f'-{db_field}')
    else:
        transactions = transactions.order_by(db_field)

    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'recurring_form': recurring_form,
        'transactions': page_obj,
        'active_templates': active_templates,
        'current_filters': {
            'search': search_query, 'categories': selected_categories, 'start_date': start_date,
            'end_date': end_date, 'min_amount': min_amount, 'max_amount': max_amount,
            'sort_by': sort_by, 'direction': direction, 'next_direction': 'asc' if direction == 'desc' else 'desc',
        }
    }

    if request.headers.get('HX-Request'):
        return render(request, "transactions/_table.html", context)

    return render(request, "transactions/home.html", context)


@login_required
def income(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')

        # 1. Single Row Delete
        if action_type == 'single_delete' or request.POST.get('delete_id'):
            delete_id = request.POST.get('delete_id')
            if delete_id:
                paycheck = get_object_or_404(PaycheckTransaction, pk=delete_id, user=request.user)
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
                paychecks = PaycheckTransaction.objects.filter(user=request.user, id__in=paycheck_ids)
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
            rule = get_object_or_404(PaycheckTemplate, pk=request.POST.get('delete_rule_id'), user=request.user)
            rule.delete()

        # 4. Create or Edit Recurring Rule Template
        elif request.POST.get('form_type') == 'recurring':
            rule_id = request.POST.get('rule_id')
            if rule_id:
                instance = get_object_or_404(PaycheckTemplate, pk=rule_id, user=request.user)
                template_form = PaycheckTemplateForm(request.POST, instance=instance)
                if template_form.is_valid():
                    template = template_form.save()
                    PaycheckTransaction.objects.filter(user=request.user, template=template).delete()
                    template.generate_historical_paychecks()
            else:
                template_form = PaycheckTemplateForm(request.POST)
                if template_form.is_valid():
                    template = template_form.save(commit=False)
                    template.user = request.user
                    template.save()
                    template.generate_historical_paychecks()

            return redirect('income')

        # 5. Create or Edit Single Paycheck
        else:
            paycheck_id = request.POST.get('paycheck_id')
            if paycheck_id:
                instance = get_object_or_404(PaycheckTransaction, pk=paycheck_id, user=request.user)
                form = PaycheckTransactionForm(request.POST, instance=instance)
            else:
                form = PaycheckTransactionForm(request.POST)

            if form.is_valid():
                paycheck = form.save(commit=False)
                paycheck.user = request.user
                paycheck.save()

        if request.headers.get('HX-Request'):
            paychecks = PaycheckTransaction.objects.filter(user=request.user).order_by('-date')
            paginator = Paginator(paychecks, 25)
            page_obj = paginator.get_page(1)
            return render(request, "transactions/_income_table.html", {'paychecks': page_obj, 'current_filters': {}})

        return redirect('income')

    # --- GET REQUEST ---
    active_templates = PaycheckTemplate.objects.filter(user=request.user)
    for template in active_templates:
        template.sync_missing_paychecks()

    paycheck_form = PaycheckTransactionForm()
    template_form = PaycheckTemplateForm()
    paychecks = PaycheckTransaction.objects.filter(user=request.user)

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

    paginator = Paginator(paychecks, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'paycheck_form': paycheck_form,
        'template_form': template_form,
        'paychecks': page_obj,
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


@login_required
def analytics(request):
    selected_years = request.GET.getlist('year')
    selected_months = request.GET.getlist('month')
    selected_categories = request.GET.getlist('category')

    selected_months = [int(m) for m in selected_months if m.isdigit()]
    selected_years = [int(y) for y in selected_years if y.isdigit()]
    selected_category_ids = [int(c) for c in selected_categories if c.isdigit()]

    # Scope QuerySets to user
    expense_qs = Transaction.objects.filter(user=request.user)
    income_qs = PaycheckTransaction.objects.filter(user=request.user)

    if selected_category_ids:
        expense_qs = expense_qs.filter(category__id__in=selected_category_ids)

    if selected_years:
        expense_qs = expense_qs.filter(date__year__in=selected_years)
        income_qs = income_qs.filter(date__year__in=selected_years)

    if selected_months:
        expense_qs = expense_qs.filter(date__month__in=selected_months)
        income_qs = income_qs.filter(date__month__in=selected_months)

    all_years = sorted(list(set(
        list(Transaction.objects.filter(user=request.user).dates('date', 'year').values_list('date__year', flat=True)) +
        list(PaycheckTransaction.objects.filter(user=request.user).dates('date', 'year').values_list('date__year', flat=True))
    )), reverse=True)

    target_years = selected_years if selected_years else (all_years if all_years else [datetime.date.today().year])
    target_months = selected_months if selected_months else list(range(1, 13))

    # KPIs
    total_spend = expense_qs.aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']

    total_income = income_qs.aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']

    net_savings = total_income - total_spend
    savings_rate = (net_savings / total_income * 100) if total_income > 0 else 0

    categories_qs = Category.objects.filter(user=request.user)
    if selected_category_ids:
        categories_qs = categories_qs.filter(id__in=selected_category_ids)

    cat_labels = []
    cat_spend = []
    cat_budgets = []
    budget_progress_list = []
    total_budget_sum = Decimal('0.00')

    # 💡 RESOLVE HISTORICAL BUDGET FOR EACH TARGET MONTH
    for cat in categories_qs:
        spend = expense_qs.filter(category=cat).aggregate(
            total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
        )['total']

        history_records = list(cat.budget_history.order_by('effective_start_date'))

        target_budget = Decimal('0.00')
        for y in target_years:
            for m in target_months:
                # End of month date boundary
                month_end = datetime.date(y, m, calendar.monthrange(y, m)[1])

                # Find the latest budget effective on or before the end of this month
                active_budget = cat.monthly_budget # default fallback
                for record in history_records:
                    if record.effective_start_date <= month_end:
                        active_budget = record.amount
                    else:
                        break

                target_budget += active_budget

        total_budget_sum += target_budget

        percent_used = float((spend / target_budget * 100)) if target_budget > 0 else (100.0 if spend > 0 else 0.0)

        if percent_used > 100:
            status_color = 'bg-red-500'
            text_color = 'text-red-600'
        elif percent_used >= 80:
            status_color = 'bg-amber-500'
            text_color = 'text-amber-600'
        else:
            status_color = 'bg-emerald-500'
            text_color = 'text-emerald-600'

        cat_labels.append(cat.name)
        cat_spend.append(float(spend))
        cat_budgets.append(float(target_budget))

        budget_progress_list.append({
            'name': cat.name,
            'spend': spend,
            'budget': target_budget,
            'percent': min(percent_used, 100),
            'raw_percent': percent_used,
            'status_color': status_color,
            'text_color': text_color,
        })

    uncategorized_spend = expense_qs.filter(category__isnull=True).aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']

    if uncategorized_spend > 0:
        cat_labels.append('Uncategorized')
        cat_spend.append(float(uncategorized_spend))
        cat_budgets.append(0.0)

    # Monthly Trends
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

    month_choices = [(i, calendar.month_abbr[i]) for i in range(1, 13)]
    category_options = Category.objects.filter(user=request.user)

    transactions_list = expense_qs.order_by('-date')
    paginator = Paginator(transactions_list, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'total_income': total_income,
        'total_spend': total_spend,
        'net_savings': net_savings,
        'savings_rate': savings_rate,
        'total_budget': total_budget_sum,
        'cat_labels': cat_labels,
        'cat_spend': cat_spend,
        'cat_budgets': cat_budgets,
        'trend_labels': trend_labels,
        'trend_spend': trend_spend,
        'trend_income': trend_income,
        'budget_progress_list': budget_progress_list,
        'selected_years': selected_years,
        'selected_months': selected_months,
        'selected_categories': selected_category_ids,
        'available_years': all_years,
        'month_choices': month_choices,
        'category_options': category_options,
        'transactions': page_obj,
    }

    if request.headers.get('HX-Request'):
        return render(request, "transactions/_analytics_content.html", context)

    return render(request, "transactions/analytics.html", context)

@login_required
def settings(request):
    if request.method == "POST":
        action = request.POST.get('action')
        today = datetime.date.today()

        # 1. Add New Category
        if action == 'add_category':
            category_name = request.POST.get('name', '').strip()
            raw_budget = request.POST.get('monthly_budget', '0.00')
            try:
                monthly_budget = Decimal(raw_budget) if raw_budget else Decimal('0.00')
            except InvalidOperation:
                monthly_budget = Decimal('0.00')

            if category_name:
                cat, created = Category.objects.get_or_create(
                    user=request.user, 
                    name=category_name, 
                    defaults={'monthly_budget': monthly_budget}
                )
                if not created:
                    cat.monthly_budget = monthly_budget
                    cat.save()

                # Log effective date record
                CategoryBudget.objects.create(
                    category=cat,
                    effective_start_date=today,
                    amount=monthly_budget
                )

        # 2. Edit Category Budget
        elif action == 'edit_category':
            category_id = request.POST.get('category_id')
            new_name = request.POST.get('name', '').strip()
            raw_budget = request.POST.get('monthly_budget', '0.00')

            if category_id and new_name:
                cat = get_object_or_404(Category, pk=category_id, user=request.user)
                cat.name = new_name
                try:
                    monthly_budget = Decimal(raw_budget) if raw_budget else Decimal('0.00')
                except InvalidOperation:
                    monthly_budget = Decimal('0.00')
                
                cat.monthly_budget = monthly_budget  # Updates current baseline
                cat.save()

                # Safely handle edits made on the exact same day
                todays_record = CategoryBudget.objects.filter(
                    category=cat, 
                    effective_start_date=today
                )
                
                if todays_record.exists():
                    todays_record.update(amount=monthly_budget)
                else:
                    CategoryBudget.objects.create(
                        category=cat,
                        effective_start_date=today,
                        amount=monthly_budget
                    )
        # 3. Delete Category
        elif action == 'delete_category':
            category_id = request.POST.get('category_id')
            if category_id:
                cat = get_object_or_404(Category, pk=category_id, user=request.user)
                cat.delete()

        return redirect('settings')

    categories = Category.objects.filter(user=request.user)
    return render(request, 'transactions/settings.html', {'categories': categories})

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Default starter categories with monthly targets
            default_categories = [
                {'name': 'Groceries', 'monthly_budget': Decimal('500.00')},
                {'name': 'Home / Rent', 'monthly_budget': Decimal('1200.00')},
                {'name': 'Utilities', 'monthly_budget': Decimal('150.00')},
                {'name': 'Entertainment', 'monthly_budget': Decimal('100.00')},
                {'name': 'Health & Fitness', 'monthly_budget': Decimal('80.00')},
                {'name': 'Clothes', 'monthly_budget': Decimal('100.00')},
                {'name': 'General', 'monthly_budget': Decimal('200.00')},
            ]

            # Bulk create default categories for the new user
            Category.objects.bulk_create([
                Category(user=user, name=cat['name'], monthly_budget=cat['monthly_budget'])
                for cat in default_categories
            ])
            
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

