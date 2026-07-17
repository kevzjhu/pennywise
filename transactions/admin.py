from django.contrib import admin
from .models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    # Customize what columns show up in the admin table list
    list_display = ('date', 'description', 'amount', 'category', 'notes')
    
    # Add filtering options on the right sidebar
    list_filter = ('category', 'date')
    
    # Add a search bar for quick lookups
    search_fields = ('description', 'notes')