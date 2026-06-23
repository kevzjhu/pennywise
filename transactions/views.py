from django.shortcuts import render, redirect
from .forms import TransactionForm
from .models import Transaction

# Create your views here.
def home(request):
    if request.method == "POST":
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