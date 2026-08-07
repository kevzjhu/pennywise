from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import date
from dateutil.relativedelta import relativedelta

DATE_KEY_FORMAT = '%Y-%m-%d'

FREQUENCY_CHOICES = [
    ('WEEKLY', 'Weekly'),
    ('BI_WEEKLY', 'Bi-Weekly'),
    ('MONTHLY', 'Monthly'),
]

FREQUENCY_STEPS = {
    'WEEKLY': relativedelta(weeks=1),
    'BI_WEEKLY': relativedelta(weeks=2),
    'MONTHLY': relativedelta(months=1),
}


class RecurringSchedule:
    """Calendar behaviour shared by the templates that project rows forward.

    A plain mixin rather than an abstract model, so the concrete models keep
    their own field declarations and no migration is needed. Expects
    `frequency`, `start_date`, `end_date` and `skipped_dates` on the host.
    """

    def build_row(self, when):
        """Return an unsaved row for the occurrence on `when`."""
        raise NotImplementedError

    def existing_dates(self):
        """Dates already covered by a stored row for this template."""
        raise NotImplementedError

    def create_for_dates(self, dates):
        rows = [self.build_row(when) for when in dates]
        if rows:
            type(rows[0]).objects.bulk_create(rows)
        return len(rows)

    def generate_history(self):
        """Create every row this schedule projects, ignoring what already exists."""
        return self.create_for_dates(self.scheduled_dates())

    def sync_missing(self):
        """Create only the projected rows that don't exist yet."""
        return self.create_for_dates(self.scheduled_dates(excluding=self.existing_dates()))

    def scheduled_dates(self, excluding=()):
        """Yield every date this schedule projects, minus skips and `excluding`."""
        step = FREQUENCY_STEPS.get(self.frequency)
        if step is None:
            return

        excluded = set(self.skipped_dates or [])
        excluded.update(d.strftime(DATE_KEY_FORMAT) for d in excluding)

        today = date.today()
        cutoff_date = min(today, self.end_date) if self.end_date else today
        current_date = self.start_date

        while current_date <= cutoff_date:
            if current_date.strftime(DATE_KEY_FORMAT) not in excluded:
                yield current_date
            current_date += step

    def skip(self, when):
        """Record `when` as skipped so later syncs don't re-create that row."""
        date_key = when.strftime(DATE_KEY_FORMAT)
        if date_key not in self.skipped_dates:
            self.skipped_dates.append(date_key)
            self.save(update_fields=['skipped_dates'])


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

class RecurringTransactionTemplate(RecurringSchedule, models.Model):
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

    def build_row(self, when):
        return Transaction(
            user=self.user,
            recurring_template=self,
            description=self.description,
            amount=self.amount,
            category=self.category,
            notes=self.notes,
            date=when,
        )

    def existing_dates(self):
        return self.transactions.values_list('date', flat=True)


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

class PaycheckTemplate(RecurringSchedule, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paycheck_templates')  # 💡 Link to User
    source_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    skipped_dates = models.JSONField(default=list, blank=True)

    def build_row(self, when):
        return PaycheckTransaction(
            user=self.user,  # 💡 Set user on auto-generated paychecks
            template=self,
            source_name=self.source_name,
            amount=self.amount,
            notes=self.notes,
            date=when,
        )

    def existing_dates(self):
        return self.paychecktransaction_set.values_list('date', flat=True)

class PaycheckTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paycheck_transactions')  # 💡 Link to User
    template = models.ForeignKey(PaycheckTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    source_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(db_index=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date']
