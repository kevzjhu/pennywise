from django.shortcuts import render, redirect, get_object_or_404
from .forms import TransactionForm
from .models import Transaction

def home(request):
    if request.method == "POST":
        delete_id = request.POST.get('delete_id')
        transaction_id = request.POST.get('transaction_id')
        
        if delete_id:
            transaction = get_object_or_404(Transaction, pk=delete_id)
            transaction.delete()
            return redirect('home')

        if transaction_id:
            instance = get_object_or_404(Transaction, pk=transaction_id)
            form = TransactionForm(request.POST, instance=instance)
        else:
            form = TransactionForm(request.POST)

        if form.is_valid():
            form.save()
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

    # HTMX Check: Return partial template if requested via HTMX, otherwise full page
    if request.headers.get('HX-Request'):
        return render(request, "transactions/_table.html", context)

    return render(request, "transactions/home.html", context)