from django.shortcuts import render, redirect, get_object_or_404
from .forms import TransactionForm
from .models import Transaction

def home(request):
    if request.method == "POST":
        delete_id = request.POST.get('delete_id')
        transaction_id = request.POST.get('transaction_id')
        
        # 1. Handle Delete Action
        if delete_id:
            transaction = get_object_or_404(Transaction, pk=delete_id)
            transaction.delete()
            return redirect('home')

        # 2. Handle Add / Edit Actions
        if transaction_id:
            instance = get_object_or_404(Transaction, pk=transaction_id)
            form = TransactionForm(request.POST, instance=instance)
        else:
            form = TransactionForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = TransactionForm()

    transactions = Transaction.objects.all().order_by('-date')

    return render(request, "transactions/home.html", {
        'form': form,
        'transactions': transactions
    })