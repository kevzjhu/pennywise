from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'amount', 'category')
    list_filter = ('category',)
    search_fields = ('description',)
