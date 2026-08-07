from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib.auth import login, update_session_auth_hash
from django.contrib import messages
from django.http import HttpResponse
from .forms import TransactionForm, PaycheckTransactionForm, PaycheckTemplateForm, RecurringTransactionTemplateForm, ProfileForm
from .models import Transaction, PaycheckTransaction, PaycheckTemplate, Category, CategoryBudget, RecurringTransactionTemplate, Profile
from django.db import transaction as db_transaction
from decimal import Decimal, InvalidOperation
import calendar
import datetime
import csv
from .analytics import (
    build_budget_progress,
    build_monthly_trends,
    build_sankey_flows,
    total_amount,
)
from .services import validate_and_parse_wealthsimple_csv, validate_and_parse_rbc_csv, validate_and_parse_td_csv


def parse_amount_param(raw):
    """Parse an amount filter from a query string. Returns None if it isn't a number."""
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_date_param(raw):
    """Parse a YYYY-MM-DD date filter from a query string. Returns None if malformed."""
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def sync_recurring_templates(templates):
    """Top up missing auto-generated rows for each of `templates`.

    Wrapped in a single transaction so a failed sync can't leave half the
    projected rows committed. Callers skip this on HTMX partial fetches so
    filtering, sorting and paging don't each trigger a write.
    """
    with db_transaction.atomic():
        for template in templates:
            template.sync_missing()


TRANSACTION_SORT_FIELDS = {
    'date': 'date',
    'description': 'description',
    'category': 'category',
    'amount': 'amount',
}

INCOME_SORT_FIELDS = {
    'date': 'date',
    'source_name': 'source_name',
    'amount': 'amount',
}

PAGE_SIZE = 25


class TableFilters:
    """The search / date / amount / sort params the transaction and income tables share.

    Parsing, validation, querying and the template's `current_filters` dict all
    live here so the two tables can't drift apart.
    """

    def __init__(self, request, sort_fields, search_field, supports_categories=False):
        self.sort_fields = sort_fields
        self.search_field = search_field
        self.supports_categories = supports_categories

        self.categories = [c for c in request.GET.getlist('category') if c.isdigit()]
        self.search = request.GET.get('search', '')
        self.start_date = request.GET.get('start_date', '')
        self.end_date = request.GET.get('end_date', '')
        self.min_amount = request.GET.get('min_amount', '')
        self.max_amount = request.GET.get('max_amount', '')
        self.sort_by = request.GET.get('sort_by', 'date')
        self.direction = request.GET.get('direction', 'desc')
        self.page = request.GET.get('page', 1)

    def apply(self, queryset):
        """Narrow and order `queryset`. Malformed params are ignored, not fatal."""
        if self.supports_categories and self.categories:
            queryset = queryset.filter(category__in=self.categories)

        if parse_date_param(self.start_date):
            queryset = queryset.filter(date__gte=self.start_date)
        if parse_date_param(self.end_date):
            queryset = queryset.filter(date__lte=self.end_date)

        if self.search:
            queryset = queryset.filter(**{f'{self.search_field}__icontains': self.search})

        low = parse_amount_param(self.min_amount)
        if low is not None:
            queryset = queryset.filter(amount__gte=low)
        high = parse_amount_param(self.max_amount)
        if high is not None:
            queryset = queryset.filter(amount__lte=high)

        db_field = self.sort_fields.get(self.sort_by, 'date')
        prefix = '-' if self.direction == 'desc' else ''
        return queryset.order_by(f'{prefix}{db_field}')

    def page_of(self, queryset, per_page=PAGE_SIZE):
        return Paginator(self.apply(queryset), per_page).get_page(self.page)

    def as_context(self):
        return {
            'search': self.search,
            'categories': self.categories,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'min_amount': self.min_amount,
            'max_amount': self.max_amount,
            'sort_by': self.sort_by,
            'direction': self.direction,
            'next_direction': 'asc' if self.direction == 'desc' else 'desc',
        }


def category_scoped_form(form_class, user, **kwargs):
    """Instantiate `form_class` with its category choices limited to `user`."""
    form = form_class(**kwargs)
    form.fields['category'].queryset = Category.objects.filter(user=user)
    return form


def get_home_context(request, sync=True):
    """Build the standard context dictionary for home.html (and its table partial)."""
    active_templates = RecurringTransactionTemplate.objects.filter(user=request.user)
    if sync:
        sync_recurring_templates(active_templates)

    filters = TableFilters(
        request, TRANSACTION_SORT_FIELDS, 'description', supports_categories=True
    )
    transactions = Transaction.objects.filter(user=request.user).select_related(
        'category', 'recurring_template'
    )

    return {
        'form': category_scoped_form(TransactionForm, request.user),
        'recurring_form': category_scoped_form(RecurringTransactionTemplateForm, request.user),
        'transactions': filters.page_of(transactions),
        'active_templates': active_templates,
        'current_filters': filters.as_context(),
    }

CSV_PARSERS = {
    'wealthsimple': validate_and_parse_wealthsimple_csv,
    'rbc': validate_and_parse_rbc_csv,
    'td': validate_and_parse_td_csv,
}


def stage_csv_for_review(request):
    """Parse an uploaded bank CSV and re-render home with the review modal open."""
    bank = request.POST.get('bank')
    parser = CSV_PARSERS.get(bank)

    try:
        if parser is None:
            raise ValueError(f"CSV parsing for '{(bank or 'unknown').upper()}' is not supported yet.")
        candidate_rows = parser(request.FILES.get('csv_file'), request.user)
    except ValueError as e:
        context = get_home_context(request)
        context.update({'csv_error': str(e), 'show_import_modal': True})
        return render(request, "transactions/home.html", context)

    context = get_home_context(request)
    context.update({
        'show_review_modal': True,
        'candidate_rows': candidate_rows,
        'user_categories': Category.objects.filter(user=request.user),
    })
    return render(request, "transactions/home.html", context)


def confirm_csv_import(request):
    """Persist the rows the user ticked in the review modal."""
    transactions_to_create = []

    for idx in request.POST.getlist('selected_rows'):
        raw_date = request.POST.get(f'date_{idx}')
        description = request.POST.get(f'description_{idx}', '').strip()
        raw_amount = request.POST.get(f'amount_{idx}', '0.00')
        category_id = request.POST.get(f'category_{idx}')

        # Require valid date, description, amount, and category for selected rows
        if not (raw_date and description and raw_amount and category_id):
            continue

        tx_date = parse_date_param(raw_date)
        amount = parse_amount_param(raw_amount)
        category = Category.objects.filter(user=request.user, pk=category_id).first()

        if tx_date and amount is not None and category:
            transactions_to_create.append(
                Transaction(
                    user=request.user,
                    date=tx_date,
                    description=description,
                    amount=amount,
                    category=category,
                )
            )

    if transactions_to_create:
        Transaction.objects.bulk_create(transactions_to_create)

    return redirect('home')


def delete_rows_and_skip_recurrences(queryset, template_attr):
    """Delete `queryset`, recording each row's date as skipped on its template.

    Without the skip the next sync would immediately re-create the row the user
    just deleted.
    """
    for row in queryset:
        template = getattr(row, template_attr)
        if template:
            template.skip(row.date)
    queryset.delete()


def save_recurring_template(request, form_class, model, redirect_to):
    """Create or update a recurring rule, then top up its projected rows.

    sync_missing() covers both cases: on a brand-new template nothing exists
    yet, so it generates the full history. On an edit it leaves already-posted
    rows (including manual overrides) untouched.
    """
    rule_id = request.POST.get('rule_id')

    if rule_id:
        instance = get_object_or_404(model, pk=rule_id, user=request.user)
        form = form_class(request.POST, instance=instance)
    else:
        form = form_class(request.POST)

    if form.is_valid():
        template = form.save(commit=False)
        template.user = request.user
        template.save()
        template.sync_missing()

    return redirect(redirect_to)


def save_single_row(request, form_class, model):
    """Create or update one transaction / paycheck owned by the current user."""
    row_id = request.POST.get('transaction_id') or request.POST.get('paycheck_id')
    if row_id:
        instance = get_object_or_404(model, pk=row_id, user=request.user)
        form = form_class(request.POST, instance=instance)
    else:
        form = form_class(request.POST)

    if form.is_valid():
        row = form.save(commit=False)
        row.user = request.user
        row.save()


@login_required
def home(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')

        if action_type == 'stage_csv':
            return stage_csv_for_review(request)

        if action_type == 'confirm_csv_import':
            return confirm_csv_import(request)

        if request.POST.get('form_type') == 'recurring':
            return save_recurring_template(
                request, RecurringTransactionTemplateForm, RecurringTransactionTemplate, 'home'
            )

        if action_type == 'single_delete' or request.POST.get('delete_id'):
            delete_id = request.POST.get('delete_id') or request.POST.get('single_delete')
            if delete_id:
                delete_rows_and_skip_recurrences(
                    Transaction.objects.filter(pk=delete_id, user=request.user),
                    'recurring_template',
                )

        elif action_type == 'bulk_delete' or request.POST.get('bulk_delete'):
            transaction_ids = request.POST.getlist('transaction_ids')
            if transaction_ids:
                delete_rows_and_skip_recurrences(
                    Transaction.objects.filter(user=request.user, id__in=transaction_ids),
                    'recurring_template',
                )

        # Deleting a rule card leaves its posted transactions alone (SET_NULL).
        elif request.POST.get('delete_rule_id'):
            rule = get_object_or_404(
                RecurringTransactionTemplate,
                pk=request.POST.get('delete_rule_id'),
                user=request.user,
            )
            rule.delete()

        else:
            save_single_row(request, TransactionForm, Transaction)

        if request.headers.get('HX-Request'):
            # Re-render the table honouring whatever filters are still active.
            return render(request, "transactions/_table.html", get_home_context(request, sync=False))

        return redirect('home')

    # --- GET REQUEST ---
    # Only sync on a full page load — HTMX partials (filter/sort/page) must not write.
    is_partial = bool(request.headers.get('HX-Request'))
    context = get_home_context(request, sync=not is_partial)

    template_name = "transactions/_table.html" if is_partial else "transactions/home.html"
    return render(request, template_name, context)


def get_income_context(request, sync=True):
    """Build the standard context dictionary for income.html (and its table partial)."""
    active_templates = PaycheckTemplate.objects.filter(user=request.user)
    if sync:
        sync_recurring_templates(active_templates)

    filters = TableFilters(request, INCOME_SORT_FIELDS, 'source_name')
    paychecks = PaycheckTransaction.objects.filter(user=request.user).select_related('template')

    return {
        'paycheck_form': PaycheckTransactionForm(),
        'template_form': PaycheckTemplateForm(),
        'paychecks': filters.page_of(paychecks),
        'active_templates': active_templates,
        'current_filters': filters.as_context(),
    }


@login_required
def income(request):
    if request.method == "POST":
        action_type = request.POST.get('action_type')

        if request.POST.get('form_type') == 'recurring':
            return save_recurring_template(
                request, PaycheckTemplateForm, PaycheckTemplate, 'income'
            )

        if action_type == 'single_delete' or request.POST.get('delete_id'):
            delete_id = request.POST.get('delete_id')
            if delete_id:
                delete_rows_and_skip_recurrences(
                    PaycheckTransaction.objects.filter(pk=delete_id, user=request.user),
                    'template',
                )

        elif action_type == 'bulk_delete' or request.POST.get('bulk_delete'):
            paycheck_ids = request.POST.getlist('paycheck_ids')
            if paycheck_ids:
                delete_rows_and_skip_recurrences(
                    PaycheckTransaction.objects.filter(user=request.user, id__in=paycheck_ids),
                    'template',
                )

        # Deleting a rule card leaves its posted paychecks alone (SET_NULL).
        elif request.POST.get('delete_rule_id'):
            rule = get_object_or_404(
                PaycheckTemplate, pk=request.POST.get('delete_rule_id'), user=request.user
            )
            rule.delete()

        else:
            save_single_row(request, PaycheckTransactionForm, PaycheckTransaction)

        if request.headers.get('HX-Request'):
            # Re-render the table honouring whatever filters are still active.
            return render(
                request, "transactions/_income_table.html", get_income_context(request, sync=False)
            )

        return redirect('income')

    # --- GET REQUEST ---
    # Only sync on a full page load — HTMX partials (filter/sort/page) must not write.
    is_partial = bool(request.headers.get('HX-Request'))
    context = get_income_context(request, sync=not is_partial)

    template_name = "transactions/_income_table.html" if is_partial else "transactions/income.html"
    return render(request, template_name, context)


class AnalyticsPeriod:
    """The year / month / category selection driving the analytics dashboard."""

    def __init__(self, request):
        self.years = [int(y) for y in request.GET.getlist('year') if y.isdigit()]
        self.months = [int(m) for m in request.GET.getlist('month') if m.isdigit()]
        self.category_ids = [int(c) for c in request.GET.getlist('category') if c.isdigit()]

    def narrow(self, queryset, by_category=False):
        if by_category and self.category_ids:
            queryset = queryset.filter(category__id__in=self.category_ids)
        if self.years:
            queryset = queryset.filter(date__year__in=self.years)
        if self.months:
            queryset = queryset.filter(date__month__in=self.months)
        return queryset

    def target_years(self, available_years):
        if self.years:
            return self.years
        return available_years or [datetime.date.today().year]

    def target_months(self):
        return self.months or list(range(1, 13))


def years_with_activity(user):
    """Descending list of years the user has any expense or income in."""
    expense_years = Transaction.objects.filter(user=user).dates('date', 'year')
    income_years = PaycheckTransaction.objects.filter(user=user).dates('date', 'year')
    years = {d.year for d in expense_years} | {d.year for d in income_years}
    return sorted(years, reverse=True)


@login_required
def analytics(request):
    period = AnalyticsPeriod(request)

    expense_qs = period.narrow(
        Transaction.objects.filter(user=request.user), by_category=True
    )
    income_qs = period.narrow(PaycheckTransaction.objects.filter(user=request.user))

    total_spend = total_amount(expense_qs)
    total_income = total_amount(income_qs)
    net_savings = total_income - total_spend

    available_years = years_with_activity(request.user)

    categories_qs = Category.objects.filter(user=request.user).prefetch_related('budget_history')
    if period.category_ids:
        categories_qs = categories_qs.filter(id__in=period.category_ids)

    context = {
        'total_income': total_income,
        'total_spend': total_spend,
        'net_savings': net_savings,
        'savings_rate': (net_savings / total_income * 100) if total_income > 0 else 0,
        # Rendered via |json_script in the template, so pass raw values not JSON strings
        'sankey_data': build_sankey_flows(expense_qs, income_qs, total_spend, total_income),
        'selected_years': period.years,
        'selected_months': period.months,
        'selected_categories': period.category_ids,
        'available_years': available_years,
        'month_choices': [(i, calendar.month_abbr[i]) for i in range(1, 13)],
        'category_options': Category.objects.filter(user=request.user),
        'transactions': Paginator(
            expense_qs.select_related('category').order_by('-date'), 15
        ).get_page(request.GET.get('page', 1)),
    }
    context.update(build_budget_progress(
        categories_qs, expense_qs, period.target_years(available_years), period.target_months()
    ))
    context.update(build_monthly_trends(expense_qs, income_qs))

    if request.headers.get('HX-Request'):
        return render(request, "transactions/_analytics_content.html", context)

    return render(request, "transactions/analytics.html", context)


@login_required
def budgets(request):
    """View to handle Category creation, editing, and deletion for Budgets."""
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

                cat.monthly_budget = monthly_budget
                cat.save()

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

        return redirect('budgets')

    categories = Category.objects.filter(user=request.user)
    return render(request, 'transactions/budgets.html', {'categories': categories})


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def settings(request):
    # Ensure profile exists for existing users
    profile, created = Profile.objects.get_or_create(user=request.user)

    # Both forms are always bound to something so re-rendering after a failed
    # POST can't hit an unbound local.
    profile_form = ProfileForm(instance=profile)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        action = request.POST.get('action')

        if action == 'upload_avatar':
            profile_form = ProfileForm(request.POST, request.FILES, instance=profile)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile picture updated successfully!')
                return redirect('settings')
            else:
                messages.error(request, 'Failed to upload profile picture. Please try again.')

        elif action == 'remove_avatar':
            if profile.avatar:
                profile.avatar.delete()
                messages.success(request, 'Profile picture removed.')
            return redirect('settings')

        elif action == 'change_password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Your password was successfully updated!')
                return redirect('settings')
            else:
                messages.error(request, 'Please correct the password errors below.')

        else:
            messages.error(request, 'Unrecognised action.')

    context = {
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'transactions/settings.html', context)

@login_required
def export_transactions_csv(request):
    """Exports user transactions as a CSV within a selected timeframe."""
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    queryset = Transaction.objects.filter(user=request.user)

    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    queryset = queryset.order_by('-date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pennywise_transactions.csv"'

    writer = csv.writer(response)
    writer.writerow(['date', 'description', 'amount', 'category', 'notes'])

    for tx in queryset:
        category_name = tx.category.name if tx.category else 'Uncategorized'
        writer.writerow([
            tx.date.strftime('%Y-%m-%d'),
            tx.description,
            tx.amount,
            category_name,
            tx.notes or ''
        ])

    return response


@login_required
def export_income_csv(request):
    """Exports user income entries as a CSV within a selected timeframe."""
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    queryset = PaycheckTransaction.objects.filter(user=request.user)

    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    queryset = queryset.order_by('-date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pennywise_income.csv"'

    writer = csv.writer(response)
    writer.writerow(['date', 'source_name', 'amount', 'notes'])

    for paycheck in queryset:
        writer.writerow([
            paycheck.date.strftime('%Y-%m-%d'),
            paycheck.source_name,
            paycheck.amount,
            paycheck.notes or ''
        ])

    return response
