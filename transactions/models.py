from django.db import models

# Create your models here.
class Transaction(models.Model):

    CATEGORY_CHOICES = [
        ('groceries', 'Groceries'),
        ('utilities', 'Utilities'),
        ('entertainment', 'Entertainment'),
        ('rent', 'Rent/Mortgage'),
        ('transport', 'Transportation'),
        ('dining', 'Dining Out'),
        ('health', 'Health/Medical'),
        ('education', 'Education'),
        ('shopping', 'Shopping'),
        ('other', 'Other'),
    ]

    date = models.DateField()
    description = models.CharField(max_length = 255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    notes = models.TextField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def __str__(self):
        return f"{self.date} - {self.description} - ${self.amount}"