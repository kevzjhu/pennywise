from django.db import models


class Transaction(models.Model):
    CATEGORY_CHOICES = [
        ('groceries', 'Groceries'),
        ('transportation', 'Transportation'),
        ('dining', 'Dining'),
        ('utilities', 'Utilities'),
        ('shopping', 'Shopping'),
        ('travel', 'Travel'),
        ('entertainment', 'Entertainment'),
        ('other', 'Other'),
    ]

    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='other')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.date} - {self.description} ({self.amount})"
