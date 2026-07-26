from django.contrib import admin
from django.contrib.auth.models import User
from .models import Transaction, PaycheckTemplate, PaycheckTransaction, Category
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, DateWidget, DecimalWidget
from import_export.admin import ImportExportModelAdmin
from decimal import Decimal, InvalidOperation


class CleanDecimalWidget(DecimalWidget):
    """
    Custom widget to clean and parse decimal amounts during CSV/Excel import.
    Handles currency symbols ($), commas, and negative values gracefully.
    """
    def clean(self, value, row=None, **kwargs):
        if value is None or str(value).strip() == '':
            return None
        clean_val = str(value).replace('$', '').replace(',', '').strip()
        try:
            return Decimal(clean_val)
        except InvalidOperation:
            raise ValueError(f"Invalid decimal amount: '{value}'")


class UserScopedCategoryWidget(ForeignKeyWidget):
    """
    Custom widget that looks up Category by name AND maps it to 
    the user specified in the import row (or falls back to first match).
    """
    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        
        username = row.get('user') if row else None
        if username:
            category = Category.objects.filter(name=value, user__username=username).first()
            if category:
                return category

        return Category.objects.filter(name=value).first()


# ---------------------------------------------------------------------------
# Resources (Import / Export Definitions)
# ---------------------------------------------------------------------------

class TransactionResource(resources.ModelResource):
    category = fields.Field(
        column_name='category',
        attribute='category',
        widget=UserScopedCategoryWidget(Category, field='name')
    )
    user = fields.Field(
        column_name='user',
        attribute='user',
        widget=ForeignKeyWidget(User, field='username')
    )
    date = fields.Field(
        column_name='date',
        attribute='date',
        widget=DateWidget(format='%Y-%m-%d')
    )
    amount = fields.Field(
        column_name='amount',
        attribute='amount',
        widget=CleanDecimalWidget()
    )

    class Meta:
        model = Transaction
        fields = ('id', 'user', 'date', 'description', 'amount', 'category', 'notes')
        import_id_fields = ()


class PaycheckTransactionResource(resources.ModelResource):
    user = fields.Field(
        column_name='user',
        attribute='user',
        widget=ForeignKeyWidget(User, field='username')
    )
    template = fields.Field(
        column_name='template',
        attribute='template',
        widget=ForeignKeyWidget(PaycheckTemplate, field='source_name')
    )
    date = fields.Field(
        column_name='date',
        attribute='date',
        widget=DateWidget(format='%Y-%m-%d')
    )
    amount = fields.Field(
        column_name='amount',
        attribute='amount',
        widget=CleanDecimalWidget()
    )

    class Meta:
        model = PaycheckTransaction
        fields = ('id', 'user', 'date', 'source_name', 'amount', 'template', 'notes')
        import_id_fields = ()


# ---------------------------------------------------------------------------
# Admin Registrations
# ---------------------------------------------------------------------------

@admin.register(Transaction)
class TransactionAdmin(ImportExportModelAdmin):
    resource_class = TransactionResource
    from_encoding = 'utf-8-sig'
    list_display = ('date', 'description', 'category', 'amount', 'user')
    list_filter = ('category', 'date', 'user')
    search_fields = ('description', 'notes')


@admin.register(PaycheckTransaction)
class PaycheckTransactionAdmin(ImportExportModelAdmin):  # 👈 Enabled Import/Export for Income
    resource_class = PaycheckTransactionResource
    from_encoding = 'utf-8-sig'
    list_display = ('date', 'source_name', 'amount', 'template', 'user')
    list_filter = ('date', 'source_name', 'user')
    search_fields = ('source_name', 'notes')


@admin.register(PaycheckTemplate)
class PaycheckTemplateAdmin(admin.ModelAdmin):
    list_display = ('source_name', 'amount', 'frequency', 'start_date', 'created_at')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'monthly_budget')
    list_filter = ('user',)
    search_fields = ('name',)