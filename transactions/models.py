from django.db import models
from django.contrib.auth.models import User 
from datetime import date
from dateutil.relativedelta import relativedelta

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

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField(db_index=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='transactions'
    )
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
    
    class Meta:
        ordering = ['-date']