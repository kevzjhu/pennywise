from django.contrib import admin
from .models import Transaction, PaycheckTemplate, PaycheckTransaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'category', 'amount')
    list_filter = ('category', 'date')
    search_fields = ('description', 'notes')

@admin.register(PaycheckTemplate)
class PaycheckTemplateAdmin(admin.ModelAdmin):
    # Removed 'user' from list_display
    list_display = ('source_name', 'amount', 'frequency', 'start_date', 'created_at')

@admin.register(PaycheckTransaction)
class PaycheckTransactionAdmin(admin.ModelAdmin):
    # Removed 'user' from list_display
    list_display = ('date', 'source_name', 'amount', 'template')
    list_filter = ('date', 'source_name')
    search_fields = ('source_name',)