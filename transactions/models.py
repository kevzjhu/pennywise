from django.db import models
from django.contrib.auth.models import User 
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import date
from dateutil.relativedelta import relativedelta

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

DEFAULT_CATEGORIES = [
    {"name": "Clothes", "monthly_budget": 400.00},
    {"name": "Education", "monthly_budget": 100.00},
    {"name": "Entertainment", "monthly_budget": 100.00},
    {"name": "Groceries", "monthly_budget": 300.00},
    {"name": "Health", "monthly_budget": 100.00},
    {"name": "Home Improvement", "monthly_budget": 150.00},
    {"name": "Miscellaneous", "monthly_budget": 100.00},
    {"name": "Recurring Payment", "monthly_budget": 200.00},
    {"name": "Utilities", "monthly_budget": 150.00},
    {"name": "Rent", "monthly_budget": 1900.00},
    {"name": "Restaurants", "monthly_budget": 200.00},
    {"name": "Transportation", "monthly_budget": 100.00},
    {"name": "Travel", "monthly_budget": 200.00},
]

@receiver(post_save, sender=User)
def setup_new_user_account(sender, instance, created, **kwargs):
    if created:
        # Create user profile
        Profile.objects.create(user=instance)
        
        # Seed initial categories owned by this user
        categories_to_create = [
            Category(
                user=instance,
                name=cat["name"],
                monthly_budget=cat["monthly_budget"]
            )
            for cat in DEFAULT_CATEGORIES
        ]
        Category.objects.bulk_create(categories_to_create)
    else:
        instance.profile.save()

class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=50)
    monthly_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
        unique_together = ('user', 'name')

    def __str__(self):
        return f"{self.name}"

class CategoryBudget(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budget_history')
    effective_start_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['-effective_start_date']
        unique_together = ('category', 'effective_start_date')  # 👈 Prevents duplicate records on the same date

    def __str__(self):
        return f"{self.category.name} from {self.effective_start_date}: ${self.amount}"

class RecurringTransactionTemplate(models.Model):
    FREQUENCY_CHOICES = [
        ('WEEKLY', 'Weekly'),
        ('BI_WEEKLY', 'Bi-Weekly'),
        ('MONTHLY', 'Monthly'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recurring_templates')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank = True, null = True)
    created_at = models.DateTimeField(auto_now_add=True)
    skipped_dates = models.JSONField(default=list, blank=True)

    def generate_historical_transactions(self):
        current_date = self.start_date
        today = date.today()
        cutoff_date = min(today, self.end_date) if self.end_date else today

        if self.frequency == 'WEEKLY':
            step = relativedelta(weeks=1)
        elif self.frequency == 'BI_WEEKLY':
            step = relativedelta(weeks=2)
        elif self.frequency == 'MONTHLY':
            step = relativedelta(months=1)
        else:
            return 0

        skipped_set = set(self.skipped_dates or [])
        transactions_to_create = []

        while current_date <= cutoff_date:
            date_str = current_date.strftime('%Y-%m-%d')
            if date_str not in skipped_set:
                transactions_to_create.append(
                    Transaction(
                        user=self.user,
                        recurring_template=self,
                        description=self.description,
                        amount=self.amount,
                        category=self.category,
                        notes = self.notes,
                        date=current_date
                    )
                )
            current_date += step

        if transactions_to_create:
            Transaction.objects.bulk_create(transactions_to_create)
        return len(transactions_to_create)

    def sync_missing_transactions(self):
        existing_dates = set(
            self.transactions.values_list('date', flat=True)
        )
        existing_date_strings = {d.strftime('%Y-%m-%d') for d in existing_dates}
        ignored_dates = existing_date_strings.union(set(self.skipped_dates or []))

        current_date = self.start_date
        today = date.today()
        cutoff_date = min(today, self.end_date) if self.end_date else today

        if self.frequency == 'WEEKLY':
            step = relativedelta(weeks=1)
        elif self.frequency == 'BI_WEEKLY':
            step = relativedelta(weeks=2)
        elif self.frequency == 'MONTHLY':
            step = relativedelta(months=1)
        else:
            return 0

        transactions_to_create = []

        while current_date <= cutoff_date:
            date_str = current_date.strftime('%Y-%m-%d')
            if date_str not in ignored_dates:
                transactions_to_create.append(
                    Transaction(
                        user=self.user,
                        recurring_template=self,
                        description=self.description,
                        amount=self.amount,
                        category=self.category,
                        notes = self.notes,
                        date=current_date
                    )
                )
            current_date += step

        if transactions_to_create:
            Transaction.objects.bulk_create(transactions_to_create)


# Update Transaction model to link to RecurringTransactionTemplate
class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    recurring_template = models.ForeignKey(
        RecurringTransactionTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='transactions'
    )
    date = models.DateField(db_index=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.date} - {self.description} - ${self.amount}"

class PaycheckTemplate(models.Model):
    FREQUENCY_CHOICES = [
        ('WEEKLY', 'Weekly'),
        ('BI_WEEKLY', 'Bi-Weekly'),
        ('MONTHLY', 'Monthly'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paycheck_templates')  # 💡 Link to User
    source_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    skipped_dates = models.JSONField(default=list, blank=True)

    def generate_historical_paychecks(self):
        current_pay_date = self.start_date
        today = date.today()
        cutoff_date = min(today, self.end_date) if self.end_date else today
        
        if self.frequency == 'WEEKLY':
            step = relativedelta(weeks=1)
        elif self.frequency == 'BI_WEEKLY':
            step = relativedelta(weeks=2)
        elif self.frequency == 'MONTHLY':
            step = relativedelta(months=1)
        else:
            return 0

        skipped_set = set(self.skipped_dates or [])
        paychecks_to_create = []

        while current_pay_date <= cutoff_date:
            date_str = current_pay_date.strftime('%Y-%m-%d')
            
            if date_str not in skipped_set:
                paychecks_to_create.append(
                    PaycheckTransaction(
                        user=self.user,  # 💡 Set user on auto-generated paychecks
                        template=self,
                        source_name=self.source_name,
                        amount=self.amount,
                        notes = self.notes,
                        date=current_pay_date
                    )
                )
            current_pay_date += step

        if paychecks_to_create:
            PaycheckTransaction.objects.bulk_create(paychecks_to_create)
            
        return len(paychecks_to_create)

    def sync_missing_paychecks(self):
        existing_dates = set(
            self.paychecktransaction_set.values_list('date', flat=True)
        )
        existing_date_strings = {d.strftime('%Y-%m-%d') for d in existing_dates}
        ignored_dates = existing_date_strings.union(set(self.skipped_dates or []))

        current_pay_date = self.start_date
        today = date.today()
        cutoff_date = min(today, self.end_date) if self.end_date else today

        if self.frequency == 'WEEKLY':
            step = relativedelta(weeks=1)
        elif self.frequency == 'BI_WEEKLY':
            step = relativedelta(weeks=2)
        elif self.frequency == 'MONTHLY':
            step = relativedelta(months=1)
        else:
            return 0

        paychecks_to_create = []

        while current_pay_date <= cutoff_date:
            date_str = current_pay_date.strftime('%Y-%m-%d')
            if date_str not in ignored_dates:
                paychecks_to_create.append(
                    PaycheckTransaction(
                        user=self.user,  # 💡 Set user
                        template=self,
                        source_name=self.source_name,
                        amount=self.amount,
                        notes = self.notes,
                        date=current_pay_date
                    )
                )
            current_pay_date += step

        if paychecks_to_create:
            PaycheckTransaction.objects.bulk_create(paychecks_to_create)

class PaycheckTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paycheck_transactions')  # 💡 Link to User
    template = models.ForeignKey(PaycheckTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    source_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(db_index=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date']